"""Three-stock research with synthetic fixtures only; no live provider calls."""
import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

from backend.app.main import app, get_fuyao_client
from backend.app.fuyao import FuyaoClient
from backend.app.errors import DiagnosisError
from backend.app.diagnosis import build_diagnosis
from backend.app.prices import build_prices, price_window, price_parameters
from backend.app.research import ResearchRequest, factual_report, attach_prices, make_plan, interpretation_catalog
from backend.app.llm import add_interpretation, validate_selection
from backend.app.stocks import STOCKS
from backend.tests.test_backend import row, source
from backend.tests.test_prices import bar, prices

CODES = [s.stock_code for s in STOCKS]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    yield
    app.dependency_overrides.clear()


def financial(code):
    response=source([row(2025, thscode=code), row(2024, '100', '20', thscode=code)])
    return replace(response, parameters={**response.parameters, 'thscode':code})


def daily(code, start, end):
    response=prices([bar(str(start),'100'),bar(str(end),'110')],thscode=code)
    return replace(response, parameters=price_parameters(code,start,end))


def test_public_catalog_is_provider_free_and_has_classification_sources(monkeypatch):
    get=Mock();monkeypatch.setattr(requests,'get',get)
    result=TestClient(app).get('/api/stocks')
    assert result.status_code==200
    assert [s['stock_code'] for s in result.json()]==CODES
    assert all(s['name'] and s['company_type'] and s['classification_basis'] and s['source_url'].startswith('https://') for s in result.json())
    get.assert_not_called()


@pytest.mark.parametrize('code', CODES)
def test_transport_parameters_are_stock_specific(monkeypatch,code):
    get=Mock(return_value=Mock(status_code=200,text='{"code":0,"data":{"item":[]}}'))
    monkeypatch.setattr(requests,'get',get)
    client=FuyaoClient('synthetic-key');start,end=price_window()
    client.annual_income_statements(code)
    assert get.call_args.kwargs['params']=={'thscode':code,'period':'annual','limit':4}
    client.historical_prices(code,start,end)
    assert get.call_args.kwargs['params']==price_parameters(code,start,end)


@pytest.mark.parametrize('code', CODES)
def test_full_research_and_followup_keep_stock_and_source_identity(code):
    fake=Mock();fake.annual_income_statements.side_effect=financial;fake.historical_prices.side_effect=daily
    app.dependency_overrides[get_fuyao_client]=lambda:fake
    client=TestClient(app)
    for question in ['营收与利润增长如何？','过去一个月股价表现如何？']:
        response=client.post('/api/research',json={'stock_code':code,'question':question})
        assert response.status_code==200
        body=response.json()
        assert body['plan']['stock_code']==body['diagnosis']['stock_code']==code
        assert body['plan']['company_name']==next(s.name for s in STOCKS if s.stock_code==code)
        assert len(body['diagnosis']['metrics'])==3
        src=body['diagnosis']['sources']+(body['price_analysis']['sources'] if body['price_analysis'] else [])
        assert all(s['parameters']['thscode']==code for s in src)
        assert body['interpretation_mode']=='deterministic'
        if body['price_analysis']:
            assert len(body['price_analysis']['observations'])==2
            assert body['follow_up_questions'][0]=='过去一个月的股价表现如何？'
    followup=client.post('/api/research',json={'stock_code':code,'question':body['follow_up_questions'][0]})
    assert followup.status_code==200 and followup.json()['diagnosis']['stock_code']==code
    assert all(call.args[0]==code for call in fake.annual_income_statements.call_args_list)
    assert all(call.args[0]==code for call in fake.historical_prices.call_args_list)
    diagnosis=client.get('/api/diagnosis',params={'stock_code':code})
    assert diagnosis.status_code==200 and diagnosis.json()['stock_code']==code


@pytest.mark.parametrize('code',CODES)
def test_company_type_defaults_and_explicit_question_priority(code):
    plan=make_plan('请研究这家公司',code)
    stock=next(s for s in STOCKS if s.stock_code==code)
    assert [d.id for d in plan.dimensions]==stock.default_dimensions
    assert plan.company_type==stock.company_type
    price=make_plan('近期股价走势如何？',code)
    assert price.dimensions[0].id=='price'
    manufacturing=make_plan('研发与产能如何？',code)
    assert next(d for d in manufacturing.dimensions if d.id=='manufacturing').availability=='unavailable'
    r=factual_report(ResearchRequest(stock_code=code,question='研发与产能如何？'),build_diagnosis(code,financial(code)))
    missing=next(f for f in r.findings if f.id=='missing_manufacturing')
    assert missing.kind=='limitation' and not missing.evidence_ids
    assert {m.name for m in r.diagnosis.metrics}=={'revenue_growth','net_profit_growth','net_profit_margin'}


def test_type_policies_have_distinct_defaults():
    assert len({tuple(d.id for d in make_plan('研究公司',code).dimensions) for code in CODES})==3


@pytest.mark.parametrize('code',CODES)
def test_cross_stock_records_and_parameter_mismatch_are_rejected(code):
    other=next(c for c in CODES if c!=code)
    with pytest.raises(DiagnosisError,match='stock'):
        build_diagnosis(code,financial(other))
    forged=replace(financial(other),parameters={**financial(other).parameters,'thscode':code})
    with pytest.raises(DiagnosisError,match='stock'):
        build_diagnosis(code,forged)
    start,end=price_window()
    with pytest.raises(DiagnosisError):build_prices(code,daily(other,start,end),start,end)
    forged_price=replace(daily(other,start,end),parameters=price_parameters(code,start,end))
    with pytest.raises(DiagnosisError):build_prices(code,forged_price,start,end)


@pytest.mark.parametrize('code',CODES)
def test_gemini_selection_and_safety_use_current_stock(monkeypatch,code):
    r=factual_report(ResearchRequest(stock_code=code,question='营收利润增长'),build_diagnosis(code,financial(code)))
    catalog=interpretation_catalog(r)
    content=json.dumps({'interpretations':[{'id':c.id,'evidence_ids':c.evidence_ids} for c in catalog]})
    assert validate_selection(content,catalog,r)==catalog
    monkeypatch.setenv('LLM_API_KEY','synthetic-key');monkeypatch.setenv('LLM_MODEL','synthetic-model')
    post=Mock(side_effect=requests.Timeout());monkeypatch.setattr(requests,'post',post)
    assert add_interpretation(r).interpretation_mode=='deterministic'
    assert post.call_count==1
    sensitive=factual_report(ResearchRequest(stock_code=code,question='可以买入吗，保证收益？'),build_diagnosis(code,financial(code)))
    add_interpretation(sensitive);assert post.call_count==1
    r.diagnosis.sources[0].parameters['thscode']=next(c for c in CODES if c!=code)
    with pytest.raises(DiagnosisError):add_interpretation(r)
    assert post.call_count==1


@pytest.mark.parametrize('code',CODES)
def test_partial_failure_does_not_mix_stocks(code):
    fake=Mock();fake.annual_income_statements.side_effect=financial
    fake.historical_prices.side_effect=DiagnosisError('upstream_rate_limited','Rate limited',429)
    app.dependency_overrides[get_fuyao_client]=lambda:fake
    body=TestClient(app).post('/api/research',json={'stock_code':code,'question':'股价'}).json()
    assert body['diagnosis']['stock_code']==code
    assert body['price_analysis']['error_code']=='upstream_rate_limited'
    assert not body['price_analysis']['sources'] and not body['price_analysis']['evidence']


def test_unsupported_codes_rejected_before_provider_access():
    fake=Mock();app.dependency_overrides[get_fuyao_client]=lambda:fake
    for code in ['000001.SZ','BAD','300750.sz','300750.SZ,002594.SZ']:
        for path in ['/api/plan','/api/research']:
            assert TestClient(app).post(path,json={'stock_code':code,'question':'增长'}).status_code==422
    fake.annual_income_statements.assert_not_called()
    fake.historical_prices.assert_not_called()


@pytest.mark.parametrize('code',CODES)
def test_foreign_financial_data_is_not_sent_to_ai_and_prices_stay_current(monkeypatch,code):
    other=next(c for c in CODES if c!=code)
    fake=Mock();fake.annual_income_statements.return_value=financial(other)
    fake.historical_prices.side_effect=daily
    app.dependency_overrides[get_fuyao_client]=lambda:fake
    post=Mock();monkeypatch.setattr(requests,'post',post)
    client=TestClient(app)
    response=client.post('/api/research',json={'stock_code':code,'question':'营收利润'})
    assert response.status_code==502 and response.json()['error']['code']=='stock_mismatch'
    body=client.post('/api/research',json={'stock_code':code,'question':'股价'}).json()
    assert body['diagnosis']['status']=='unavailable' and not body['diagnosis']['sources']
    assert all(s['parameters']['thscode']==code for s in body['price_analysis']['sources'])
    assert body['price_analysis']['observations']
    post.assert_not_called()


def test_evidence_ids_are_unique_across_stock_reports():
    reports=[build_diagnosis(code,financial(code)) for code in CODES]
    all_ids=[e.evidence_id for r in reports for e in r.evidence]
    assert len(all_ids)==len(set(all_ids))


def test_classification_uses_verified_business_sources_without_development_copy():
    expected = {
        '600519.SH': ('白酒消费企业', 'https://www.moutai.com.cn/mtgf/qygk/gsjj/index.html'),
        '300750.SZ': ('电池与储能制造企业', 'https://www.catl.com/about/profile/'),
        '002594.SZ': ('汽车及多元制造企业', 'https://www.bydglobal.com/cn/about'),
    }
    for stock in STOCKS:
        assert (stock.company_type, stock.source_url) == expected[stock.stock_code]
        assert '人工审阅' in stock.classification_basis
        assert '非自动行业识别' in stock.classification_basis
        assert 'MVP' not in stock.classification_basis + stock.source
        plan = make_plan('请研究这家公司', stock.stock_code)
        assert plan.classification_source_url == stock.source_url
        assert plan.company_type_basis == stock.classification_basis
