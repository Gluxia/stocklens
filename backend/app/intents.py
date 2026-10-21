"""Finite, deterministic user intent recognition; no financial claims or answer generation."""
import re
import unicodedata
from dataclasses import dataclass

from pydantic import Field

from .answer_contract import ContractModel, IntentId
from .stocks import get_stock


@dataclass(frozen=True)
class IntentDefinition:
    id: IntentId
    label: str
    required_evidence: tuple[str, ...]


# Priority reflects the explicit task, not the company profile or available background metrics.
INTENT_CATALOG = (
    IntentDefinition('price_causality', '股价原因核验', ('price_observations', 'verified_causal_evidence')),
    IntentDefinition('cashflow_support', '现金流对利润的支持', ('operating_cashflow', 'comparable_profit')),
    IntentDefinition('manufacturing_evidence_gap', '研发与产能证据缺口', ('verified_rd_disclosure', 'verified_capacity_disclosure')),
    IntentDefinition('valuation_evidence_gap', '估值证据缺口', ('verified_valuation_input_chain',)),
    IntentDefinition('growth_comparison', '营收与净利润增长比较', ('revenue_growth', 'net_profit_growth', 'matching_annual_periods')),
    IntentDefinition('margin_meaning', '净利润率含义', ('net_profit_margin', 'consolidated_reporting_basis')),
    IntentDefinition('price_performance', '历史股价表现', ('price_observations', 'price_return', 'observed_period')),
    IntentDefinition('unsupported', '未支持的研究意图', ()),
)


class IntentSelection(ContractModel):
    stock_code: str
    intent_id: IntentId
    secondary_intent_ids: list[IntentId] = Field(default_factory=list)
    # These are user premises to check later, never verified facts or price directions.
    unverified_premises: list[str] = Field(default_factory=list)


def identify_intent(question: str, stock_code: str = '600519.SH') -> IntentSelection:
    get_stock(stock_code)
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ValueError('A research question must contain 1 to 1000 characters')
    text = unicodedata.normalize('NFKC', question).casefold().strip()
    has = lambda words: any(word in text for word in words)
    matched = set()
    price = has(('股价', '价格', '走势', '行情', '涨跌', 'price', 'stock performance'))
    if price:
        matched.add('price_performance')
        if has(('为什么', '为何', '原因', '导致', 'why', 'cause', 'driven', 'driving')):
            matched.add('price_causality')
            if not has(('表现', '涨跌幅', '涨幅', '走势', 'performance', 'return', 'trend')):
                matched.discard('price_performance')
    if has(('现金流', '现金创造', 'cashflow', 'cash flow', 'cash-flow')):
        matched.add('cashflow_support')
    if has(('研发', '产能', 'r&d', 'research and development', 'capacity')):
        matched.add('manufacturing_evidence_gap')
    if has(('估值', '市盈率', '市净率', 'valuation', 'p/e', 'p/b')):
        matched.add('valuation_evidence_gap')
    revenue = has(('营收', '收入', 'revenue', 'sales'))
    profit_text = text
    for term in ('净利润率', '净利率', 'net profit margin', 'net margin', 'profit margin'):
        profit_text = profit_text.replace(term, '')
    profit = any(term in profit_text for term in ('净利润', '净利', '利润', '盈利', 'profit', 'earnings'))
    comparison = has(('增长', '同比', '增速', '差异', '区别', '比较', '同步', '快', 'growth', 'compare', 'comparison', 'differ', 'versus', ' vs '))
    if revenue and profit and comparison:
        matched.add('growth_comparison')
    if has(('净利润率', '净利率', 'net profit margin', 'net margin', 'profit margin')):
        matched.add('margin_meaning')
    ordered = [item.id for item in INTENT_CATALOG if item.id in matched]
    # Forecast/action requests are outside this finite research catalog; existing compliance stays separate.
    excluded_task = has(('买入', '卖出', '荐股', '保证收益', '稳赚', '目标价', 'should i buy', 'should i sell', 'guarantee', 'recommend a stock'))
    forecast = price and has(('预测', '明天', '未来', 'forecast', 'predict', 'tomorrow', 'next week'))
    if excluded_task or forecast:
        ordered = ['unsupported'] + ordered
    if not ordered:
        ordered = ['unsupported']
    premises = []
    if price:
        if has(('上涨', '上涨了', '大涨', '涨了')) and not has(('没有上涨', '未上涨', '不涨')):
            premises.append('price_increase')
        elif has(('下跌', '大跌', '跌了')) and not has(('没有下跌', '未下跌', '不跌')):
            premises.append('price_decrease')
        elif re.search(r'\b(rise|rising|rose|increase|increased|up)\b', text):
            premises.append('price_increase')
        elif re.search(r'\b(fall|falling|fell|decline|decreased|down)\b', text):
            premises.append('price_decrease')
        elif 'price_causality' in matched:
            premises.append('price_movement')
    return IntentSelection(stock_code=stock_code, intent_id=ordered[0],
        secondary_intent_ids=ordered[1:], unverified_premises=premises)
