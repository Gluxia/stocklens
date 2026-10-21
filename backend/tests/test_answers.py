"""Deterministic answers use synthetic source snapshots, never real company amounts."""
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from itertools import product
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.app.answer_contract import Answer
from backend.app.answers import build_answer
from backend.app.diagnosis import build_diagnosis
from backend.app.errors import DiagnosisError
from backend.app.main import app, get_fuyao_client
from backend.app.prices import build_prices
from backend.app.research import ResearchReport, ResearchRequest, attach_prices, factual_report
from backend.tests.test_answer_contract import QUESTIONS, CODES
from backend.tests.test_backend import row, source
from backend.tests.test_prices import START, END, bar, prices


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    monkeypatch.delenv('LLM_MODEL', raising=False)
    monkeypatch.delenv('LLM_FOLLOW_UP_ENABLED', raising=False)
    yield
    app.dependency_overrides.clear()


def financial(code, revenue='120', profit='30', years=(2024, 2023)):
    response = source([row(years[0], revenue, profit, thscode=code), row(years[1], '100', '20', thscode=code)])
    return replace(response, parameters={**response.parameters, 'thscode': code})


def price_source(code, close='110', bars=None):
    response = prices([bar('2025-09-22', '100'), bar('2025-10-17', close)] if bars is None else bars, thscode=code)
    return replace(response, parameters={**response.parameters, 'thscode': code})


def report(question, code='600519.SH', revenue='120', profit='30', close='110', bars=None):
    r = factual_report(ResearchRequest(stock_code=code, question=question), build_diagnosis(code, financial(code, revenue, profit)))
    if any(d.id == 'price' for d in r.plan.dimensions):
        attach_prices(r, build_prices(code, price_source(code, close, bars), START, END))
    return r


def resign(source_record, payload):
    source_record.raw_json = json.dumps(payload)
    source_record.sha256 = hashlib.sha256(source_record.raw_json.encode()).hexdigest()


def metric_evidence(r, name):
    owner = r.price_analysis if name.startswith('price_') else r.diagnosis
    m = next(m for m in owner.metrics if m.name == name)
    ev = next(e for e in owner.evidence if e.evidence_id == m.evidence_id)
    return m, ev


def assert_refs(r, answer):
    records = r.diagnosis.evidence + (r.price_analysis.evidence if r.price_analysis else [])
    sources = {s.source_id: s for s in r.diagnosis.sources + (r.price_analysis.sources if r.price_analysis else [])}
    for id in answer.supporting_evidence_ids:
        ev = next(e for e in records if e.evidence_id == id)
        assert ev.status == 'available'
        assert sources[ev.source_id].parameters['thscode'] == r.diagnosis.stock_code
    assert answer.scope.stock_code == r.diagnosis.stock_code


@pytest.mark.parametrize('code,case', list(product(CODES, QUESTIONS)))
def test_seven_intents_three_companies_with_validated_sources(code, case):
    question, intent = case
    r = report(question, code)
    original = r.model_dump_json()
    answer = build_answer(r)
    assert answer.intent_id == intent
    expected = {'price_performance':'partial', 'growth_comparison':'answered', 'margin_meaning':'answered',
                'valuation_evidence_gap':'answered', 'cashflow_support':'unavailable',
                'price_causality':'partial', 'manufacturing_evidence_gap':'unavailable'}
    assert answer.answer_status == expected[intent]
    assert_refs(r, answer)
    assert r.model_dump_json() == original
    if intent in ('valuation_evidence_gap','cashflow_support','manufacturing_evidence_gap'):
        assert not answer.supporting_evidence_ids
        assert answer.missing_evidence
        assert '20.00%' not in answer.direct_answer and '50.00%' not in answer.direct_answer


@pytest.mark.parametrize('revenue,profit,relation,difference', [
    ('120','30','高于','30.00'), ('150','22','低于','40.00'), ('120','24','等于','0.00'),
    ('80','10','低于','30.00'), ('80','24','高于','40.00'),
])
def test_growth_comparison_uses_decimal_and_two_valid_references(revenue, profit, relation, difference):
    r = report(QUESTIONS[1][0], revenue=revenue, profit=profit)
    answer = build_answer(r)
    assert answer.answer_status == 'answered'
    assert relation in answer.direct_answer and f'{difference} 个百分点' in answer.direct_answer
    assert '2024 年度对比 2023 年度' in answer.direct_answer
    assert answer.supporting_evidence_ids == [m.evidence_id for m in r.diagnosis.metrics[:2]]
    assert len(answer.supporting_evidence_ids) == 2


@pytest.mark.parametrize('mutation', ['missing_metric','missing_evidence','missing_input','wrong_value','nan','wrong_unit',
    'input_unit','input_field','input_order','input_period','root_period','root_end','formula','basis','raw_hash',
    'raw_amount','raw_unit','raw_currency','duplicate_input','unavailable_input','root_source','source_endpoint','snapshot_time'])
def test_bad_growth_evidence_never_produces_comparison(mutation):
    r = report(QUESTIONS[1][0]); m, ev = metric_evidence(r, 'net_profit_growth')
    leaf = next(e for e in r.diagnosis.evidence if e.evidence_id == ev.input_evidence_ids[0])
    src = r.diagnosis.sources[0]
    if mutation == 'missing_metric': r.diagnosis.metrics.remove(m)
    if mutation == 'missing_evidence': r.diagnosis.evidence.remove(ev)
    if mutation == 'missing_input': ev.input_evidence_ids[0] = 'unknown-ref'
    if mutation == 'wrong_value': m.value = '999'
    if mutation == 'nan': ev.value = m.value = 'NaN'
    if mutation == 'wrong_unit': m.unit = ev.unit = 'CNY yuan'
    if mutation == 'input_unit': leaf.unit = 'USD'
    if mutation == 'input_field': leaf.original_field_name = 'parent_holder_net_profit'
    if mutation == 'input_order': ev.input_evidence_ids.reverse()
    if mutation == 'input_period': leaf.reporting_period = '2023 FY'
    if mutation == 'root_period': ev.reporting_period = '2023 FY vs 2022 FY'
    if mutation == 'root_end': ev.period_end = '2023-12-31'
    if mutation == 'formula': ev.formula = 'invented formula'
    if mutation == 'basis': src.reporting_basis = 'parent_only'
    if mutation == 'raw_hash': src.sha256 = 'incorrect'
    if mutation in ('raw_amount', 'raw_unit', 'raw_currency'):
        payload = json.loads(src.raw_json)
        payload['data']['item'][0][{'raw_amount':'net_profit','raw_unit':'unit','raw_currency':'currency'}[mutation]] = {'raw_amount':'999','raw_unit':'million','raw_currency':'USD'}[mutation]
        resign(src, payload)
    if mutation == 'duplicate_input': ev.input_evidence_ids[1] = ev.input_evidence_ids[0]
    if mutation == 'unavailable_input': leaf.status = 'unavailable'
    if mutation == 'root_source': ev.source_id = 'unknown-source'
    if mutation == 'source_endpoint': src.endpoint = 'https://example.test/other'
    if mutation == 'snapshot_time': ev.retrieved_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    answer = build_answer(r)
    assert answer.answer_status != 'answered'
    assert '百分点差异' in answer.direct_answer
    assert '两者相差' not in answer.direct_answer
    assert m.evidence_id not in answer.supporting_evidence_ids
    assert answer.missing_evidence


def test_comparison_rejects_different_verified_snapshots():
    r = report(QUESTIONS[1][0]); other = report(QUESTIONS[1][0])
    m, root = metric_evidence(other, 'net_profit_growth')
    r.diagnosis.metrics[1] = m
    r.diagnosis.sources += other.diagnosis.sources
    r.diagnosis.evidence += other.diagnosis.evidence
    answer = build_answer(r)
    assert answer.answer_status == 'partial'
    assert any(g.code == 'incompatible_growth_comparison' for g in answer.missing_evidence)
    assert '不能比较' in answer.direct_answer


@pytest.mark.parametrize('rows', [[], [row(2024)], [row(2024),row(2022)], [row(2024),row(2023,'0','0')]])
def test_missing_year_or_baseline_is_not_filled(rows):
    r = factual_report(ResearchRequest(question=QUESTIONS[1][0]), build_diagnosis('600519.SH', source(rows)))
    answer = build_answer(r)
    assert answer.answer_status == 'unavailable'
    assert not answer.supporting_evidence_ids
    assert answer.missing_evidence


@pytest.mark.parametrize('close,word,number', [('110','上涨','10.00'),('90','下跌','-10.00'),('100','持平','0.00')])
@pytest.mark.parametrize('question', [QUESTIONS[0][0], QUESTIONS[5][0]])
def test_price_directions_only_come_from_validated_evidence(question, close, word, number):
    r = report(question, close=close)
    answer = build_answer(r)
    assert answer.answer_status == 'partial'
    assert word in answer.direct_answer and number+'%' in answer.direct_answer
    assert '不复权' in answer.direct_answer and '不含分红' in answer.direct_answer
    assert '2025-09-22 至 2025-10-17' in answer.direct_answer
    assert str(answer.scope.price_requested_start) == '2025-09-20'
    assert str(answer.scope.price_observed_start) == '2025-09-22'
    assert answer.scope.reporting_periods == []
    if question == QUESTIONS[5][0]:
        assert '无法解释' in answer.direct_answer and '因果' in answer.direct_answer
        if close != '110': assert '未显示上涨' in answer.direct_answer
    assert_refs(r, answer)


@pytest.mark.parametrize('mutation', ['no_price_analysis','empty','single','timeout','wrong_adjustment','wrong_currency',
                                    'bad_period','bad_observations','bad_raw_ohlc','wrong_input_order','missing_input','invalid_number','request_mismatch'])
def test_missing_or_invalid_prices_never_assert_a_direction(mutation):
    r = report(QUESTIONS[5][0]); p = r.price_analysis
    m, ev = metric_evidence(r, 'price_return')
    if mutation == 'no_price_analysis': r.price_analysis = None
    if mutation == 'empty': r.price_analysis = build_prices('600519.SH', price_source('600519.SH', bars=[]), START, END)
    if mutation == 'single': r.price_analysis = build_prices('600519.SH', price_source('600519.SH', bars=[bar('2025-09-22')]), START, END)
    if mutation == 'timeout': p.error_code = 'upstream_timeout'; p.metrics = []; p.sources = []; p.evidence = []; p.observations = []
    if mutation == 'wrong_adjustment': p.adjustment = 'forward'
    if mutation == 'wrong_currency': p.currency = 'USD'
    if mutation == 'bad_period': p.actual_start = p.actual_end
    if mutation == 'bad_observations': p.observations.reverse()
    if mutation == 'bad_raw_ohlc':
        src = p.sources[0]; payload = json.loads(src.raw_json); payload['data']['item'][0]['high_price'] = '1'; resign(src, payload)
    if mutation == 'wrong_input_order': ev.input_evidence_ids.reverse()
    if mutation == 'missing_input': ev.input_evidence_ids[0] = 'foreign-ref'
    if mutation == 'invalid_number': ev.value = m.value = 'NaN'
    if mutation == 'request_mismatch': p.requested_end = '2025-10-18'
    answer = build_answer(r)
    assert answer.answer_status == 'unavailable'
    assert answer.supporting_evidence_ids == []
    assert '不能确认' in answer.direct_answer
    assert '%（上涨）' not in answer.direct_answer
    assert '无法解释价格变化原因' in answer.direct_answer
    assert answer.missing_evidence


def test_matching_endpoints_does_not_prove_complete_coverage():
    r = report(QUESTIONS[0][0], bars=[bar(str(START), '100'), bar(str(END), '110')])
    answer = build_answer(r)
    assert answer.scope.price_requested_start == answer.scope.price_observed_start
    assert answer.scope.price_requested_end == answer.scope.price_observed_end
    assert answer.answer_status == 'partial'
    assert any(g.code == 'trading_calendar_unverified' for g in answer.missing_evidence)


@pytest.mark.parametrize('mutation', ['value','basis','period','missing_input'])
def test_margin_requires_same_period_consolidated_evidence(mutation):
    r = report(QUESTIONS[2][0]); m, ev = metric_evidence(r, 'net_profit_margin')
    if mutation == 'value': ev.value = m.value = '1000'
    if mutation == 'basis': r.diagnosis.sources[0].reporting_basis = 'parent_only'
    if mutation == 'period': ev.period_end = '2023-12-31'
    if mutation == 'missing_input': ev.input_evidence_ids = []
    answer = build_answer(r)
    assert answer.answer_status == 'unavailable'
    assert not answer.supporting_evidence_ids
    assert '没有可核验' in answer.direct_answer


@pytest.mark.parametrize('question,status', [('评估估值水平还缺少哪些证据？','answered'),('当前估值合理吗？','unavailable')])
def test_valuation_gap_inventory_is_not_an_actual_valuation(question, status):
    answer = build_answer(report(question))
    assert answer.answer_status == status
    assert '估值判断仍未完成' in answer.direct_answer
    assert not answer.supporting_evidence_ids
    assert 'valuation_input_chain' in {g.code for g in answer.missing_evidence}


@pytest.mark.parametrize('diagnosis_status,mode', list(product(['complete','partial','unavailable'], ['llm','deterministic'])))
def test_answer_state_is_not_copied_from_diagnosis_or_model(diagnosis_status, mode):
    r = report(QUESTIONS[1][0]); r.diagnosis.status = diagnosis_status; r.interpretation_mode = mode
    assert build_answer(r).answer_status == 'answered'
    r = report(QUESTIONS[4][0]); r.diagnosis.status = diagnosis_status; r.interpretation_mode = mode
    assert build_answer(r).answer_status == 'unavailable'


@pytest.mark.parametrize('mutation', ['plan','source_parameters','raw_stock','foreign_metric','foreign_price_leaf'])
def test_cross_stock_references_are_rejected(mutation):
    r = report(QUESTIONS[1][0] if mutation != 'foreign_price_leaf' else QUESTIONS[0][0])
    if mutation == 'plan': r.plan.stock_code = '002594.SZ'
    if mutation == 'source_parameters': r.diagnosis.sources[0].parameters['thscode'] = '002594.SZ'
    if mutation == 'raw_stock':
        src = r.diagnosis.sources[0]; payload = json.loads(src.raw_json); payload['data']['item'][0]['thscode'] = '002594.SZ'; resign(src,payload)
    if mutation == 'foreign_metric':
        foreign = report(QUESTIONS[1][0], '002594.SZ')
        r.diagnosis.sources += foreign.diagnosis.sources
        r.diagnosis.evidence += foreign.diagnosis.evidence
        r.diagnosis.metrics[0] = foreign.diagnosis.metrics[0]
    if mutation == 'foreign_price_leaf':
        src = r.price_analysis.sources[0]; payload = json.loads(src.raw_json); payload['data']['thscode'] = '002594.SZ'; resign(src,payload)
    with pytest.raises(DiagnosisError) as exc: build_answer(r)
    assert exc.value.code == 'stock_mismatch'


@pytest.mark.parametrize('question', ['请分析新闻', '预测未来股价', '净利润率如何，可以买吗？'])
def test_unsupported_and_existing_safety_bypass(question):
    answer = build_answer(report(question))
    assert answer.intent_id == 'unsupported'
    assert answer.answer_status == 'unavailable'
    assert not answer.supporting_evidence_ids
    assert '不提供价格预测、买卖建议或收益保证' in answer.direct_answer


def test_multiple_intents_do_not_claim_the_whole_question_answered():
    answer = build_answer(report('营业收入和净利润增长有何差异，净利润率能说明什么？'))
    assert answer.intent_id == 'growth_comparison'
    assert answer.answer_status == 'partial'
    assert any(g.code == 'secondary_margin_meaning' for g in answer.missing_evidence)


@pytest.mark.parametrize('code', CODES)
def test_research_endpoint_adds_optional_answer_and_keeps_old_fields(code):
    fake = Mock(); fake.annual_income_statements.side_effect = financial
    app.dependency_overrides[get_fuyao_client] = lambda: fake
    response = TestClient(app).post('/api/research',json={'stock_code':code,'question':QUESTIONS[1][0]})
    assert response.status_code == 200
    body = response.json()
    assert Answer.model_validate(body['answer']).answer_status == 'answered'
    legacy = {k:v for k,v in body.items() if k != 'answer'}
    assert ResearchReport.model_validate(legacy).answer is None
    assert {'findings','observations','interpretations','follow_up_questions','follow_up_suggestions','diagnosis'} <= set(body)
    assert body['interpretation_mode'] == 'deterministic'
    assert fake.annual_income_statements.call_args.args[0] == code
    assert ResearchReport.model_fields['answer'].default is None


@pytest.mark.parametrize('revenue,profit', [('1e70','1e69'), ('100.000000000001','20.000000000001')])
def test_large_and_tiny_decimal_comparisons_do_not_use_float(revenue, profit):
    r = report(QUESTIONS[1][0], revenue=revenue, profit=profit)
    answer = build_answer(r)
    assert answer.answer_status == 'answered'
    assert '两者相差' in answer.direct_answer
    assert_refs(r, answer)
    if revenue.startswith('100.'):
        assert '大小关系按未舍入值判断' in answer.direct_answer


@pytest.mark.parametrize('entity', ['source_id','evidence_id'])
def test_duplicate_graph_identifiers_rejected(entity):
    r = report(QUESTIONS[1][0])
    if entity == 'source_id': r.diagnosis.sources.append(r.diagnosis.sources[0])
    else: r.diagnosis.evidence.append(r.diagnosis.evidence[0])
    with pytest.raises(DiagnosisError) as exc: build_answer(r)
    assert exc.value.code == 'invalid_answer_evidence'


def test_future_financial_period_not_used_as_an_annual_fact():
    data = financial('600519.SH', years=(2090,2089))
    r = factual_report(ResearchRequest(question=QUESTIONS[1][0]), build_diagnosis('600519.SH', data))
    answer = build_answer(r)
    assert answer.answer_status == 'unavailable'
    assert not answer.supporting_evidence_ids
    assert any(g.code == 'future_reporting_period' for g in answer.missing_evidence)


def test_model_mode_cannot_change_or_replace_built_answer(monkeypatch):
    from backend.app.llm import add_interpretation
    from backend.app.followups import add_followups
    r = report(QUESTIONS[1][0]); r.answer = build_answer(r)
    expected = r.answer.model_dump_json()
    monkeypatch.setenv('LLM_API_KEY','synthetic-key'); monkeypatch.setenv('LLM_MODEL','synthetic-model')
    import requests
    monkeypatch.setattr(requests,'post',Mock(side_effect=requests.Timeout()))
    add_followups(add_interpretation(r))
    assert r.interpretation_mode == 'deterministic'
    assert r.answer.model_dump_json() == expected
    assert r.answer.answer_status == 'answered'


@pytest.mark.parametrize('code,case', list(product(CODES, QUESTIONS)))
def test_real_endpoint_path_for_all_intents_without_live_requests(code, case, monkeypatch):
    from backend.app.fuyao import SourceResponse
    from backend.app.prices import price_parameters
    question, intent = case
    fake = Mock(); fake.annual_income_statements.side_effect = financial
    def daily(stock_code, start, end):
        payload = {'code':0,'data':{'thscode':stock_code,'interval':'1d','adjust':'none','item':[
            {'date_ms':price_parameters(stock_code,start,end)['start'],'open_price':'100','close_price':'100','high_price':'120','low_price':'90'},
            {'date_ms':price_parameters(stock_code,end,end)['start'],'open_price':'100','close_price':'110','high_price':'120','low_price':'90'}]}}
        return SourceResponse('https://fuyao.aicubes.cn/api/a-share/prices/historical',price_parameters(stock_code,start,end),datetime.now(timezone.utc),json.dumps(payload),payload)
    fake.historical_prices.side_effect = daily
    app.dependency_overrides[get_fuyao_client] = lambda: fake
    network = Mock(side_effect=AssertionError('No network in regression tests'))
    monkeypatch.setattr('requests.get',network); monkeypatch.setattr('requests.post',network)
    response = TestClient(app).post('/api/research',json={'stock_code':code,'question':question})
    assert response.status_code == 200
    body = response.json()
    assert body['answer']['intent_id'] == intent
    assert body['answer']['scope']['stock_code'] == code
    assert body['follow_up_mode'] == 'deterministic'
    if intent in ('price_performance','price_causality'):
        assert body['answer']['answer_status'] == 'partial'
        assert body['answer']['supporting_evidence_ids']
        fake.historical_prices.assert_called_once()
    else:
        fake.historical_prices.assert_not_called()
    network.assert_not_called()


def test_existing_hard_financial_api_failure_preserves_http_contract():
    fake = Mock(); fake.annual_income_statements.side_effect = DiagnosisError('upstream_rate_limited','Rate limited',429)
    app.dependency_overrides[get_fuyao_client] = lambda: fake
    response = TestClient(app).post('/api/research',json={'question':QUESTIONS[1][0]})
    assert response.status_code == 429
    assert response.json()['error']['code'] == 'upstream_rate_limited'
    assert 'answer' not in response.json()
