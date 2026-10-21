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
    assert price.follow_up_suggestions[0]['id'] == 'annual_comparison'
    assert financial_report.follow_up_suggestions[0]['id'] == 'price_performance'
    assert both.follow_up_suggestions[0]['id'] == 'annual_comparison'
    annual = next(c for c in both.follow_up_suggestions if c['id'] == 'annual_comparison')
    assert len(annual['reporting_periods']) == 1
    assert len(annual['evidence_ids']) == 2
    for r in (financial_report, price, both):
        refs = {e.evidence_id for e in r.diagnosis.evidence + (r.price_analysis.evidence if r.price_analysis else [])}
        assert len(r.follow_up_suggestions) <= 4
        assert len(set(r.follow_up_questions)) == len(r.follow_up_questions)
        assert r.question not in r.follow_up_questions
        assert all(c['stock_code'] == code and set(c['evidence_ids']) <= refs for c in r.follow_up_suggestions)


def test_repeated_original_filtered_and_missing_data_does_not_disable_capability():
    r = report(question='同一年度区间的营业收入与净利润同比增长表现有何差异？')
    assert 'annual_comparison' not in {c.id for c in candidates(r)}
    r.diagnosis.metrics = []
    assert next(c for c in candidates(r) if c.id == 'margin_limits').availability == 'supported'
    assert not next(c for c in candidates(r) if c.id == 'margin_limits').evidence_ids
    price_query = next(c for c in candidates(r) if c.id == 'price_performance')
    assert price_query.availability == 'supported' and not price_query.evidence_ids
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
    r, post = enable(monkeypatch, '{"question_ids": ["annual_comparison", "manufacturing_gap"]}')
    add_followups(r)
    assert r.follow_up_mode == 'llm'
    assert [c['id'] for c in r.follow_up_suggestions] == ['annual_comparison', 'manufacturing_gap']
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
    r, post = enable(monkeypatch, '{"question_ids": ["annual_comparison", "annual_comparison"]}')
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
    r, post = enable(monkeypatch, '{"question_ids": ["annual_comparison"]}')
    if skip == 'disabled': monkeypatch.delenv('LLM_FOLLOW_UP_ENABLED')
    if skip == 'primary_failed': r.interpretation_mode = 'deterministic'
    if skip == 'safety': r.plan.safety_notice = 'Sensitive question'
    add_followups(r)
    post.assert_not_called()
    assert r.follow_up_mode == 'deterministic'


def test_foreign_sources_rejected_before_model(monkeypatch):
    r, post = enable(monkeypatch, '{"question_ids": ["annual_comparison"]}')
    r.diagnosis.sources[0].parameters['thscode'] = '002594.SZ'
    with pytest.raises(DiagnosisError): add_followups(r)
    post.assert_not_called()


@pytest.mark.parametrize('question,excluded', [
    ('贵州茅台这个月涨跌怎么样？', 'price_performance'),
    ('最近这只股票的走势怎样？', 'price_performance'),
    ('How has the stock price performed recently?', 'price_performance'),
    ('过去一个月价格波动范围多大，最高最低是多少？', 'price_performance'),
    ('营业收入和净利润谁增长得更快？', 'annual_comparison'),
    ('收入和盈利增速是否同步？', 'annual_comparison'),
    ('Compare sales and earnings', 'annual_comparison'),
    ('净利润率能说明什么？', 'margin_limits'),
    ('盈利能力怎么样？', 'margin_limits'),
    ('利润占营收的比重是多少？', 'margin_limits'),
    ('What does the profit margin mean?', 'margin_limits'),
    ('研发强度及产能利用情况怎么样？', 'manufacturing_gap'),
    ('经营现金流质量怎么样？', 'cashflow_gap'),
    ('当前估值贵吗？', 'valuation_gap'),
])
def test_semantic_topics_not_just_similar_wording(question, excluded):
    catalog = candidates(report('300750.SZ', question))
    assert excluded not in {c.id for c in catalog}
    assert all(c.question != question for c in catalog)


@pytest.mark.parametrize('code', CODES)
def test_pending_topics_supplement_supported_business_questions(code):
    r = add_followups(report(code, '过去一个月的股价表现如何？'))
    items = r.follow_up_suggestions
    assert 1 <= len(items) <= 4
    assert items[0]['id'] == 'annual_comparison'
    assert len(items) == 2
    pending = [i for i in items if i['availability'] == 'pending']
    assert len(pending) <= 1
    if pending:
        assert items[-1] == pending[0]
        assert not pending[0]['evidence_ids']
        assert pending[0]['id'] == ('cashflow_gap' if code == '600519.SH' else 'manufacturing_gap')
    assert not {'price_coverage', 'price_return_basis', 'period_boundaries'} & {i['id'] for i in items}
    assert all(not any(t in i['question'] for t in ('交易日', '公式', 'API', '口径')) for i in items)
    if code != '600519.SH':
        assert {'cashflow_gap', 'valuation_gap', 'manufacturing_gap'} >= {i['id'] for i in pending}


def test_financial_question_offers_real_price_request_without_claiming_existing_prices():
    from fastapi.testclient import TestClient
    from backend.app.main import app, get_fuyao_client
    from backend.app.stocks import get_stock
    code = '002594.SZ'
    r = add_followups(report(code, '营业收入与净利润的同比增长表现有何差异？'))
    item = next(i for i in r.follow_up_suggestions if i['id'] == 'price_performance')
    assert item['availability'] == 'supported' and not item['evidence_ids'] and not item['reporting_periods']
    fake = Mock()
    fake.annual_income_statements.side_effect = financial
    fake.historical_prices.side_effect = daily
    app.dependency_overrides[get_fuyao_client] = lambda: fake
    try:
        result = TestClient(app).post('/api/research', json={'stock_code': code, 'question': item['question']})
        assert result.status_code == 200
        body = result.json()
        assert body['plan']['company_name'] == get_stock(code).name
        assert body['diagnosis']['stock_code'] == code and body['price_analysis']['observations']
        assert fake.historical_prices.call_args.args[0] == code
    finally:
        app.dependency_overrides.clear()


def test_new_price_followup_keeps_default_request_window_and_existing_evidence():
    r = report('600519.SH', '过去一个月的股价表现如何？')
    old_prices = r.price_analysis.model_dump()
    old_diagnosis = r.diagnosis.model_dump()
    add_followups(r)
    assert r.price_analysis.model_dump() == old_prices
    assert r.diagnosis.model_dump() == old_diagnosis
    assert 'coverage_unverified' in r.price_analysis.issues
    assert any(f.id == 'price_coverage' for f in r.findings)


def test_supported_recommendations_first_even_if_model_ranks_pending_first(monkeypatch):
    r, post = enable(monkeypatch, '{"question_ids": ["manufacturing_gap", "annual_comparison"]}')
    add_followups(r)
    assert r.follow_up_mode == 'llm'
    assert [i['id'] for i in r.follow_up_suggestions] == ['annual_comparison', 'manufacturing_gap']
    assert post.call_count == 1


def test_pending_only_model_choice_falls_back_when_supported_questions_exist(monkeypatch):
    r, post = enable(monkeypatch, '{"question_ids": ["manufacturing_gap"]}')
    expected = [c.id for c in candidates(r)[:4]]
    add_followups(r)
    assert r.follow_up_mode == 'deterministic'
    assert [i['id'] for i in r.follow_up_suggestions] == expected
    assert post.call_count == 1


def test_incomplete_financial_evidence_not_cited_but_research_still_supported():
    r = report(question='请研究这家公司')
    missing = next(m for m in r.diagnosis.metrics if m.name == 'net_profit_margin')
    next(e for e in r.diagnosis.evidence if e.evidence_id == missing.evidence_id).status = 'unavailable'
    catalog = candidates(r)
    margin = next(c for c in catalog if c.id == 'margin_limits')
    assert margin.availability == 'supported'
    assert not margin.evidence_ids and not margin.reporting_periods
    assert next(c for c in catalog if c.id == 'annual_comparison').availability == 'supported'


@pytest.mark.parametrize('candidate_id,interpretation_id', [
    ('annual_comparison', 'interpret_growth_comparison'),
    ('margin_limits', 'interpret_margin'),
])
def test_interpretations_already_answered_are_not_recommended(candidate_id, interpretation_id):
    from backend.app.research import Interpretation
    r = report(question='过去一个月股价表现如何？')
    if candidate_id == 'margin_limits':
        r.findings = [f for f in r.findings if f.id != 'margin_context']
    item = next(c for c in candidates(r) if c.id == candidate_id)
    r.interpretations = [Interpretation(id=interpretation_id, text='Synthetic validated interpretation', evidence_ids=item.evidence_ids)]
    assert candidate_id not in {c.id for c in candidates(r)}


def test_existing_report_answers_are_not_repackaged_to_fill_four_slots():
    from backend.app.research import Interpretation
    r = report(question='过去一个月股价表现如何？')
    r.question = '请研究这家公司'
    r.findings = [f for f in r.findings if f.id != 'margin_context']
    catalog = candidates(r)
    r.interpretations = [Interpretation(id=interpretation_id, text='Synthetic validated interpretation', evidence_ids=next(c for c in catalog if c.id == id).evidence_ids)
        for id, interpretation_id in [('annual_comparison', 'interpret_growth_comparison'), ('margin_limits', 'interpret_margin')]]
    r = add_followups(r)
    assert len(r.follow_up_suggestions) == 1
    assert r.follow_up_suggestions[0]['availability'] == 'pending'
    assert not {'price_performance', 'price_bounds', 'annual_comparison', 'margin_limits'} & {c['id'] for c in r.follow_up_suggestions}


def test_existing_mixed_growth_answer_is_not_recommended_again():
    from backend.app.research import Finding
    r = report(question='过去一个月股价表现如何？')
    item = next(c for c in candidates(r) if c.id == 'annual_comparison')
    r.findings.append(Finding(id='divergent_growth', category='mixed', kind='observation', title='Synthetic comparison', text='Synthetic comparison', evidence_ids=item.evidence_ids, dimension='growth'))
    assert 'annual_comparison' not in {c.id for c in candidates(r)}


def test_model_cannot_reintroduce_already_answered_candidate(monkeypatch):
    from backend.app.research import Interpretation
    r, post = enable(monkeypatch, '{"question_ids": ["annual_comparison"]}')
    item = next(c for c in candidates(r) if c.id == 'annual_comparison')
    r.interpretations = [Interpretation(id='interpret_growth_comparison', text='Synthetic comparison', evidence_ids=item.evidence_ids)]
    expected = [c.id for c in candidates(r)[:4]]
    add_followups(r)
    assert r.follow_up_mode == 'deterministic'
    assert [c['id'] for c in r.follow_up_suggestions] == expected
    assert post.call_count == 1


def test_margin_already_explained_in_report_limitations_is_not_recommended():
    r = report(question='过去一个月股价表现如何？')
    assert any(f.id == 'margin_context' for f in r.findings)
    assert 'margin_limits' not in {c.id for c in candidates(r)}


@pytest.mark.parametrize('code', CODES)
def test_price_causality_missing_financials_offers_supported_comparison_and_fetches_again(code, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app, get_fuyao_client
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    from backend.tests.test_prices import START, END
    monkeypatch.setattr('backend.app.main.price_window', lambda: (START, END))
    fake = Mock()
    fake.annual_income_statements.side_effect = [DiagnosisError('upstream_timeout', 'Synthetic timeout'), financial(code)]
    fake.historical_prices.side_effect = daily
    app.dependency_overrides[get_fuyao_client] = lambda: fake
    try:
        client = TestClient(app)
        first = client.post('/api/research', json={'stock_code': code, 'question': '为什么最近股价上涨？'}).json()
        assert first['answer']['intent_id'] == 'price_causality'
        assert first['answer']['supporting_evidence_ids']
        assert first['diagnosis']['status'] == 'unavailable'
        item = next(c for c in first['follow_up_suggestions'] if c['id'] == 'annual_comparison')
        assert item['availability'] == 'supported'
        assert item['evidence_ids'] == [] and item['reporting_periods'] == []
        assert not any(c['id'] == 'price_performance' for c in first['follow_up_suggestions'])
        second = client.post('/api/research', json={'stock_code': code, 'question': item['question']}).json()
        assert second['answer']['intent_id'] == 'growth_comparison'
        assert second['answer']['answer_status'] == 'answered'
        assert len(second['answer']['supporting_evidence_ids']) == 2
        assert set(second['answer']['supporting_evidence_ids']) <= {e['evidence_id'] for e in second['diagnosis']['evidence']}
        assert second['diagnosis']['stock_code'] == code
        assert all(s['parameters']['thscode'] == code for s in second['diagnosis']['sources'])
        assert fake.annual_income_statements.call_count == 2
        assert fake.historical_prices.call_count == 1
        assert all(call.args[0] == code for call in fake.annual_income_statements.call_args_list)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('code', CODES)
def test_answered_financial_research_offers_price_capability_then_fetches_prices(code, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app, get_fuyao_client
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    from backend.tests.test_prices import START, END
    monkeypatch.setattr('backend.app.main.price_window', lambda: (START, END))
    fake = Mock()
    fake.annual_income_statements.side_effect = financial
    fake.historical_prices.side_effect = daily
    app.dependency_overrides[get_fuyao_client] = lambda: fake
    try:
        client = TestClient(app)
        first = client.post('/api/research', json={'stock_code': code, 'question': '营业收入与净利润的同比增长表现有何差异？'}).json()
        assert first['answer']['answer_status'] == 'answered'
        assert first['price_analysis'] is None
        item = next(c for c in first['follow_up_suggestions'] if c['id'] == 'price_performance')
        assert item['availability'] == 'supported' and not item['evidence_ids']
        second = client.post('/api/research', json={'stock_code': code, 'question': item['question']}).json()
        assert second['answer']['intent_id'] == 'price_performance'
        assert second['price_analysis']['observations']
        assert fake.historical_prices.call_count == 1
        assert fake.historical_prices.call_args.args[0] == code
        assert all(s['parameters']['thscode'] == code for s in second['price_analysis']['sources'])
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('code', CODES)
@pytest.mark.parametrize('question,excluded', [
    ('营业收入与净利润的同比增长表现有何差异？', 'annual_comparison'),
    ('净利润率能说明什么？', 'margin_limits'),
    ('为什么最近股价上涨？', 'price_performance'),
    ('评估估值水平还缺少哪些证据？', 'valuation_gap'),
    ('经营现金流能否支持账面利润？', 'cashflow_gap'),
    ('研发投入和产能利用情况如何？', 'manufacturing_gap'),
])
def test_primary_answer_topic_filtered_even_without_keyword_or_finding_clues(code, question, excluded):
    from backend.app.answers import build_answer
    r = report(code, question)
    r.answer = build_answer(r)
    r.question = '继续了解这家公司'
    r.findings = []; r.interpretations = []
    # No financial evidence in this snapshot must not disable the next financial request.
    r.diagnosis.metrics = []
    catalog = candidates(r)
    assert excluded not in {c.id for c in catalog}
    pending = [c for c in catalog if c.availability == 'pending']
    assert len(pending) <= 1
    if pending:
        assert catalog[-1] == pending[0]
    assert all(c.stock_code == code for c in catalog)
    assert all(c.availability == 'supported' for c in catalog if c.id in ('annual_comparison', 'margin_limits', 'price_performance'))


def test_foreign_answer_scope_rejected_before_followup_selection():
    from backend.app.answers import build_answer
    r = report(question='为什么最近股价上涨？')
    r.answer = build_answer(r)
    r.answer.scope.stock_code = '002594.SZ'
    with pytest.raises(DiagnosisError):
        candidates(r)


@pytest.mark.parametrize('code', CODES)
@pytest.mark.parametrize('financial_failure', [False, True])
def test_price_timeout_keeps_supported_financial_topics_despite_background(code, financial_failure, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app, get_fuyao_client
    from backend.app.research import Interpretation

    fake = Mock()
    if financial_failure:
        fake.annual_income_statements.side_effect = DiagnosisError('upstream_timeout', 'Synthetic financial timeout')
    else:
        fake.annual_income_statements.side_effect = financial
    fake.historical_prices.side_effect = DiagnosisError('upstream_timeout', 'Synthetic price timeout')

    def background_interpretations(r):
        # Simulate valid constrained selections without calling a model or changing its contract.
        if r.diagnosis.metrics:
            growth = [m.evidence_id for m in r.diagnosis.metrics if m.name in ('revenue_growth', 'net_profit_growth')]
            margin = [m.evidence_id for m in r.diagnosis.metrics if m.name == 'net_profit_margin']
            r.interpretations = [Interpretation(id='interpret_growth_comparison', text='Synthetic annual background', evidence_ids=growth),
                                Interpretation(id='interpret_margin', text='Synthetic accounting background', evidence_ids=margin)]
            r.interpretation_mode = 'llm'
        return r

    monkeypatch.setattr('backend.app.main.add_interpretation', background_interpretations)
    app.dependency_overrides[get_fuyao_client] = lambda: fake
    try:
        response = TestClient(app).post('/api/research', json={'stock_code': code, 'question': '为什么最近股价上涨？'})
        assert response.status_code == 200
        body = response.json()
        assert body['answer']['intent_id'] == 'price_causality'
        assert body['answer']['answer_status'] == 'unavailable'
        assert not body['answer']['supporting_evidence_ids']
        assert body['price_analysis']['error_code'] == 'upstream_timeout'
        assert not body['price_analysis']['observations'] and not body['price_analysis']['metrics']
        items = body['follow_up_suggestions']
        assert [item['id'] for item in items[:2]] == ['annual_comparison', 'margin_limits']
        assert all(item['availability'] == 'supported' and item['stock_code'] == code for item in items[:2])
        if financial_failure:
            assert all(not item['evidence_ids'] for item in items[:2])
        assert 'price_performance' not in {item['id'] for item in items}
        assert sum(item['availability'] == 'pending' for item in items) <= 1
        assert items[-1]['availability'] == 'pending'
        assert fake.historical_prices.call_count == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('code', CODES)
def test_background_comparison_does_not_override_margin_primary_answer(code):
    from backend.app.answers import build_answer
    from backend.app.research import Interpretation
    r = report(code, '净利润率能说明什么？')
    r.answer = build_answer(r)
    refs = [m.evidence_id for m in r.diagnosis.metrics if m.name in ('revenue_growth', 'net_profit_growth')]
    r.interpretations = [Interpretation(id='interpret_growth_comparison', text='Synthetic background comparison', evidence_ids=refs)]
    catalog = candidates(r)
    assert next(c for c in catalog if c.id == 'annual_comparison').availability == 'supported'
    assert 'margin_limits' not in {c.id for c in catalog}
