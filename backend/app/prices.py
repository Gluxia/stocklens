"""Daily price observations; no interpolation, trading-calendar or causal assumptions."""

import calendar
import hashlib
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from .diagnosis import calculate, identifier, number
from .errors import DiagnosisError
from .fuyao import SourceResponse
from .schemas import Evidence, Metric, Source

SHANGHAI = ZoneInfo('Asia/Shanghai')
PRICE_CONTRACT = 'https://fuyao.aicubes.cn/docs/api-reference/prices/'


class PriceObservation(BaseModel):
    date: str
    close: str
    high: str
    low: str
    evidence_ids: list[str]


class PriceAnalysis(BaseModel):
    status: Literal['partial', 'unavailable'] = 'unavailable'
    requested_start: str
    requested_end: str
    actual_start: str | None = None
    actual_end: str | None = None
    currency: str = 'CNY'
    adjustment: str = 'none'
    interval: str = '1d'
    coverage: str = 'unverified'
    retrieved_at: datetime | None = None
    error_code: str | None = None
    issues: list[str] = Field(default_factory=list)
    observations: list[PriceObservation] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


def price_window(now: datetime | None = None):
    """Previous calendar month through yesterday, excluding an unfinished daily bar."""
    today = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI).date()
    month = today.month - 1 or 12
    year = today.year - (today.month == 1)
    start = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
    return start, today - timedelta(days=1)


def price_parameters(stock_code: str, start: date, end: date):
    return {'thscode': stock_code, 'interval': '1d', 'adjust': 'none',
            'start': int(datetime.combine(start, time.min, SHANGHAI).timestamp() * 1000),
            'end': int(datetime.combine(end, time.max, SHANGHAI).timestamp() * 1000)}


def build_prices(stock_code: str, response: SourceResponse, start: date, end: date):
    result = PriceAnalysis(requested_start=str(start), requested_end=str(end), retrieved_at=response.retrieved_at)
    data = response.payload.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('item'), list):
        raise DiagnosisError('invalid_response', 'Historical price response is invalid.')
    # The live response supplies these identity fields, although the documentation example omits them.
    if data.get('thscode') != stock_code or data.get('interval') != '1d' or data.get('adjust') != 'none':
        raise DiagnosisError('unverified_price_metadata', 'Historical stock, interval or adjustment could not be verified.')
    source_id = identifier()
    result.sources.append(Source(source_id=source_id, endpoint=response.endpoint, parameters=response.parameters,
        retrieved_at=response.retrieved_at, sha256=hashlib.sha256(response.raw_json.encode()).hexdigest(),
        raw_json=response.raw_json, contract_url=PRICE_CONTRACT, reporting_basis='daily_unadjusted',
        unit_basis='A-share prices are CNY per the Fuyao prices contract.'))
    result.issues.append('coverage_unverified')
    rows = []
    seen = set()
    for index, bar in enumerate(data['item']):
        if not isinstance(bar, dict) or type(bar.get('date_ms')) is not int:
            result.issues.append('invalid_price_date')
            continue
        try:
            day = datetime.fromtimestamp(bar['date_ms'] / 1000, SHANGHAI).date()
        except (ValueError, OverflowError, OSError):
            result.issues.append('invalid_price_date')
            continue
        if day in seen:
            # Never choose silently between duplicate or conflicting bars.
            raise DiagnosisError('duplicate_price_date', 'Duplicate daily price observations were returned.')
        seen.add(day)
        if not start <= day <= end:
            result.issues.append('out_of_range_price')
            continue
        values = {key: number(bar.get(key))[0] for key in ('open_price', 'high_price', 'low_price', 'close_price')}
        if any(v is None or v <= 0 for v in values.values()):
            result.issues.append('invalid_price_value')
            continue
        if not (values['low_price'] <= min(values['open_price'], values['close_price']) <= max(values['open_price'], values['close_price']) <= values['high_price']):
            result.issues.append('invalid_price_range')
            continue
        ids = {}
        for field, value in values.items():
            ev = Evidence(evidence_id=identifier(), kind='source', source_id=source_id, endpoint=response.endpoint,
                original_field_name=field, json_path=f'$.data.item[{index}].{field}', reporting_period=str(day),
                period_end=str(day), value=str(value), unit='CNY yuan', retrieved_at=response.retrieved_at,
                status='available', metadata_json_paths={'date_ms': f'$.data.item[{index}].date_ms',
                    'thscode': '$.data.thscode', 'interval': '$.data.interval', 'adjust': '$.data.adjust'})
            result.evidence.append(ev)
            ids[field] = ev.evidence_id
        rows.append((day, values, ids))
    rows.sort(key=lambda row: row[0])
    result.observations = [PriceObservation(date=str(day), close=str(v['close_price']), high=str(v['high_price']), low=str(v['low_price']), evidence_ids=list(ids.values())) for day, v, ids in rows]
    if not rows:
        result.issues.append('no_price_data')
        return result
    result.actual_start, result.actual_end = str(rows[0][0]), str(rows[-1][0])
    result.status = 'partial'  # Trading-calendar completeness is deliberately not asserted.
    if (end - rows[-1][0]).days > 7:
        result.issues.append('stale_price_data')
    if len(rows) < 2:
        result.issues.append('insufficient_price_observations')
    first, last = rows[0], rows[-1]
    highest = max(rows, key=lambda row: row[1]['high_price'])
    lowest = min(rows, key=lambda row: row[1]['low_price'])
    ret = calculate(last[1]['close_price'], first[1]['close_price'], growth=True)[0] if len(rows) >= 2 else None
    specs = [
        ('price_return', ret, '%', '(end_close / start_close - 1) * 100', [last[2]['close_price'], first[2]['close_price']]),
        ('price_high', highest[1]['high_price'], 'CNY yuan', 'max(valid daily high_price)', [row[2]['high_price'] for row in rows]),
        ('price_low', lowest[1]['low_price'], 'CNY yuan', 'min(valid daily low_price)', [row[2]['low_price'] for row in rows]),
        ('price_count', len(rows), 'observations', 'count(valid unique daily close_price observations)', [row[2]['close_price'] for row in rows]),
    ]
    for name, value, unit, formula, inputs in specs:
        eid = identifier()
        reason = 'insufficient_price_observations' if value is None else None
        result.evidence.append(Evidence(evidence_id=eid, kind='calculation', source_id=source_id, endpoint=response.endpoint,
            original_field_name=None, json_path=None, reporting_period=f'{result.actual_start} ~ {result.actual_end}',
            period_end=result.actual_end, value=str(value) if value is not None else None, unit=unit, formula=formula,
            input_evidence_ids=inputs, retrieved_at=response.retrieved_at, status='available' if value is not None else 'unavailable', reason=reason))
        result.metrics.append(Metric(name=name, value=str(value) if value is not None else None, unit=unit,
            status='available' if value is not None else 'unavailable', reason=reason, evidence_id=eid))
    return result
