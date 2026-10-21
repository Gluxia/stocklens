"""Curated research scope, not automatic industry identification or market search."""
from pydantic import BaseModel

from .errors import DiagnosisError


class Stock(BaseModel):
    stock_code: str
    name: str
    exchange: str
    company_type: str
    classification_basis: str
    source: str
    source_url: str
    identity_source_url: str = 'https://fuyao.aicubes.cn/docs/api-reference/ticker-search/'
    default_dimensions: list[str]


STOCKS = (
    Stock(stock_code='600519.SH', name='贵州茅台', exchange='上海证券交易所', company_type='白酒消费企业',
          classification_basis='主营茅台酒及茅台酱香系列酒的生产与销售。',
          source='贵州茅台公司简介', source_url='https://www.moutai.com.cn/mtgf/qygk/gsjj/index.html',
          default_dimensions=['growth', 'profitability']),
    Stock(stock_code='300750.SZ', name='宁德时代', exchange='深圳证券交易所', company_type='电池与储能制造企业',
          classification_basis='主要从事动力电池与储能业务。',
          source='宁德时代企业简介', source_url='https://www.catl.com/about/profile/',
          default_dimensions=['growth', 'profitability', 'manufacturing']),
    Stock(stock_code='002594.SZ', name='比亚迪', exchange='深圳证券交易所', company_type='汽车及多元制造企业',
          classification_basis='业务涵盖整车、电池及其他制造领域。',
          source='比亚迪公司简介', source_url='https://www.bydglobal.com/cn/about',
          default_dimensions=['profitability', 'growth', 'manufacturing']),
)


def get_stock(stock_code: str) -> Stock:
    stock = next((s for s in STOCKS if s.stock_code == stock_code), None)
    if stock is None:
        raise DiagnosisError('unsupported_stock', 'The stock is outside the three-stock research whitelist.', 422)
    return stock


def verify_source_stock(stock_code, response):
    if response.parameters.get('thscode') != stock_code:
        raise DiagnosisError('stock_mismatch', 'Source request stock does not match research stock.')
