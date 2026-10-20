"""Regression coverage for bounded interpretation wording, using synthetic financials."""
import json
from unittest.mock import Mock

import pytest
import requests

from backend.app.llm import add_interpretation, validate_selection
from backend.app.research import Interpretation, interpretation_catalog
from backend.tests.test_backend import row
from backend.tests.test_research import report


@pytest.mark.parametrize('revenue,profit,relation', [
    ('120', '30', 'higher than'), ('150', '22', 'lower than'), ('120', '24', 'equal to'),
    ('80', '10', 'lower than'), ('80', '24', 'higher than'), ('100', '20', 'equal to'),
])
def test_comparison_replaces_overlapping_growth_interpretations(revenue, profit, relation):
    result = report([row(2024, revenue, profit), row(2023, '100', '20')])
    catalog = interpretation_catalog(result)
    comparison = next(c for c in catalog if c.id == 'interpret_growth_comparison')
    assert f'is {relation} revenue growth' in comparison.text
    metrics = {m.name: m for m in result.diagnosis.metrics}
    assert comparison.evidence_ids == [metrics['revenue_growth'].evidence_id, metrics['net_profit_growth'].evidence_id]
    assert len(set(comparison.evidence_ids)) == 2
    assert not {c.id for c in catalog} & {'interpret_revenue_growth', 'interpret_net_profit_growth', 'interpret_divergence'}
    content = json.dumps({'interpretations': [dict(id=c.id, evidence_ids=c.evidence_ids) for c in catalog]})
    assert validate_selection(content, catalog, result) == catalog


@pytest.mark.parametrize('mutation', ['missing_profit', 'missing_year', 'different_period', 'unavailable_evidence', 'wrong_value', 'wrong_unit', 'missing_input'])
def test_comparison_requires_verified_compatible_metrics(mutation):
    result = report([row(2024, '120', None), row(2023, '100', '20')]) if mutation == 'missing_profit' else report()
    profit = next(m for m in result.diagnosis.metrics if m.name == 'net_profit_growth')
    ev = next(e for e in result.diagnosis.evidence if e.evidence_id == profit.evidence_id)
    if mutation == 'missing_year':
        result = report([row(2024)])
    elif mutation == 'different_period':
        ev.reporting_period = '2023 FY vs 2022 FY'
    elif mutation == 'unavailable_evidence':
        ev.status = 'unavailable'
    elif mutation == 'wrong_value':
        ev.value = '999'
    elif mutation == 'wrong_unit':
        ev.unit = 'CNY yuan'
    elif mutation == 'missing_input':
        ev.input_evidence_ids = ['unknown', 'other']
    assert 'interpret_growth_comparison' not in {c.id for c in interpretation_catalog(result)}


def test_profitability_only_question_does_not_gain_irrelevant_growth_comparison():
    assert 'interpret_growth_comparison' not in {c.id for c in interpretation_catalog(report(question='净利润率如何'))}


@pytest.mark.parametrize('second', [
    'The annual comparison shows expansion in this measure. It does not establish persistence, the underlying cause, or investment attractiveness.',
    'THE ANNUAL COMPARISON SHOWS EXPANSION IN THIS MEASURE! It does not establish persistence, the underlying cause, or investment attractiveness.',
    'The annual comparison shows expansion in this metric. It does not establish persistence, the underlying cause, or investment attractiveness.',
])
def test_different_ids_cannot_bypass_duplicate_or_near_duplicate_guard(second):
    result = report()
    refs = [m.evidence_id for m in result.diagnosis.metrics[:2]]
    catalog = [Interpretation(id='a', text='The annual comparison shows expansion in this measure. It does not establish persistence, the underlying cause, or investment attractiveness.', evidence_ids=[refs[0]]),
               Interpretation(id='b', text=second, evidence_ids=[refs[1]])]
    content = json.dumps({'interpretations': [dict(id=c.id, evidence_ids=c.evidence_ids) for c in catalog]})
    with pytest.raises(ValueError, match='Repeated interpretation'):
        validate_selection(content, catalog, result)


def test_combined_comparison_citations_cannot_be_dropped_reordered_or_invented():
    result = report()
    candidate = next(c for c in interpretation_catalog(result) if c.id == 'interpret_growth_comparison')
    for refs in ([candidate.evidence_ids[0]], list(reversed(candidate.evidence_ids)), ['invented']):
        with pytest.raises(ValueError):
            validate_selection(json.dumps({'interpretations': [{'id': candidate.id, 'evidence_ids': refs}]}), [candidate], result)


def test_gemini_cannot_select_retired_generic_growth_ids(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'synthetic-key')
    monkeypatch.setenv('LLM_MODEL', 'synthetic-model')
    result = report()
    observation_ids = [o.evidence_ids for o in result.observations]
    revenue = next(m for m in result.diagnosis.metrics if m.name == 'revenue_growth')
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'interpretations': [{'id': 'interpret_revenue_growth', 'evidence_ids': [revenue.evidence_id]}]})}}]}
    monkeypatch.setattr(requests, 'post', Mock(return_value=response))
    result = add_interpretation(result)
    assert result.interpretation_mode == 'deterministic'
    assert not result.interpretations
    assert [o.evidence_ids for o in result.observations] == observation_ids
