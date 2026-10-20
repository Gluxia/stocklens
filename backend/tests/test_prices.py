"""Synthetic prices only; these fixtures are not company market data."""
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

from backend.app.errors import DiagnosisError
from backend.app.fuyao import FuyaoClient, SourceResponse
from backend.app.prices import build_prices, price_window, price_parameters
from backend.app.research import attach_prices, interpretation_catalog
from backend.app.llm import validate_selection, add_interpretation
from backend.app.main import app, get_fuyao_client
from backend.tests.test_research import report
from backend.tests.test_backend import row, source

START, END = date(2025, 9, 20), date(2025, 10, 19)
ENDPOINT = 'https://fuyao.aicubes.cn/api/a-share/prices/historical'


def bar(day, close='110', high='120', low='90'):
    return {'date_ms': price_parameters('600519.SH', date.fromisoformat(day), END)['start'],
            'open_price': '100', 'close_price': close, 'high_price': high, 'low_price': low}


def prices(bars=None, **metadata):
    payload = {'code': 0, 'data': {'thscode': '600519.SH', 'interval': '1d', 'adjust': 'none',
        'item': bars if bars is not None else [bar('2025-09-22', '100'), bar('2025-10-17', '110')], **metadata}}
    return SourceResponse(ENDPOINT, price_parameters('600519.SH', START, END), datetime(2025, 10, 20, tzinfo=timezone.utc), json.dumps(payload), payload)


def build(response=None):
    return build_prices('600519.SH', response or prices(), START, END)


def test_decimal_calculation_dates_and_complete_evidence_graph():
    p = build()
    assert p.status == 'partial' and p.coverage == 'unverified'
    assert (p.actual_start, p.actual_end) == ('2025-09-22', '2025-10-17')
    assert p.currency == 'CNY' and p.adjustment == 'none'
    metrics = {m.name: m for m in p.metrics}
    assert Decimal(metrics['price_return'].value) == Decimal('10')
    assert metrics['price_high'].value == '120'
    assert metrics['price_low'].value == '90'
    assert metrics['price_count'].value == '2'
    ids = {e.evidence_id for e in p.evidence}
    assert len(ids) == len(p.evidence)
    assert all(set(e.input_evidence_ids) <= ids for e in p.evidence)
    for ev in p.evidence:
        assert ev.source_id == p.sources[0].source_id
        if ev.kind == 'source':
            index = int(ev.json_path.split('[')[1].split(']')[0])
            assert ev.value == prices().payload['data']['item'][index][ev.original_field_name]
    assert p.sources[0].raw_json == prices().raw_json


def test_precision_and_negative_return():
    p = build(prices([bar('2025-09-22', '99.123456789123456789'), bar('2025-10-17', '90.123456789123456789')]))
    ret = p.metrics[0].value
    assert len(ret) > 20 and Decimal(ret) < 0


@pytest.mark.parametrize('value', [None, '', 'NaN', 'Infinity', True, 0, '-1', 1.2, '1e999', 'x'])
def test_invalid_prices_are_excluded_without_inventing_data(value):
    p = build(prices([bar('2025-09-22', close=value)]))
    assert p.status == 'unavailable' and not p.observations and not p.metrics
    assert 'invalid_price_value' in p.issues


@pytest.mark.parametrize('field,value,code', [('thscode','000001.SZ','unverified_price_metadata'), ('adjust','forward','unverified_price_metadata'), ('interval','1w','unverified_price_metadata'), ('thscode',None,'unverified_price_metadata')])
def test_metadata_must_be_verified(field, value, code):
    with pytest.raises(DiagnosisError, match='could not be verified') as exc:
        build(prices(**{field:value}))
    assert exc.value.code == code


def test_duplicates_are_rejected_even_if_identical():
    with pytest.raises(DiagnosisError) as exc:
        build(prices([bar('2025-09-22'), bar('2025-09-22')]))
    assert exc.value.code == 'duplicate_price_date'


def test_missing_single_stale_unsorted_and_out_of_range_data():
    assert build(prices([])).status == 'unavailable'
    single = build(prices([bar('2025-09-22')]))
    assert single.metrics[0].value is None
    assert single.metrics[0].status == 'unavailable'
    assert 'stale_price_data' in single.issues
    p = build(prices([bar('2025-10-17'), bar('2025-09-22'), bar('2025-09-01')]))
    assert p.actual_start == '2025-09-22'
    assert 'out_of_range_price' in p.issues


@pytest.mark.parametrize('bad', [{'date_ms': True}, {'date_ms': 10**80}, {'date_ms': 'bad'}, None, bar('2025-09-22', high='50')])
def test_invalid_date_or_ohlc_is_rejected(bad):
    p = build(prices([bad]))
    assert p.status == 'unavailable'


def test_calendar_month_window_leap_year_and_timezone():
    assert price_window(datetime(2024, 3, 31, tzinfo=timezone.utc)) == (date(2024, 2, 29), date(2024, 3, 30))
    assert price_window(datetime(2025, 1, 1, tzinfo=timezone.utc)) == (date(2024, 12, 1), date(2024, 12, 31))
    assert price_parameters('600519.SH', START, END)['adjust'] == 'none'


def test_price_interpretation_only_uses_catalog_and_available_refs():
    r = attach_prices(report(question='股价表现'), build())
    assert r.plan.dimensions[0].id == 'price'
    candidate = next(c for c in interpretation_catalog(r) if c.id == 'interpret_price_return')
    assert '不能认定财务事件导致' in candidate.text
    selected = {'interpretations': [dict(id=candidate.id, evidence_ids=candidate.evidence_ids)]}
    assert validate_selection(json.dumps(selected), [candidate], r) == [candidate]
    selected['interpretations'][0]['evidence_ids'] = ['invented']
    with pytest.raises(ValueError):
        validate_selection(json.dumps(selected), [candidate], r)


@pytest.mark.parametrize('code', ['upstream_rate_limited', 'upstream_timeout', 'upstream_http_error', 'invalid_response'])
def test_research_price_failures_keep_financial_report(monkeypatch, code):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    client = Mock()
    client.annual_income_statements.return_value = source([row(2024), row(2023)])
    client.historical_prices.side_effect = DiagnosisError(code, 'Sanitized error', 429)
    app.dependency_overrides[get_fuyao_client] = lambda: client
    try:
        response = TestClient(app).post('/api/research', json={'question':'过去一个月股价表现'})
        assert response.status_code == 200
        body = response.json()
        assert body['price_analysis']['error_code'] == code
        assert body['price_analysis']['observations'] == []
        assert body['diagnosis']['metrics']
        assert not any(f['dimension'] == 'price' and f['category'] != 'unknown' for f in body['findings'])
    finally:
        app.dependency_overrides.clear()


def test_price_journey_survives_financial_api_failure(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    client = Mock()
    client.annual_income_statements.side_effect = DiagnosisError('upstream_timeout','Timeout',504)
    client.historical_prices.side_effect = lambda code,start,end: prices([bar(str(end))])
    app.dependency_overrides[get_fuyao_client] = lambda: client
    try:
        body = TestClient(app).post('/api/research',json={'question':'股价表现'}).json()
        assert body['diagnosis']['status'] == 'unavailable'
        assert body['price_analysis']['observations']
    finally:
        app.dependency_overrides.clear()


def test_transport_verified_request_and_http429(monkeypatch):
    get = Mock(return_value=Mock(status_code=429))
    monkeypatch.setattr(requests,'get',get)
    with pytest.raises(DiagnosisError) as exc:
        FuyaoClient('synthetic-key').historical_prices('600519.SH',START,END)
    assert exc.value.code == 'upstream_rate_limited'
    assert get.call_args.args[0] == ENDPOINT
    assert get.call_args.kwargs['params'] == price_parameters('600519.SH',START,END)


def test_price_sensitive_question_keeps_deterministic_fallback(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','synthetic-key')
    monkeypatch.setenv('LLM_MODEL','synthetic-model')
    post = Mock()
    monkeypatch.setattr(requests,'post',post)
    r = attach_prices(report(question='股价会涨吗，保证收益可以买入吗'),build())
    assert add_interpretation(r).interpretation_mode == 'deterministic'
    post.assert_not_called()


def test_full_price_journey_llm_selection_and_timeout(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'synthetic-key')
    monkeypatch.setenv('LLM_MODEL', 'synthetic-model')
    monkeypatch.setenv('LLM_BASE_URL', 'https://example.test/v1')
    client = Mock()
    client.annual_income_statements.return_value = source([row(2024), row(2023)])
    client.historical_prices.side_effect = lambda code, start, end: prices([bar(str(start), '100'), bar(str(end), '110')])
    def selected_response(*args, **kwargs):
        prompt = json.loads(kwargs['json']['messages'][1]['content'])
        candidate = next(c for c in prompt['candidates'] if c['id'] == 'interpret_price_return')
        assert prompt['dimensions'][0] == 'price'
        content = json.dumps({'interpretations': [{'id': candidate['id'], 'evidence_ids': candidate['evidence_ids']}]})
        return Mock(status_code=200, json=lambda: {'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]})
    post = Mock(side_effect=selected_response)
    monkeypatch.setattr(requests, 'post', post)
    app.dependency_overrides[get_fuyao_client] = lambda: client
    try:
        response = TestClient(app).post('/api/research', json={'question': '贵州茅台过去一个月的股价表现如何？'})
        assert response.status_code == 200
        body = response.json()
        assert body['interpretation_mode'] == 'llm'
        assert body['interpretations'][0]['id'] == 'interpret_price_return'
        assert body['price_analysis']['metrics'][0]['value'] == '10.0'
        post.side_effect = requests.Timeout()
        fallback = TestClient(app).post('/api/research', json={'question':'过去一个月股价表现'}).json()
        assert fallback['interpretation_mode'] == 'deterministic'
        assert fallback['price_analysis']['observations']
        assert any(o['id'] == 'price_return' for o in fallback['observations'])
    finally:
        app.dependency_overrides.clear()
