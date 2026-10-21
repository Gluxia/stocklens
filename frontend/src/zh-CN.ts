/** Presentation-only localization. Provider records and API objects stay untouched. */
import Decimal from 'decimal.js'
import { formatMetric, labels, reasonText, type Finding, type Plan, type ResearchReport } from './api'

export const dimensionLabels: Record<string, string> = { growth: '成长能力', profitability: '盈利能力', valuation: '估值水平', price: '股价表现', manufacturing: '制造业专属证据（待验证）', quality: '盈利质量与财务韧性', data_quality: '数据质量' }
export const safetyNotice = '本问题涉及投资操作或收益确定性。StockLens 仅提供基于证据的研究信息，不提供买卖建议，也不承诺收益。'
export const disclaimer = '本报告仅提供研究信息，不构成买卖建议，不承诺收益。年度财务数据不能反映当前交易状况。'
export const sourceName = (name: string) => name === 'Fuyao' ? 'Fuyao（扶摇）' : '数据来源待核验'
export const unitText = (unit: string | null) => unit === 'observations' ? '条' : unit === 'CNY yuan' ? '人民币元（CNY）' : unit ?? '未提供'
export function periodText(period: string) {
  if (period === 'unknown') return '报告期未知'
  return period.replace(/(\d{4}) FY/g, '$1 年度').replace(' vs ', ' 对比 ')
}
export function dimensionReason(item: Plan['dimensions'][number]) {
  if (item.reason.startsWith('公司类型默认关注：') || item.reason.startsWith('公司类型补充关注：')) return item.reason.replace(/growth/g, '成长能力').replace(/profitability/g, '盈利能力').replace(/manufacturing/g, '制造业专属证据（待验证）')
  if (item.reason === 'No specific supported dimension matched; the default annual operating-performance review was selected.') return '未匹配到特定研究维度，默认从成长能力与盈利能力了解年度经营表现。'
  if (item.reason === 'Included as annual financial context alongside historical prices; no causal link is established.') return '作为年度财务背景，与历史价格分别观察；不据此推断财务事件与股价变化之间的因果关系。'
  if (item.reason === 'Included as available annual financial context; it cannot answer the requested unavailable dimension.') return '作为可获取的年度财务背景纳入研究，不能替代所问维度缺失的证据。'
  if (/^The question matched .+ keywords\.$/.test(item.reason)) return `问题中包含与${dimensionLabels[item.id] ?? '该维度'}相关的关键词，因此纳入研究。`
  return '该维度由后端研究计划选定；具体选择原因暂未提供经核验的中文说明。'
}
export function freshnessText(report: ResearchReport) {
  const year = report.diagnosis.current_year
  if (year === null) return '暂无可核验的年度报告期。'
  if (report.freshness_status === 'stale') return `最新返回的是 ${year} 年度数据，早于上一自然年度，可能缺少较新披露。请核实数据时效性。`
  if (report.freshness_status === 'unknown') return '返回的报告期可能尚未结束或晚于当前日期，请核验原始日期后再使用。'
  return `最新返回报告期为 ${year} 年度。获取时间不代表数据反映当前经营或股价；本次未核查更新的中期报告。`
}
export function findingCopy(item: Finding, report: ResearchReport): { title: string; text: string } {
  if (item.dimension === 'price') {
    const price = report.price_analysis
    if (item.id === 'price_coverage') return { title: '历史价格覆盖范围尚待核验', text: price?.status === 'unavailable' ? '未能取得有效历史价格，未生成图表或价格判断。请查看价格区块中的数据状态。' : '尚未核验完整交易日历。结果仅覆盖已返回的有效观测，不保证包含所有应有交易日；历史价格变化不能解释事件因果关系。' }
    const m = price?.metrics.find(m => m.name === item.id && item.evidence_ids.includes(m.evidence_id))
    if (m?.value !== null && m?.value !== undefined && m.status === 'available') {
      const title = ({ price_return: '观测区间价格涨跌幅', price_high: '观测区间最高价', price_low: '观测区间最低价', price_count: '有效交易观测数' } as Record<string, string>)[m.name] ?? '历史价格事实'
      const value = new Decimal(m.value).toFixed(m.name === 'price_count' ? 0 : 2)
      return { title, text: `${price?.actual_start} 至 ${price?.actual_end}，${title}为 ${value}${m.unit === '%' ? '%' : m.unit === 'observations' ? ' 条' : ' 元'}。不复权，仅描述历史观测，不代表投资建议。` }
    }
  }
  const metric = report.diagnosis.metrics.find(metric => metric.name === item.id && item.evidence_ids.includes(metric.evidence_id))
  if (metric && labels[metric.name]) {
    if (metric.status !== 'available' || metric.value === null) return { title: `${labels[metric.name]}暂不可用`, text: `尚不能形成可核验的指标结果：${reasonText(metric.reason)}。` }
    const evidence = report.diagnosis.evidence.find(ev => ev.evidence_id === metric.evidence_id)
    const direction = item.category === 'positive' ? '营业收入同比上升' : item.category === 'negative' ? '营业收入同比下降' : labels[metric.name]
    const title = item.category === 'positive' || item.category === 'negative' ? (metric.name === 'net_profit_growth' ? direction.replace('营业收入', '净利润') : direction) : labels[metric.name]
    return { title, text: `${evidence ? periodText(evidence.reporting_period) : '当前报告期'}，${labels[metric.name]}为 ${formatMetric(metric)}。${['positive', 'negative'].includes(item.category) ? '正负方向仅描述本次年度变化，不代表投资价值判断。' : ''}` }
  }
  if (item.id === 'missing_manufacturing') return { title: '制造业专属指标尚待验证', text: '当前仅提供合并报表通用指标。研发、产能、销量及订单等尚未形成可核验指标，不据此推断分部业绩或竞争优势。' }
  if (item.id === 'divergent_growth') return { title: '营业收入与净利润变化方向不一致', text: '两项年度增长指标呈现不同方向，需要结合观察；现有证据不足以解释差异的成因。' }
  if (item.id.startsWith('missing_') && dimensionLabels[item.dimension]) return { title: `${dimensionLabels[item.dimension]}尚未核验`, text: '当前版本尚未接入该维度的已核验数据，仅凭年度利润表无法回答相关问题。' }
  if (item.id === 'margin_context') return { title: '行业对比与长期表现尚未评估', text: '单一净利润率不足以判断竞争优势、估值或投资适合性；目前缺少同行基准与更长期的比较。' }
  if (item.id === 'freshness') return { title: '报告时效性有待核验', text: freshnessText(report) }
  return { title: '该项信息尚待核验', text: '此项内容暂未提供经核验的中文表述，请查看关联证据；本界面不补充未经支持的结论。' }
}

// Exact catalog matching avoids translating arbitrary generated claims as trusted analysis.
const interpretationTranslations: Record<string, string> = {
  'For the same annual comparison, net profit growth is higher than revenue growth. This comparison does not establish underlying causes, persistence, or investment attractiveness.': '在同一年度对比中，净利润同比增长率高于营业收入同比增长率。该比较不说明变化成因、变化能否持续或投资吸引力。',
  'For the same annual comparison, net profit growth is lower than revenue growth. This comparison does not establish underlying causes, persistence, or investment attractiveness.': '在同一年度对比中，净利润同比增长率低于营业收入同比增长率。该比较不说明变化成因、变化能否持续或投资吸引力。',
  'For the same annual comparison, net profit growth is equal to revenue growth. This comparison does not establish underlying causes, persistence, or investment attractiveness.': '在同一年度对比中，净利润同比增长率等于营业收入同比增长率。该比较不说明变化成因、变化能否持续或投资吸引力。',
  '区间收盘价变化仅描述已返回观测的历史价格表现，不包含分红收益；不能据此预测未来收益，也不能认定财务事件导致了股价变化。': '区间收盘价变化仅描述已返回观测的历史价格表现，不包含分红收益；不能据此预测未来收益，也不能认定财务事件导致了股价变化。',
  'The annual comparison shows expansion in this measure. It does not establish persistence, the underlying cause, or investment attractiveness.': '该指标在年度比较中上升，但现有证据不能说明增长能否持续、具体成因或投资吸引力。',
  'The annual comparison shows contraction in this measure. Additional evidence is needed to establish its cause or persistence.': '该指标在年度比较中下降，其成因及是否持续仍需更多证据核验。',
  'Revenue and profit signals should be considered together. Their divergence prevents a uniformly positive or negative reading of annual growth; causes remain unverified.': '营业收入与净利润应结合观察。两者变化方向不一致，不宜对年度增长作单一正面或负面判断；差异成因仍待核验。',
  'The reported margin describes consolidated accounting profitability. It does not establish cash generation or relative competitive strength without additional evidence.': '该净利润率反映合并报表口径下的会计盈利水平。缺少其他证据时，不能据此判断现金创造能力或相对竞争优势。',
}
export function interpretationText(text: string) { return interpretationTranslations[text] ?? '该项解读尚无经核验的中文版本，请查看关联证据。此处不展示未经支持的扩展结论。' }
const statuses: Record<string, string> = {
  'AI is not configured; displaying deterministic factual observations.': 'AI 解读未启用，当前展示基于确定性计算的客观事实摘要。',
  'Deterministic research only: requests for investment actions or guaranteed outcomes are not sent to the model.': '本问题涉及投资操作或收益承诺，未提交给模型，仅展示可核验的客观事实。',
  'Insufficient validated evidence for AI interpretation; displaying deterministic results.': '已核验证据不足以支持 AI 解读，当前仅展示确定性计算结果。',
  'AI configuration is invalid; displaying deterministic factual observations.': 'AI 配置暂不可用，已切换为客观事实摘要。',
  'AI unavailable or output failed evidence validation; displaying deterministic factual observations.': 'AI 暂不可用或输出未通过证据校验，已切换为客观事实摘要。',
  'AI selected and prioritized these interpretations from a Python-validated catalog. Wording and numerical facts are controlled by the backend.': 'AI 从通过后端校验的解读集合中选取并排序；数值与表述均受后端约束。',
}
export const interpretationStatus = (text: string) => statuses[text] ?? '解读状态暂未提供经核验的中文说明，请以客观事实与原始证据为准。'
const followUps: Record<string, string> = {
  '过去一个月的股价表现如何？': '过去一个月的股价表现如何？',
  'How did revenue and net profit growth compare?': '营业收入与净利润的同比增长表现有何差异？',
  'What does the reported net profit margin establish?': '已披露的净利润率能说明什么？',
  'What evidence is missing to assess valuation?': '评估估值水平还缺少哪些证据？',
  'Can the available statements establish cash-flow quality?': '现有财务报表能否说明现金流质量？',
}
export const followUpText = (text: string) => followUps[text] ?? null
export function metadataLabel(name: string) {
  const names: Record<string, string> = { thscode: '股票代码', fiscal_year: '财年', fiscal_period: '财务期间', period: '报告类型', currency: '币种', period_end_ms: '报告期末时间戳', report_date_ms: '披露时间戳' }
  return `${names[name] ?? '元数据'}路径（${name}）`
}
export const unitBasisText = (text: string) => text === 'A-share prices are CNY per the Fuyao prices contract.' ? '依据 Fuyao 行情接口通用约定，A 股价格以人民币元计价。' : ['Original-currency yuan, verified against the Fuyao financials contract.', 'Original currency yuan'].includes(text) ? '金额单位为原币元，依据 Fuyao 财务接口说明核验。' : '单位说明尚待核验，请对照原始响应与接口文档。'
