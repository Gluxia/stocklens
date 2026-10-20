import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from uuid import uuid4
from zoneinfo import ZoneInfo

from .errors import DiagnosisError
from .fuyao import CONTRACT_URL, SourceResponse
from .schemas import Diagnosis, Evidence, Metric, Source
from .stocks import get_stock, verify_source_stock


def identifier():
    return str(uuid4())


def number(value):
    if value is None:
        return None, "missing_value"
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        return None, "invalid_number"
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None, "invalid_number"
    # Bound magnitude and precision to avoid pathological upstream values.
    if not parsed.is_finite() or len(parsed.as_tuple().digits) > 38 or abs(parsed.adjusted()) > 100:
        return None, "invalid_number"
    return parsed, None


def calculate(current: Decimal | None, baseline: Decimal | None, *, growth: bool):
    if current is None or baseline is None:
        return None, "missing_or_invalid_input"
    if baseline == 0:
        return None, "zero_denominator"
    if baseline < 0:
        return None, "negative_growth_baseline" if growth else "nonpositive_revenue"
    with localcontext() as context:
        context.prec = 38
        context.rounding = ROUND_HALF_EVEN
        return ((current - baseline) if growth else current) / baseline * Decimal(100), None


def validate_record(item, stock_code):
    if not isinstance(item, dict):
        raise DiagnosisError("invalid_record", "Income statement record must be an object.")
    year = item.get("fiscal_year")
    if type(year) is not int or not 1900 <= year <= 9999:
        raise DiagnosisError("invalid_reporting_period", "A valid integer fiscal_year is required.")
    if item.get("thscode") != stock_code:
        raise DiagnosisError("stock_mismatch", "Source stock does not match the requested stock.")
    if item.get("period") != "annual" or item.get("fiscal_period") not in ("FY", "Q4"):
        raise DiagnosisError("invalid_reporting_period", "Source record is not a verified annual period.")
    timestamp = item.get("period_end_ms")
    try:
        if type(timestamp) is not int:
            raise ValueError
        period_end = datetime.fromtimestamp(timestamp / 1000, ZoneInfo("Asia/Shanghai"))
        if period_end.date().isoformat() != f"{year}-12-31":
            raise ValueError
    except (ValueError, OverflowError, OSError):
        raise DiagnosisError("invalid_reporting_period", "Annual period end does not match fiscal_year.") from None
    if item.get("currency") != "CNY":
        raise DiagnosisError("unverified_unit", "Expected CNY under the verified Fuyao contract.")
    # Explicit incompatible unit metadata must not override the documented contract silently.
    if "unit" in item and item["unit"] not in ("yuan", "元", "CNY"):
        raise DiagnosisError("unverified_unit", "Source unit conflicts with the yuan contract.")
    return year, period_end.date().isoformat()


def build_diagnosis(stock_code: str, response: SourceResponse) -> Diagnosis:
    verify_source_stock(stock_code, response)
    data = response.payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("item"), list):
        raise DiagnosisError("invalid_response", "Expected data.item to be a list.")
    source_id = identifier()
    source = Source(
        source_id=source_id, endpoint=response.endpoint, parameters=response.parameters,
        retrieved_at=response.retrieved_at, raw_json=response.raw_json,
        sha256=hashlib.sha256(response.raw_json.encode()).hexdigest(), contract_url=CONTRACT_URL,
    )
    records = {}
    evidence = []
    issues = []
    for index, item in enumerate(data["item"]):
        year, period_end = validate_record(item, stock_code)
        if year in records:
            raise DiagnosisError("duplicate_reporting_period", f"Multiple annual records for {year}; revision selection is unsupported.")
        fields = {}
        for field in ("operating_income", "net_profit"):
            value, reason = number(item.get(field))
            path = f"$.data.item[{index}]"
            ev = Evidence(
                evidence_id=identifier(), kind="source", source_id=source_id,
                endpoint=response.endpoint, original_field_name=field, json_path=f"{path}.{field}",
                reporting_period=f"{year} FY", period_end=period_end,
                value=str(value) if value is not None else None, unit="CNY yuan",
                retrieved_at=response.retrieved_at,
                status="available" if reason is None else "unavailable", reason=reason,
                metadata_json_paths={name: f"{path}.{name}" for name in (
                    "thscode", "fiscal_year", "fiscal_period", "period", "currency", "period_end_ms", "report_date_ms"
                ) if name in item},
            )
            evidence.append(ev)
            fields[field] = (value, ev.evidence_id)
            if reason:
                issues.append(f"{year}.{field}: {reason}")
        records[year] = fields

    current_year = max(records) if records else None
    previous_year = current_year - 1 if current_year else None
    if not records:
        issues.append("no_financial_data")
    elif previous_year not in records:
        issues.append(f"missing_previous_year: {previous_year}")
    metrics = []
    for name, numerator_field, growth in (
        ("revenue_growth", "operating_income", True),
        ("net_profit_growth", "net_profit", True),
        ("net_profit_margin", "net_profit", False),
    ):
        numerator = records.get(current_year, {}).get(numerator_field)
        denominator = records.get(previous_year if growth else current_year, {}).get(
            numerator_field if growth else "operating_income"
        )
        value, reason = calculate(
            numerator[0] if numerator else None, denominator[0] if denominator else None, growth=growth,
        )
        if current_year is None:
            reason = "no_financial_data"
        elif growth and previous_year not in records:
            reason = "missing_previous_year"
        formula = (
            "(current - previous) / previous * 100" if growth else "net_profit / operating_income * 100"
        )
        ev = Evidence(
            evidence_id=identifier(), kind="calculation", source_id=source_id,
            endpoint=response.endpoint, original_field_name=None, json_path=None,
            reporting_period=(f"{current_year} FY vs {previous_year} FY" if growth else f"{current_year} FY") if current_year else "unknown",
            period_end=f"{current_year}-12-31" if current_year else "unknown",
            value=str(value) if value is not None else None, unit="%", formula=formula,
            input_evidence_ids=[entry[1] for entry in (numerator, denominator) if entry],
            retrieved_at=response.retrieved_at,
            status="available" if reason is None else "unavailable", reason=reason,
        )
        evidence.append(ev)
        metrics.append(Metric(name=name, value=ev.value, status=ev.status, reason=reason, evidence_id=ev.evidence_id))
        if reason:
            issues.append(f"{name}: {reason}")
    available = sum(metric.status == "available" for metric in metrics)
    return Diagnosis(
        stock_code=stock_code, status="complete" if available == 3 else "partial" if available else "unavailable",
        current_year=current_year, previous_year=previous_year, issues=issues,
        metrics=metrics, evidence=evidence, sources=[source],
    )


def validate_stock_code(stock_code):
    if not re.fullmatch(r"[0-9]{6}\.(SH|SZ|BJ)", stock_code):
        raise DiagnosisError("invalid_stock_code", "Expected a code such as 600519.SH.", 422)
    get_stock(stock_code)
