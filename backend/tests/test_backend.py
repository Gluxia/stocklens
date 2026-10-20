"""All monetary amounts below are synthetic test inputs, not company financials."""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import requests
from fastapi.testclient import TestClient

from backend.app.diagnosis import build_diagnosis, calculate, number
from backend.app.errors import DiagnosisError
from backend.app.fuyao import FuyaoClient, INCOME_ENDPOINT, SourceResponse
from backend.app.main import app, get_fuyao_client


def row(year, revenue="120", profit="30", **overrides):
    record = {
        "thscode": "600519.SH", "period": "annual", "fiscal_year": year,
        "fiscal_period": "FY", "currency": "CNY",
        "period_end_ms": int(datetime(year, 12, 31, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000),
        "operating_income": revenue, "net_profit": profit,
    }
    return record | overrides


def source(rows):
    payload = {"code": 0, "data": {"item": rows}}
    return SourceResponse(
        INCOME_ENDPOINT, {"thscode": "600519.SH", "period": "annual", "limit": 4},
        datetime.now(timezone.utc), json.dumps(payload), payload,
    )


def diagnose(rows):
    return build_diagnosis("600519.SH", source(rows))


def test_calculations_and_traceability():
    response = source([row(2023, "100", "20"), row(2024)])
    report = build_diagnosis("600519.SH", response)
    assert report.status == "complete"
    assert report.current_year == 2024
    assert report.previous_year == 2023
    assert [Decimal(m.value) for m in report.metrics] == [Decimal(20), Decimal(50), Decimal(25)]
    by_id = {e.evidence_id: e for e in report.evidence}
    assert len(by_id) == len(report.evidence)
    original = json.loads(report.sources[0].raw_json)
    for metric in report.metrics:
        calculated = by_id[metric.evidence_id]
        assert calculated.formula
        assert len(calculated.input_evidence_ids) == 2
        for reference in calculated.input_evidence_ids:
            item = by_id[reference]
            assert item.kind == "source"
            assert item.unit == "CNY yuan"
            assert item.retrieved_at.tzinfo is not None
            index = int(item.json_path.split("[")[1].split("]")[0])
            assert item.value == original["data"]["item"][index][item.original_field_name]
    assert report.sources[0].sha256 == hashlib.sha256(response.raw_json.encode()).hexdigest()


def test_decimal_precision():
    result, reason = calculate(Decimal("0.3"), Decimal("0.1"), growth=True)
    assert result == Decimal("200")
    assert reason is None


@pytest.mark.parametrize("value", [True, False, "NaN", "Infinity", "-Infinity", "text", {}, [], 1.2, "1e999", "9" * 39])
def test_invalid_numbers(value):
    assert number(value) == (None, "invalid_number")


@pytest.mark.parametrize("baseline,expected", [("0", "zero_denominator"), ("-1", "negative_growth_baseline")])
def test_invalid_growth_denominator(baseline, expected):
    assert calculate(Decimal(2), Decimal(baseline), growth=True) == (None, expected)


def test_missing_values_and_zero_revenue():
    report = diagnose([row(2024, "0", None), row(2023, "100", "20")])
    assert report.status == "partial"
    assert report.metrics[0].value == "-100"
    assert report.metrics[1].value is None
    assert report.metrics[2].value is None
    assert report.metrics[2].reason == "missing_or_invalid_input"
    assert diagnose([row(2024, "0", "10")]).metrics[2].reason == "zero_denominator"


def test_negative_profit_is_valid_for_margin():
    report = diagnose([row(2024, "100", "-10")])
    assert report.metrics[2].value == "-10.0"


def test_missing_year_does_not_compare_nonconsecutive_periods():
    report = diagnose([row(2024), row(2022)])
    assert report.status == "partial"
    assert report.metrics[0].reason == "missing_previous_year"
    assert report.metrics[1].value is None
    assert report.metrics[2].value is not None


def test_empty_data():
    report = diagnose([])
    assert report.status == "unavailable"
    assert report.current_year is None
    assert all(m.value is None and m.reason == "no_financial_data" for m in report.metrics)


def test_absent_field_is_not_zero():
    record = row(2024)
    del record["net_profit"]
    report = diagnose([record, row(2023)])
    assert report.metrics[0].value == "0"
    assert report.metrics[1].value is None
    assert report.metrics[2].value is None
    assert any(e.original_field_name == "net_profit" and e.reason == "missing_value" for e in report.evidence)


def test_invalid_value_is_explicit_and_preserved_in_source():
    report = diagnose([row(2024, profit="bad"), row(2023)])
    assert report.status == "partial"
    assert "2024.net_profit: invalid_number" in report.issues
    assert json.loads(report.sources[0].raw_json)["data"]["item"][0]["net_profit"] == "bad"


def test_negative_revenue_margin_unavailable():
    assert diagnose([row(2024, revenue="-100")]).metrics[2].reason == "nonpositive_revenue"


def test_duplicate_period_is_not_overwritten():
    with pytest.raises(DiagnosisError, match="Multiple annual records") as exc:
        diagnose([row(2024), row(2024, "999")])
    assert exc.value.code == "duplicate_reporting_period"


@pytest.mark.parametrize("overrides,code", [
    ({"fiscal_year": "2024"}, "invalid_reporting_period"),
    ({"fiscal_year": True}, "invalid_reporting_period"),
    ({"period": "quarterly"}, "invalid_reporting_period"),
    ({"fiscal_period": "Q1"}, "invalid_reporting_period"),
    ({"period_end_ms": None}, "invalid_reporting_period"),
    ({"period_end_ms": 0}, "invalid_reporting_period"),
    ({"currency": None}, "unverified_unit"),
    ({"currency": "USD"}, "unverified_unit"),
    ({"unit": "million yuan"}, "unverified_unit"),
    ({"thscode": "000001.SZ"}, "stock_mismatch"),
])
def test_metadata_validation(overrides, code):
    with pytest.raises(DiagnosisError) as exc:
        diagnose([row(2024, **overrides)])
    assert exc.value.code == code


@pytest.fixture
def web_client():
    fake = Mock()
    fake.annual_income_statements.return_value = source([row(2024), row(2023, "100", "20")])
    app.dependency_overrides[get_fuyao_client] = lambda: fake
    with TestClient(app) as client:
        yield client, fake
    app.dependency_overrides.clear()


def test_endpoint(web_client):
    client, fake = web_client
    response = client.get("/api/diagnosis", params={"stock_code": "600519.SH"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["metrics"][0]["value"] == "20.0"
    assert "raw_json" in body["sources"][0]
    fake.annual_income_statements.assert_called_once_with("600519.SH")


@pytest.mark.parametrize("stock", ["BAD", "600519", "600519.sh", "600519.SH,000001.SZ", "000001.SZ"])
def test_stock_validation_before_network(web_client, stock):
    client, fake = web_client
    assert client.get("/api/diagnosis", params={"stock_code": stock}).status_code == 422
    fake.annual_income_statements.assert_not_called()


def test_required_stock(web_client):
    client, fake = web_client
    assert client.get("/api/diagnosis").status_code == 422
    fake.annual_income_statements.assert_not_called()


@pytest.mark.parametrize("code,status", [("upstream_timeout", 504), ("missing_api_key", 503), ("duplicate_reporting_period", 502)])
def test_endpoint_error_mapping(web_client, code, status):
    client, fake = web_client
    fake.annual_income_statements.side_effect = DiagnosisError(code, "Safe message", status)
    response = client.get("/api/diagnosis?stock_code=600519.SH")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_missing_key_never_calls_network(monkeypatch):
    get = Mock()
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(DiagnosisError) as exc:
        FuyaoClient("").annual_income_statements("600519.SH")
    assert exc.value.code == "missing_api_key"
    get.assert_not_called()


def test_transport_contract_and_decimal_parsing(monkeypatch):
    response = Mock(status_code=200, text='{"code":0,"data":{"item":[]},"number":0.1234567890123456789}')
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    result = FuyaoClient("test-secret").annual_income_statements("600519.SH")
    assert result.payload["number"] == Decimal("0.1234567890123456789")
    get.assert_called_once_with(INCOME_ENDPOINT, params={"thscode": "600519.SH", "period": "annual", "limit": 4},
                                headers={"X-api-key": "test-secret"}, timeout=15, allow_redirects=False)


@pytest.mark.parametrize("exception,code", [
    (requests.Timeout("secret"), "upstream_timeout"),
    (requests.ConnectionError("secret"), "upstream_http_error"),
    (requests.HTTPError("secret"), "upstream_http_error"),
])
def test_transport_failure_sanitization(monkeypatch, exception, code):
    monkeypatch.setattr(requests, "get", Mock(side_effect=exception))
    with pytest.raises(DiagnosisError) as exc:
        FuyaoClient("test-secret").annual_income_statements("600519.SH")
    assert exc.value.code == code
    assert "secret" not in str(exc.value)


@pytest.mark.parametrize("status", [301, 401, 429, 500])
def test_http_status_errors(monkeypatch, status):
    response = Mock(status_code=status, text='{"code":0,"data":{"item":[]}}')
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError("private provider body")
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    with pytest.raises(DiagnosisError) as exc:
        FuyaoClient("test-secret").annual_income_statements("600519.SH")
    assert exc.value.code == ("upstream_rate_limited" if status == 429 else "upstream_http_error")


def test_snapshot_reuses_original_contract(monkeypatch):
    get = Mock(return_value=Mock(status_code=200, text='{"code":0,"data":{}}'))
    monkeypatch.setattr(requests, "get", get)
    FuyaoClient("test-secret").price_snapshot("600519.SH")
    assert get.call_args.kwargs["params"] == {"thscodes": "600519.SH"}


@pytest.mark.parametrize("text,code", [
    ("not json", "invalid_json"), ('{"code":0,"x":NaN}', "invalid_json"),
    ("[]", "invalid_response"), ('{"code":false}', "invalid_response"),
    ('{"code":2001,"message":"secret"}', "upstream_api_error"),
])
def test_invalid_upstream_responses(monkeypatch, text, code):
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(status_code=200, text=text)))
    with pytest.raises(DiagnosisError) as exc:
        FuyaoClient("test-secret").annual_income_statements("600519.SH")
    assert exc.value.code == code
    assert "secret" not in str(exc.value)


@pytest.mark.parametrize("data", [None, {}, {"item": None}, {"item": {}}, {"item": [None]}])
def test_invalid_data_shape(data):
    response = source([])
    response.payload["data"] = data
    with pytest.raises(DiagnosisError):
        build_diagnosis("600519.SH", response)


def test_transport_through_endpoint(monkeypatch):
    response = Mock(status_code=200, text=source([row(2024), row(2023, "100", "20")]).raw_json)
    monkeypatch.setenv("FUYAO_API_KEY", "test-secret")
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    with TestClient(app) as client:
        result = client.get("/api/diagnosis?stock_code=600519.SH")
    assert result.status_code == 200
    assert result.json()["status"] == "complete"
    assert "test-secret" not in result.text
