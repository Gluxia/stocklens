"""Only safe categorical diagnostics may leave the provider boundary."""
import itertools
import json
from unittest.mock import Mock

import pytest
import requests

from backend.app.llm import add_interpretation, validate_selection
from backend.app.research import Interpretation, attach_prices, interpretation_catalog
from backend.tests.test_prices import build
from backend.tests.test_research import report


@pytest.mark.parametrize('mode,reason', [
    ('timeout', 'timeout'), ('quota', 'provider_rate_limited_or_quota'),
    ('http', 'provider_http_error'), ('connection', 'provider_connection_error'),
    ('malformed', 'invalid_selection_json'), ('shape', 'malformed_provider_output'),
    ('duplicate', 'duplicate_interpretation_id'), ('reference', 'invalid_evidence_references'),
    ('unknown', 'unsupported_interpretation_id'), ('refused', 'incomplete_or_refused_output'),
    ('near_duplicate', 'repeated_interpretation_wording'),
])
def test_safe_fallback_diagnostics(monkeypatch, caplog, mode, reason):
    monkeypatch.setenv('LLM_API_KEY', 'SECRET_KEY_SHOULD_NOT_BE_LOGGED')
    monkeypatch.setenv('LLM_MODEL', 'synthetic-model')
    monkeypatch.setenv('LLM_BASE_URL', 'https://example.test/v1')
    r = report(question='growth SENSITIVE_QUESTION')
    catalog = interpretation_catalog(r)
    candidate = catalog[0]
    selections = [{'id': candidate.id, 'evidence_ids': candidate.evidence_ids}]
    if mode == 'duplicate': selections *= 2
    if mode == 'reference': selections[0]['evidence_ids'] = ['SENSITIVE_REFERENCE']
    if mode == 'unknown': selections[0]['id'] = 'SENSITIVE_UNKNOWN_ID'
    if mode == 'near_duplicate':
        duplicate = Interpretation(id='other', text=candidate.text.replace('comparison', 'comparison '), evidence_ids=candidate.evidence_ids)
        monkeypatch.setattr('backend.app.llm.interpretation_catalog', lambda _: catalog + [duplicate])
        selections.append({'id': duplicate.id, 'evidence_ids': duplicate.evidence_ids})
    content = 'SENSITIVE_PROVIDER_BODY' if mode == 'malformed' else json.dumps({'interpretations':selections})
    response = Mock(status_code=429 if mode=='quota' else 503 if mode=='http' else 200)
    response.json.return_value = {'choices': [None]} if mode=='shape' else {'choices':[{'finish_reason':'length' if mode=='refused' else 'stop', 'message':{'content':content}}]}
    if mode in ('quota','http'):
        response.raise_for_status.side_effect = requests.HTTPError('SENSITIVE_PROVIDER_BODY')
    post = Mock(return_value=response)
    if mode=='timeout': post.side_effect = requests.Timeout('SENSITIVE_PROVIDER_BODY')
    if mode=='connection': post.side_effect = requests.ConnectionError('SENSITIVE_PROVIDER_BODY')
    monkeypatch.setattr(requests,'post',post)
    before = r.diagnosis.model_dump_json()
    with caplog.at_level('WARNING', logger='backend.app.llm'):
        result = add_interpretation(r)
    assert result.interpretation_mode=='deterministic' and not result.interpretations
    assert result.diagnosis.model_dump_json()==before
    assert f'reason={reason} ' in caplog.text
    for sensitive in ['SECRET_KEY_SHOULD_NOT_BE_LOGGED','SENSITIVE_PROVIDER_BODY','SENSITIVE_QUESTION','SENSITIVE_REFERENCE','SENSITIVE_UNKNOWN_ID']:
        assert sensitive not in caplog.text
    assert post.call_count==1


def test_all_valid_combined_catalog_selections_survive_deduplication():
    r = attach_prices(report(question='贵州茅台的经营表现与近期股价变化是否一致？'), build())
    catalog=interpretation_catalog(r)
    assert {c.id for c in catalog}=={'interpret_growth_comparison','interpret_price_return','interpret_margin'}
    for count in range(1,4):
        for selection in itertools.permutations(catalog,count):
            content=json.dumps({'interpretations':[{'id':c.id,'evidence_ids':c.evidence_ids} for c in selection]})
            assert validate_selection(content,catalog,r)==list(selection)


def test_configuration_diagnostics_do_not_print_secret_url(monkeypatch,caplog):
    monkeypatch.setenv('LLM_API_KEY','synthetic-secret')
    monkeypatch.setenv('LLM_MODEL','synthetic-model')
    monkeypatch.setenv('LLM_BASE_URL','https://user:SENSITIVE_PASSWORD@example.test/v1')
    post=Mock();monkeypatch.setattr(requests,'post',post)
    with caplog.at_level('WARNING',logger='backend.app.llm'):
        assert add_interpretation(report()).interpretation_mode=='deterministic'
    assert 'reason=invalid_configuration' in caplog.text
    assert 'SENSITIVE_PASSWORD' not in caplog.text
    post.assert_not_called()
