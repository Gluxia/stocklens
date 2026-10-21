"""Offline follow-up catalog, ranking and isolation regression tests."""
import json
from unittest.mock import Mock

import pytest
import requests

from backend.app.followups import add_followups, candidates, validate_ids
from backend.app.research import ResearchRequest, factual_report, attach_prices
from backend.app.diagnosis import build_diagnosis
from backend.app.prices import build_prices, price_window
from backend.app.errors import DiagnosisError
from backend.tests.test_multi_stock import financial, daily, CODES


def report(code='600519.SH', question='营收与净利润增长如何？'):
    r = factual_report(ResearchRequest(stock_code=code, question=question), build_diagnosis(code, financial(code)))
    if '股价' in question:
        start, end = price_window()
        attach_prices(r, build_prices(code, daily(code, start, end), start, end))
    return r


@pytest.fixture(autouse=True)
def disabled(monkeypatch):
    monkeypatch.delenv('LLM_FOLLOW_UP_ENABLED', raising=False)


@pytest.mark.parametrize('code', CODES)
def test_context_routing_and_evidence_stock_isolation(code):
    financial_report = add_followups(report(code))
    price = add_followups(report(code, '过去一个月的股价表现如何？'))
    both = add_followups(report(code, '营收与股价如何？'))
    assert price.follow_up_suggestions[0]['id'] == 'price_coverage'
    assert financial_report.follow_up_suggestions[0]['id'] == 'annual_comparison'
    assert both.follow_up_suggestions[0]['id'] == 'period_boundaries'
    assert len(both.follow_up_suggestions[0]['reporting_periods']) == 2
    for r in (financial_report, price, both):
        refs = {e.evidence_id for e in r.diagnosis.evidence + (r.price_analysis.evidence if r.price_analysis else [])}
        assert len(r.follow_up_suggestions) <= 4
        assert len(set(r.follow_up_questions)) == len(r.follow_up_questions)
        assert r.question not in r.follow_up_questions
        assert all(c['stock_code'] == code and set(c['evidence_ids']) <= refs for c in r.follow_up_suggestions)


def test_repeated_original_filtered_and_missing_data_pending():
    r = report(question='同一年度区间的营业收入与净利润同比增长表现有何差异？')
    assert 'annual_comparison' not in {c.id for c in candidates(r)}
    r.diagnosis.metrics = []
    assert all(c.availability == 'pending' for c in candidates(r))
    manufacturing = candidates(report('300750.SZ'))
    assert next(c for c in manufacturing if c.id == 'manufacturing_gap').availability == 'pending'
    assert all(c.availability == 'pending' for c in manufacturing if c.dimension in ('valuation', 'quality', 'manufacturing'))


@pytest.mark.parametrize('content', [
    '{}', '{bad', 'null', '{"question_ids": []}', '{"question_ids": ["invented"]}',
    '{"question_ids": ["price_coverage", "price_coverage"]}',
    '{"question_ids": ["price_coverage"], "claim": "buy"}',
    '{"question_ids": [1]}',
])
def test_invalid_selection_rejected(content):
    with pytest.raises((ValueError, TypeError)):
        validate_ids(content, candidates(report()))


def enable(monkeypatch, content):
    monkeypatch.setenv('LLM_FOLLOW_UP_ENABLED', 'true')
    monkeypatch.setenv('LLM_API_KEY', 'synthetic-key')
    monkeypatch.setenv('LLM_MODEL', 'synthetic-model')
    monkeypatch.setenv('LLM_BASE_URL', 'https://example.test/v1')
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]}
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, 'post', post)
    r = report('300750.SZ', '股价走势如何？')
    r.interpretation_mode = 'llm'
    return r, post


def test_optional_ranking_one_call_only_and_no_free_text_or_raw_question(monkeypatch):
    r, post = enable(monkeypatch, '{"question_ids": ["price_bounds", "manufacturing_gap"]}')
    add_followups(r)
    assert r.follow_up_mode == 'llm'
    assert [c['id'] for c in r.follow_up_suggestions] == ['price_bounds', 'manufacturing_gap']
    assert r.follow_up_suggestions[1]['availability'] == 'pending'
    assert post.call_count == 1
    payload = post.call_args.kwargs
    assert payload['timeout'] == (3, 8) and payload['allow_redirects'] is False
    context = json.loads(payload['json']['messages'][1]['content'])
    assert context['stock_code'] == '300750.SZ'
    assert r.question not in payload['json']['messages'][1]['content']
    assert all(c['stock_code'] == '300750.SZ' for c in context['candidates'])


@pytest.mark.parametrize('failure', ['timeout', '429', 'malformed', 'duplicate'])
def test_failure_retains_deterministic_order_and_safe_log(monkeypatch, caplog, failure):
    r, post = enable(monkeypatch, '{"question_ids": ["price_bounds", "price_bounds"]}')
    expected = [c.id for c in candidates(r)[:4]]
    if failure == 'timeout': post.side_effect = requests.Timeout('sensitive-provider-body')
    if failure == '429':
        post.return_value.status_code = 429
        post.return_value.raise_for_status.side_effect = requests.HTTPError('sensitive-provider-body')
    if failure == 'malformed': post.return_value.json.return_value = None
    add_followups(r)
    assert r.follow_up_mode == 'deterministic'
    assert [c['id'] for c in r.follow_up_suggestions] == expected
    assert post.call_count == 1
    assert 'synthetic-key' not in caplog.text and 'sensitive-provider-body' not in caplog.text


@pytest.mark.parametrize('skip', ['disabled', 'primary_failed', 'safety'])
def test_no_extra_request_unless_enabled_safe_and_primary_success(monkeypatch, skip):
    r, post = enable(monkeypatch, '{"question_ids": ["price_bounds"]}')
    if skip == 'disabled': monkeypatch.delenv('LLM_FOLLOW_UP_ENABLED')
    if skip == 'primary_failed': r.interpretation_mode = 'deterministic'
    if skip == 'safety': r.plan.safety_notice = 'Sensitive question'
    add_followups(r)
    post.assert_not_called()
    assert r.follow_up_mode == 'deterministic'


def test_foreign_sources_rejected_before_model(monkeypatch):
    r, post = enable(monkeypatch, '{"question_ids": ["price_bounds"]}')
    r.diagnosis.sources[0].parameters['thscode'] = '002594.SZ'
    with pytest.raises(DiagnosisError): add_followups(r)
    post.assert_not_called()
