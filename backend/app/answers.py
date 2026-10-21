"""Deterministic primary answers over the current report's validated evidence only."""
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from zoneinfo import ZoneInfo

from .answer_contract import Answer, AnswerScope, MissingEvidence
from .diagnosis import calculate, number, validate_record
from .errors import DiagnosisError
from .fuyao import INCOME_ENDPOINT
from .intents import INTENT_CATALOG, identify_intent
from .research import ResearchReport, verify_report_stock
from .schemas import Evidence

PRICE_ENDPOINT = 'https://fuyao.aicubes.cn/api/a-share/prices/historical'
LEAF_PATH = re.compile(r'^\$\.data\.item\[(\d+)\]\.([a-z_]+)$')


class EvidenceProblem(Exception):
    def __init__(self, code='invalid_answer_evidence', reason='invalid'):
        self.code, self.reason = code, reason


def gap(code, description, reason='unverified'):
    return MissingEvidence(code=code, description=description, reason=reason)


def display(value):
    with localcontext() as ctx:
        ctx.rounding = ROUND_HALF_EVEN
        return format(value, '.2f')


@dataclass
class VerifiedMetric:
    value: Decimal
    evidence: Evidence
    inputs: list[Evidence]


def period_text(value):
    return value.replace(' FY vs ', ' 年度对比 ').replace(' FY', ' 年度')


class EvidenceReader:
    """Verify the selected metric graph without changing metrics, IDs or source records."""
    def __init__(self, report):
        verify_report_stock(report)
        self.report = report
        self.code = report.diagnosis.stock_code
        sources = report.diagnosis.sources + (report.price_analysis.sources if report.price_analysis else [])
        records = report.diagnosis.evidence + (report.price_analysis.evidence if report.price_analysis else [])
        self.sources = {s.source_id: s for s in sources}
        self.evidence = {e.evidence_id: e for e in records}
        if len(self.sources) != len(sources) or len(self.evidence) != len(records):
            raise DiagnosisError('invalid_answer_evidence', 'Ambiguous evidence or source IDs.')
        self.payloads = {}

    def source(self, ev):
        source = self.sources.get(ev.source_id)
        if (not source or source.endpoint != ev.endpoint or ev.retrieved_at != source.retrieved_at
                or ev.data_source != 'Fuyao' or source.retrieved_at.tzinfo is None):
            raise EvidenceProblem()
        if source.parameters.get('thscode') != self.code:
            raise DiagnosisError('stock_mismatch', 'Answer evidence belongs to another stock.')
        if source.source_id not in self.payloads:
            if hashlib.sha256(source.raw_json.encode()).hexdigest() != source.sha256:
                raise EvidenceProblem()
            try:
                payload = json.loads(source.raw_json, parse_float=Decimal)
                if type(payload['code']) is not int or payload['code'] != 0 or not isinstance(payload['data']['item'], list):
                    raise EvidenceProblem()
            except (ValueError, KeyError, TypeError):
                raise EvidenceProblem() from None
            self.payloads[source.source_id] = payload
        return source, self.payloads[source.source_id]

    def available(self, id):
        ev = self.evidence.get(id)
        if not ev or ev.status != 'available':
            reason = 'not_returned' if not ev or (ev.reason or '').startswith('missing') else 'invalid'
            raise EvidenceProblem('missing_answer_evidence', reason)
        value, error = number(ev.value)
        if error:
            raise EvidenceProblem()
        self.source(ev)
        return ev, value

    def leaf(self, id, field, endpoint):
        ev, value = self.available(id)
        source, payload = self.source(ev)
        path = LEAF_PATH.fullmatch(ev.json_path or '')
        if (ev.kind != 'source' or ev.input_evidence_ids or ev.endpoint != endpoint or
                ev.original_field_name != field or not path or path[2] != field or ev.unit != 'CNY yuan'):
            raise EvidenceProblem()
        try:
            row = payload['data']['item'][int(path[1])]
            raw_value, error = number(row[field])
            if error or value != raw_value:
                raise EvidenceProblem()
            if endpoint == INCOME_ENDPOINT:
                if source.reporting_basis != 'consolidated' or source.parameters.get('period') != 'annual':
                    raise EvidenceProblem('incompatible_reporting_basis')
                year, end = validate_record(row, self.code)
                if date.fromisoformat(end) > source.retrieved_at.astimezone(ZoneInfo('Asia/Shanghai')).date():
                    raise EvidenceProblem('future_reporting_period', 'period_mismatch')
                if ev.reporting_period != f'{year} FY' or ev.period_end != end:
                    raise EvidenceProblem('incompatible_reporting_period', 'period_mismatch')
            else:
                data = payload['data']
                if data.get('thscode') != self.code:
                    raise DiagnosisError('stock_mismatch', 'Answer price source belongs to another stock.')
                if (data.get('currency', 'CNY') != 'CNY' or data.get('interval') != '1d' or data.get('adjust') != 'none' or source.reporting_basis != 'daily_unadjusted'
                        or source.parameters.get('interval') != '1d' or source.parameters.get('adjust') != 'none'):
                    raise EvidenceProblem('incompatible_price_basis')
                if type(row['date_ms']) is not int:
                    raise EvidenceProblem()
                day = datetime.fromtimestamp(row['date_ms'] / 1000, ZoneInfo('Asia/Shanghai')).date().isoformat()
                values = [number(row.get(key))[0] for key in ('open_price', 'high_price', 'low_price', 'close_price')]
                if any(v is None or v <= 0 for v in values) or not values[2] <= min(values[0], values[3]) <= max(values[0], values[3]) <= values[1]:
                    raise EvidenceProblem('invalid_price_observation')
                if date.fromisoformat(day) >= source.retrieved_at.astimezone(ZoneInfo('Asia/Shanghai')).date():
                    raise EvidenceProblem('unfinished_price_observation', 'period_mismatch')
                if day != ev.period_end or day != ev.reporting_period or value <= 0:
                    raise EvidenceProblem('incompatible_price_period', 'period_mismatch')
        except DiagnosisError as exc:
            if exc.code == 'stock_mismatch':
                raise
            raise EvidenceProblem('invalid_financial_source', 'invalid') from None
        except (KeyError, IndexError, TypeError, ValueError, OverflowError, OSError):
            raise EvidenceProblem() from None
        return ev, value

    def metric(self, name):
        price = name == 'price_return'
        owner = self.report.price_analysis if price else self.report.diagnosis
        items = [m for m in owner.metrics if m.name == name] if owner else []
        if not items or items[0].status != 'available' or items[0].value is None:
            error = self.report.price_analysis.error_code if price and self.report.price_analysis else None
            reason = 'not_returned'
            if error:
                reason = 'provider_failure' if error.startswith('upstream_') or error == 'missing_api_key' else 'invalid'
            elif items and items[0].reason in ('invalid_number', 'zero_denominator', 'negative_growth_baseline', 'nonpositive_revenue'):
                reason = 'invalid'
            raise EvidenceProblem(name + '_unavailable', reason)
        if len(items) != 1:
            raise EvidenceProblem()
        metric = items[0]
        ev, value = self.available(metric.evidence_id)
        parsed, error = number(metric.value)
        if (error or parsed != value or metric.unit != '%' or ev.unit != '%' or ev.kind != 'calculation'
                or len(ev.input_evidence_ids) != 2 or len(set(ev.input_evidence_ids)) != 2):
            raise EvidenceProblem()
        if price:
            fields, formula = ('close_price', 'close_price'), '(end_close / start_close - 1) * 100'
        elif name == 'net_profit_margin':
            fields, formula = ('net_profit', 'operating_income'), 'net_profit / operating_income * 100'
        else:
            fields = ('operating_income',) * 2 if name == 'revenue_growth' else ('net_profit',) * 2
            formula = '(current - previous) / previous * 100'
        if ev.formula != formula:
            raise EvidenceProblem()
        inputs = [self.leaf(id, field, PRICE_ENDPOINT if price else INCOME_ENDPOINT) for id, field in zip(ev.input_evidence_ids, fields)]
        if any(item.source_id != ev.source_id for item, _ in inputs):
            raise EvidenceProblem('incompatible_source_snapshot')
        expected, error = calculate(inputs[0][1], inputs[1][1], growth=name != 'net_profit_margin')
        if error or expected != value:
            raise EvidenceProblem()
        if price:
            self.price_period(ev, inputs)
        else:
            current = self.report.diagnosis.current_year
            previous = self.report.diagnosis.previous_year
            growth = name != 'net_profit_margin'
            if current is None or (growth and (previous is None or previous != current - 1)):
                raise EvidenceProblem('incompatible_reporting_period', 'period_mismatch')
            expected_period = f'{current} FY vs {previous} FY' if growth else f'{current} FY'
            if (ev.reporting_period != expected_period or ev.period_end != f'{current}-12-31'
                    or inputs[0][0].period_end != ev.period_end
                    or inputs[1][0].period_end != f'{previous if growth else current}-12-31'):
                raise EvidenceProblem('incompatible_reporting_period', 'period_mismatch')
        return VerifiedMetric(value, ev, [item for item, _ in inputs])

    def price_period(self, ev, inputs):
        from .prices import price_parameters
        p = self.report.price_analysis
        if p.interval != '1d' or p.adjustment != 'none' or p.currency != 'CNY':
            raise EvidenceProblem('incompatible_price_basis')
        try:
            start, end = date.fromisoformat(p.requested_start), date.fromisoformat(p.requested_end)
            actual_start, actual_end = date.fromisoformat(p.actual_start), date.fromisoformat(p.actual_end)
            if not start <= actual_start < actual_end <= end:
                raise EvidenceProblem('incompatible_price_period', 'period_mismatch')
            source = self.sources[ev.source_id]
            if any(source.parameters.get(k) != v for k, v in price_parameters(self.code, start, end).items()):
                raise EvidenceProblem('incompatible_price_period', 'period_mismatch')
            if (inputs[0][0].period_end != p.actual_end or inputs[1][0].period_end != p.actual_start
                    or ev.reporting_period != f'{p.actual_start} ~ {p.actual_end}' or ev.period_end != p.actual_end):
                raise EvidenceProblem('incompatible_price_period', 'period_mismatch')
            observations = p.observations
            days = [o.date for o in observations]
            if len(days) < 2 or days != sorted(set(days)) or days[0] != p.actual_start or days[-1] != p.actual_end:
                raise EvidenceProblem()
            for observation, (leaf, value) in zip((observations[-1], observations[0]), inputs):
                if leaf.evidence_id not in observation.evidence_ids or number(observation.close)[0] != value:
                    raise EvidenceProblem()
        except (ValueError, TypeError):
            raise EvidenceProblem('incompatible_price_period', 'period_mismatch') from None


def build_answer(report: ResearchReport) -> Answer:
    reader = EvidenceReader(report)
    selected = identify_intent(report.question, report.diagnosis.stock_code)
    intent = 'unsupported' if report.plan.safety_notice else selected.intent_id
    refs, periods, missing = [], [], []
    scope = AnswerScope(stock_code=report.diagnosis.stock_code)
    status = 'unavailable'

    def read(name, label):
        try:
            result = reader.metric(name)
            refs.append(result.evidence.evidence_id)
            periods.append(result.evidence.reporting_period)
            return result
        except EvidenceProblem as exc:
            missing.append(gap(exc.code, label + '缺少有效且口径、期间及输入引用一致的证据。', exc.reason))
            return None

    if intent == 'growth_comparison':
        revenue, profit = read('revenue_growth', '营业收入同比增长率'), read('net_profit_growth', '净利润同比增长率')
        if revenue and profit:
            a, b = revenue.evidence, profit.evidence
            if (a.reporting_period, a.period_end, a.source_id) != (b.reporting_period, b.period_end, b.source_id):
                missing.append(gap('incompatible_growth_comparison', '两项增长率必须来自同期间、同口径及同一来源快照。', 'period_mismatch'))
                text = '两项增长率各自存在，但期间或来源口径不可比，不能比较大小或计算百分点差异。'
                status = 'partial'
            else:
                with localcontext() as ctx:
                    ctx.prec = 240
                    difference = profit.value - revenue.value
                relation = '高于' if difference > 0 else '低于' if difference < 0 else '等于'
                text = f'{period_text(a.reporting_period)}，营业收入同比增长率为 {display(revenue.value)}%，净利润同比增长率为 {display(profit.value)}%；净利润增长率{relation}营业收入增长率，两者相差 {display(difference.copy_abs())} 个百分点。该比较不说明差异成因或增长能否持续。'
                if difference and difference.copy_abs() < Decimal('.005'):
                    text += '数值和百分点差异保留两位小数，大小关系按未舍入值判断。'
                status = 'answered'
        else:
            facts = []
            for item, label in ((revenue, '营业收入'), (profit, '净利润')):
                if item:
                    facts.append(f'{period_text(item.evidence.reporting_period)}，{label}同比增长率为 {display(item.value)}%')
            text = ('；'.join(facts) + '。' if facts else '') + '缺少同期间且有效的两项增长率，暂不能比较大小或计算百分点差异。'
            status = 'partial' if facts else 'unavailable'
    elif intent == 'margin_meaning':
        margin = read('net_profit_margin', '净利润率')
        if margin:
            text = f'{period_text(margin.evidence.reporting_period)}，合并口径净利润率为 {display(margin.value)}%。它是净利润占营业收入的比例，描述该年度的会计盈利水平；不能单独推断经营现金流、竞争优势或当前经营状况。'
            status = 'answered'
        else:
            text = '净利润率表示净利润占营业收入的比例，但当前没有可核验的该公司数值与报告期，不能给出实际盈利水平判断，也不能据此推断现金流或竞争优势。'
    elif intent in ('price_performance', 'price_causality'):
        scope.assumptions.append('使用现有默认近一个自然月请求窗口；实际观测区间与财务年度报告期分别标注，不解析其他时间范围。')
        p = report.price_analysis
        if p:
            try:
                start, end = date.fromisoformat(p.requested_start), date.fromisoformat(p.requested_end)
                if start <= end:
                    scope.price_requested_start, scope.price_requested_end = start, end
            except (ValueError, TypeError):
                pass
        price = read('price_return', '区间价格涨跌幅')
        if price:
            scope.price_observed_start, scope.price_observed_end = date.fromisoformat(p.actual_start), date.fromisoformat(p.actual_end)
            direction = '上涨' if price.value > 0 else '下跌' if price.value < 0 else '持平'
            text = f'实际有效观测区间为 {p.actual_start} 至 {p.actual_end}（北京时间），首尾收盘价变化为 {display(price.value)}%（{direction}），采用不复权口径，不含分红收益。'
            if price.value and price.value.copy_abs() < Decimal('.005'):
                text += '显示值保留两位小数，方向按原始精度判断。'
            missing.append(gap('trading_calendar_unverified', '尚未逐日核验交易日历及缺失观测，不能确认请求区间完整覆盖。'))
            text += '尚未核验完整交易日历，结果仅描述已返回的有效观测。'
            status = 'partial'
        else:
            text = '当前没有可核验的区间价格涨跌幅，不能确认所述区间上涨、下跌或持平。'
        if intent == 'price_causality':
            if price and 'price_increase' in selected.unverified_premises and price.value <= 0:
                text += '该观测区间未显示上涨，不能把问题中的上涨前提当成已验证事实，也不能据此判断其他未指定区间。'
            elif price and 'price_decrease' in selected.unverified_premises and price.value >= 0:
                text += '该观测区间未显示下跌，不能把问题中的下跌前提当成已验证事实。'
            text += '缺少经核验的事件与因果证据，无法解释价格变化原因；近期价格和年度财报不能单独建立因果关系。'
            missing.append(gap('price_causal_evidence', '缺少与价格区间对应且能支持因果判断的事件及研究证据。', 'not_supported'))
    elif intent == 'valuation_evidence_gap':
        text = '当前尚未建立完整的估值证据链：需要核验同一时点的价格与股本或市值、与估值方法匹配的盈利或净资产基础，以及比较基准。已有经营指标或历史股价不能单独替代这些组合证据，估值判断仍未完成。'
        missing.extend([gap('valuation_input_chain', '同一时点价格、股本或市值与适用财务基础的已验证组合。', 'not_supported'),
                        gap('valuation_benchmark', '适用估值方法、比较基准及期间口径。', 'not_supported')])
        inventory = any(word in report.question.casefold() for word in ('缺', '补充', '需要哪些', '需要什么', 'missing', 'what evidence', 'what data', 'which data', 'evidence gap'))
        status = 'answered' if inventory else 'unavailable'
    elif intent == 'cashflow_support':
        text = '目前没有经核验的经营活动现金流及与账面利润可比的期间和口径，无法判断现金流是否支持账面利润。营业收入、净利润增长或净利润率不能替代这一判断。'
        missing.extend([gap('operating_cashflow', '同期经营活动现金流及其报表来源。', 'not_supported'),
                        gap('cashflow_profit_comparability', '现金流与利润的期间和口径可比性。')])
    elif intent == 'manufacturing_evidence_gap':
        text = '研发投入和产能利用指标尚未核验，当前无法判断其规模或变化。年度合并营业收入与净利润不能替代研发、产能或具体业务分部的证据。'
        missing.extend([gap('rd_disclosure', '研发投入及费用化、资本化口径的已验证披露。', 'not_supported'),
                        gap('capacity_disclosure', '具体业务的产能、实际产量及利用率口径。', 'not_supported')])
    else:
        text = '当前支持历史股价表现、年度营收与净利润增长比较、净利润率含义及相关证据缺口说明。该问题不在当前可回答范围内，不提供价格预测、买卖建议或收益保证。'
        missing.append(gap('unsupported_question', '当前审核意图目录未支持该研究任务。', 'not_supported'))
    scope.reporting_periods = list(dict.fromkeys(periods)) if intent not in ('price_performance', 'price_causality') else []
    if intent != 'unsupported':
        for secondary in selected.secondary_intent_ids:
            if secondary == 'price_performance' and intent == 'price_causality' and refs:
                continue
            label = next(item.label for item in INTENT_CATALOG if item.id == secondary)
            missing.append(gap('secondary_' + secondary, f'已识别的附加意图“{label}”尚未在本答案中展开。'))
            if status == 'answered':
                status = 'partial'
    return Answer(intent_id=intent, answer_status=status, direct_answer=text,
                  supporting_evidence_ids=list(dict.fromkeys(refs)), missing_evidence=missing, scope=scope)
