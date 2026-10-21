"""Offline intent and schema tests only; no final answers or financial facts are generated."""
import json
from datetime import date
from itertools import product
from typing import get_args
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from backend.app.answer_contract import Answer, AnswerScope, IntentId, MissingEvidence
from backend.app.errors import DiagnosisError
from backend.app.intents import INTENT_CATALOG, identify_intent
from backend.app.research import ResearchReport, make_plan
from backend.app.stocks import STOCKS

CODES = [stock.stock_code for stock in STOCKS]
QUESTIONS = [
    ('过去一个月的股价表现如何？', 'price_performance'),
    ('营业收入与净利润的同比增长表现有何差异？', 'growth_comparison'),
    ('净利润率能说明什么？', 'margin_meaning'),
    ('评估估值水平还缺少哪些证据？', 'valuation_evidence_gap'),
    ('经营现金流能否支持账面利润？', 'cashflow_support'),
    ('为什么最近股价上涨？', 'price_causality'),
    ('研发投入和产能利用情况如何？', 'manufacturing_evidence_gap'),
]


@pytest.mark.parametrize('code,case', list(product(CODES, QUESTIONS)))
def test_seven_audit_questions_for_three_stocks(code, case, monkeypatch):
    question, expected = case
    get, post = Mock(), Mock()
    monkeypatch.setattr('requests.get', get)
    monkeypatch.setattr('requests.post', post)
    result = identify_intent(question, code)
    assert result.intent_id == expected
    assert result.stock_code == code
    assert not result.secondary_intent_ids
    assert result.unverified_premises == (['price_increase'] if expected == 'price_causality' else [])
    assert 'answer_status' not in result.model_dump()
    assert 'direct_answer' not in result.model_dump()
    get.assert_not_called()
    post.assert_not_called()


@pytest.mark.parametrize('question,primary,secondary', [
    ('营收与净利润增长有何差异，净利润率能说明什么？', 'growth_comparison', ['margin_meaning']),
    ('净利润率能说明什么，过去一个月股价表现如何？', 'margin_meaning', ['price_performance']),
    ('估值还缺哪些证据，营收与净利润增长有何差异？', 'valuation_evidence_gap', ['growth_comparison']),
    ('现金流能否支持利润，估值还缺哪些证据？', 'cashflow_support', ['valuation_evidence_gap']),
    ('研发和产能情况如何，同时比较营收和净利润增长？', 'manufacturing_evidence_gap', ['growth_comparison']),
    ('为什么最近股价上涨，现金流能否支持利润？', 'price_causality', ['cashflow_support']),
    ('过去一个月股价表现如何，为什么上涨？', 'price_causality', ['price_performance']),
    ('净利润率和净利率能说明什么？', 'margin_meaning', []),
    ('营收增长如何，净利润率能说明什么？', 'margin_meaning', []),
])
def test_multi_intent_priority_and_no_background_as_primary(question, primary, secondary):
    result = identify_intent(question, '300750.SZ')
    assert result.intent_id == primary
    assert result.secondary_intent_ids == secondary
    assert len(result.secondary_intent_ids) == len(set(result.secondary_intent_ids))


@pytest.mark.parametrize('code', CODES)
def test_company_defaults_do_not_inject_user_intents(code):
    assert identify_intent('净利润率能说明什么？', code).intent_id == 'margin_meaning'
    assert identify_intent('净利润率能说明什么？', code).secondary_intent_ids == []
    assert identify_intent('请介绍这家公司', code).intent_id == 'unsupported'
    # The existing dimension router remains unchanged and separate from this contract.
    if code != '600519.SH':
        assert 'manufacturing' in [d.id for d in make_plan('净利润率能说明什么？', code).dimensions]


@pytest.mark.parametrize('question,intent', [
    ('How did the stock price perform?', 'price_performance'),
    ('Compare revenue and net profit growth', 'growth_comparison'),
    ('What does net profit margin mean?', 'margin_meaning'),
    ('What evidence is missing for valuation?', 'valuation_evidence_gap'),
    ('Can operating cash flow support profits?', 'cashflow_support'),
    ('Why did the stock price rise?', 'price_causality'),
    ('R&D and capacity utilization?', 'manufacturing_evidence_gap'),
    ('新闻如何？', 'unsupported'), ('毛利率如何？', 'unsupported'),
    ('明天股价会涨多少？', 'unsupported'), ('预测未来股价', 'unsupported'),
    ('保证收益，应该买入吗？', 'unsupported'),
    ('净利润率是多少，应该买入吗？', 'unsupported'),
])
def test_finite_catalog_and_unsupported_requests(question, intent):
    assert identify_intent(question).intent_id == intent


@pytest.mark.parametrize('question,premise', [
    ('为什么最近股价上涨？', ['price_increase']),
    ('为什么股价下跌？', ['price_decrease']),
    ('Why did the stock price fall?', ['price_decrease']),
    ('为什么股价没有上涨？', ['price_movement']),
    ('最近股价上涨了多少？', ['price_increase']),
    ('过去一个月的股价表现如何？', []),
])
def test_price_direction_is_only_an_unverified_user_premise(question, premise):
    result = identify_intent(question)
    assert result.unverified_premises == premise
    assert not {'verified_direction', 'price_return', 'answer_status'} & set(result.model_dump())


@pytest.mark.parametrize('question', ['', '   ', 'x' * 1001, None, 123])
def test_invalid_questions_rejected(question):
    with pytest.raises(ValueError):
        identify_intent(question)


def test_catalog_is_exact_and_missing_dimensions_never_substitute_financial_metrics():
    assert {d.id for d in INTENT_CATALOG} == set(get_args(IntentId))
    assert len(INTENT_CATALOG) == 8
    expected = {'cashflow_support': 'operating_cashflow', 'manufacturing_evidence_gap': 'verified_capacity_disclosure',
                'valuation_evidence_gap': 'verified_valuation_input_chain', 'price_causality': 'verified_causal_evidence'}
    for intent, evidence in expected.items():
        definition = next(d for d in INTENT_CATALOG if d.id == intent)
        assert evidence in definition.required_evidence
        assert not {'revenue_growth', 'net_profit_margin'} & set(definition.required_evidence)


@pytest.mark.parametrize('code', ['000001.SZ', 'BAD', '300750.sz'])
def test_unsupported_stock_rejected(code):
    with pytest.raises(DiagnosisError):
        identify_intent('净利润率能说明什么？', code)
    with pytest.raises(ValidationError):
        AnswerScope(stock_code=code)


def answer_payload(status='unavailable', intent='cashflow_support'):
    # Placeholder text verifies a schema; it is not a generated company answer.
    return dict(intent_id=intent, answer_status=status, direct_answer='Synthetic contract text',
                supporting_evidence_ids=[], missing_evidence=[dict(code='synthetic_gap', description='Synthetic missing evidence', reason='not_supported')],
                scope=dict(stock_code='600519.SH'))


@pytest.mark.parametrize('diagnosis_status,interpretation_mode,answer_status', list(product(
    ['complete', 'partial', 'unavailable'], ['llm', 'deterministic'], ['answered', 'partial', 'unavailable'])))
def test_answer_state_independent_of_financial_and_ai_state(diagnosis_status, interpretation_mode, answer_status):
    # Envelope states deliberately have no role in Answer validation or status assignment.
    envelope = dict(diagnosis_status=diagnosis_status, interpretation_mode=interpretation_mode)
    result = Answer.model_validate(answer_payload(answer_status, 'valuation_evidence_gap'))
    assert result.answer_status == answer_status
    assert envelope == dict(diagnosis_status=diagnosis_status, interpretation_mode=interpretation_mode)
    assert not {'diagnosis_status', 'interpretation_mode'} & set(result.model_dump())


def test_gap_inventory_can_be_answered_while_financial_inputs_remain_missing():
    result = Answer.model_validate(answer_payload('answered', 'valuation_evidence_gap'))
    assert result.missing_evidence and result.supporting_evidence_ids == []


@pytest.mark.parametrize('status', ['partial', 'unavailable'])
def test_incomplete_answer_requires_explicit_gap(status):
    payload = answer_payload(status)
    payload['missing_evidence'] = []
    with pytest.raises(ValidationError): Answer.model_validate(payload)


@pytest.mark.parametrize('field,value', [('intent_id','fake'), ('answer_status','complete'), ('direct_answer','  '),
                                        ('supporting_evidence_ids',['a','a']), ('supporting_evidence_ids',[' '])])
def test_invalid_contract_fields_rejected(field, value):
    payload = answer_payload(); payload[field] = value
    with pytest.raises(ValidationError): Answer.model_validate(payload)


def test_contract_forbids_extra_claim_fields_and_fake_gap_source_ids():
    payload = answer_payload(); payload['price_prediction'] = 'synthetic'
    with pytest.raises(ValidationError): Answer.model_validate(payload)
    with pytest.raises(ValidationError):
        MissingEvidence(code='gap', description='Missing source', reason='unverified', evidence_id='invented')


@pytest.mark.parametrize('scope', [
    {'price_requested_start':'2025-10-01'},
    {'price_requested_start':'2025-10-02','price_requested_end':'2025-10-01'},
    {'price_observed_end':'2025-10-01'},
    {'price_requested_start':'2025-10-01','price_requested_end':'2025-10-10','price_observed_start':'2025-09-30','price_observed_end':'2025-10-05'},
    {'time_zone':'Australia/Sydney'},
])
def test_scope_rejects_ambiguous_or_invalid_intervals(scope):
    with pytest.raises(ValidationError): AnswerScope(stock_code='600519.SH', **scope)


def test_scope_keeps_reporting_periods_distinct_and_does_not_infer_coverage():
    scope = AnswerScope(stock_code='002594.SZ', reporting_periods=['2024 FY vs 2023 FY'],
                        price_requested_start='2025-10-01', price_requested_end='2025-10-10',
                        price_observed_start='2025-10-01', price_observed_end='2025-10-10')
    assert scope.price_observed_end == date(2025, 10, 10)
    assert scope.reporting_periods == ['2024 FY vs 2023 FY']
    assert scope.time_zone == 'Asia/Shanghai'
    assert 'coverage' not in scope.model_dump()


def test_serialization_defaults_and_old_api_contract_remain_unchanged():
    first, second = Answer.model_validate(answer_payload()), Answer.model_validate(answer_payload())
    first.supporting_evidence_ids.append('synthetic-ref')
    assert second.supporting_evidence_ids == []
    assert json.loads(second.model_dump_json())['scope']['stock_code'] == '600519.SH'
    assert set(Answer.model_fields) == {'intent_id','answer_status','direct_answer','supporting_evidence_ids','missing_evidence','scope'}
    assert ResearchReport.model_fields['answer'].default is None
    assert 'answer' not in ResearchReport.model_json_schema().get('required', [])
