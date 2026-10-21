import { z } from 'zod'
import Decimal from 'decimal.js'

const numeric = z.string().refine(value => {
  try { return new Decimal(value).isFinite() } catch { return false }
}, '无效的十进制数值')
export const stockCodeSchema = z.enum(['600519.SH', '300750.SZ', '002594.SZ'])
export type StockCode = z.infer<typeof stockCodeSchema>
export const stockSchema = z.object({ stock_code: stockCodeSchema, name: z.string(), exchange: z.string(), company_type: z.string(), classification_basis: z.string(), source: z.string(), source_url: z.string().url(), identity_source_url: z.string().url(), default_dimensions: z.array(z.string()) })
export type Stock = z.infer<typeof stockSchema>
const status = z.enum(['available', 'unavailable'])
const evidenceSchema = z.object({
  evidence_id: z.string(), kind: z.enum(['source', 'calculation']), source_id: z.string(),
  data_source: z.string(), endpoint: z.string(), original_field_name: z.string().nullable(),
  json_path: z.string().nullable(), reporting_period: z.string(), period_end: z.string(),
  value: numeric.nullable(), unit: z.string().nullable(), formula: z.string().nullable(),
  input_evidence_ids: z.array(z.string()), retrieved_at: z.string().datetime({ offset: true }),
  status, reason: z.string().nullable(), metadata_json_paths: z.record(z.string(), z.string()),
})
export const diagnosisSchema = z.object({
  stock_code: stockCodeSchema, status: z.enum(['complete', 'partial', 'unavailable']),
  current_year: z.number().int().nullable(), previous_year: z.number().int().nullable(),
  calculation_version: z.string(), decimal_precision: z.number(), rounding: z.string(),
  issues: z.array(z.string()),
  metrics: z.array(z.object({ name: z.string(), value: numeric.nullable(), unit: z.string(), status, reason: z.string().nullable(), evidence_id: z.string() })),
  evidence: z.array(evidenceSchema),
  sources: z.array(z.object({ source_id: z.string(), endpoint: z.string(), parameters: z.record(z.string(), z.unknown()), retrieved_at: z.string().datetime({ offset: true }), sha256: z.string(), raw_json: z.string(), contract_url: z.string(), reporting_basis: z.string(), unit_basis: z.string() })),
})
export type Diagnosis = z.infer<typeof diagnosisSchema>
export type Evidence = z.infer<typeof evidenceSchema>
export type Metric = Diagnosis['metrics'][number]

export async function fetchDiagnosis(signal?: AbortSignal, stockCode: StockCode = '600519.SH'): Promise<Diagnosis> {
  const response = await fetch(`/api/diagnosis?stock_code=${encodeURIComponent(stockCode)}`, { signal, headers: { Accept: 'application/json' } })
  let body: unknown
  try { body = await response.json() } catch { throw new Error('服务响应无法解析，请确认后端服务已启动。') }
  if (!response.ok) {
    const error = z.object({ error: z.object({ code: z.string(), message: z.string() }) }).safeParse(body)
    throw new Error(error.success ? apiErrorText(error.data.error.code, response.status) : `研究请求未完成（HTTP ${response.status}），请检查后端服务后重试。`)
  }
  const parsed = diagnosisSchema.safeParse(body)
  if (!parsed.success) throw new Error('响应未通过财务证据格式校验，本次未展示结果。')
  if (parsed.data.stock_code !== stockCode || parsed.data.sources.some(s => s.parameters.thscode !== stockCode)) throw new Error('响应股票身份不匹配，本次未展示结果。')
  return parsed.data
}
export const labels: Record<string, string> = { revenue_growth: '营业收入同比增长率', net_profit_growth: '净利润同比增长率', net_profit_margin: '净利润率' }
export function formatMetric(metric: Metric) {
  if (metric.status !== 'available' || metric.value === null) return '暂不可用'
  return `${new Decimal(metric.value).toFixed(2)}${metric.unit === '%' ? '%' : ` ${metric.unit}`}`
}
export function formatDate(value: string) {
  return `${new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(new Date(value))}（北京时间）`
}
const reasons: Record<string, string> = {
  missing_value: '原始字段缺失', invalid_number: '原始数值无效', missing_or_invalid_input: '计算所需数据缺失或无效',
  zero_denominator: '分母为零，无法计算', negative_growth_baseline: '上年基数为负，不适用常规同比增长率',
  nonpositive_revenue: '营业收入非正，无法计算该净利润率', no_financial_data: '未获取到财务数据',
  missing_previous_year: '缺少相邻上一年度数据',
}
export function reasonText(value: string | null): string {
  if (!value) return '证据不足'
  if (reasons[value]) return reasons[value]
  const missingYear = /^missing_previous_year: (\d{4})$/.exec(value)
  if (missingYear) return `缺少 ${missingYear[1]} 年度数据`
  const fieldIssue = /^(\d{4})\.(operating_income|net_profit): (.+)$/.exec(value)
  if (fieldIssue) return `${fieldIssue[1]} 年度${fieldIssue[2] === 'operating_income' ? '营业收入' : '净利润'}：${reasonText(fieldIssue[3])}`
  const metricIssue = /^(revenue_growth|net_profit_growth|net_profit_margin): (.+)$/.exec(value)
  if (metricIssue) return `${labels[metricIssue[1]]}：${reasonText(metricIssue[2])}`
  return '数据异常或说明尚待核验，请查看原始证据'
}
const errorMessages: Record<string, string> = {
  missing_api_key: '后端尚未配置 Fuyao API 密钥，请检查服务配置。', upstream_timeout: 'Fuyao 数据请求超时，请稍后重试。',
  upstream_rate_limited: 'Fuyao 请求频率或额度已达限制，请稍后重试或检查额度。', upstream_http_error: '暂时无法获取 Fuyao 数据，请检查服务连接后重试。',
  upstream_api_error: 'Fuyao 返回业务错误，本次未生成研究结果。', invalid_json: '数据源响应无法解析，本次未展示财务结果。',
  invalid_response: '数据源响应格式异常，本次未展示财务结果。', invalid_record: '数据源记录无效，请核验原始数据。',
  invalid_reporting_period: '报告期信息未通过核验，本次未进行比较。', stock_mismatch: '数据源股票代码与所选股票不一致。',
  unverified_unit: '数据单位或币种尚未通过核验，本次未展示计算结果。', duplicate_reporting_period: '存在重复报告期，无法确定适用记录。',
  invalid_stock_code: '股票代码格式无效，请使用 600519.SH。', unsupported_stock: '当前支持贵州茅台、宁德时代和比亚迪，请选择其中一家公司。',
}
export const apiErrorText = (code: string, status: number) => errorMessages[code] ?? `研究请求未完成（HTTP ${status}），请稍后重试。`
export function requestErrorText(failure: unknown) {
  if (failure instanceof Error && /[\u3400-\u9fff]/.test(failure.message)) return failure.message
  return '无法连接研究服务，请检查网络及后端服务后重试。'
}

export function classify(report: Diagnosis) {
  // Only a change relative to a positive prior-year baseline is classified.
  const eligible = report.metrics.filter(metric => {
    const ev = report.evidence.find(e => e.evidence_id === metric.evidence_id)
    return ['revenue_growth', 'net_profit_growth'].includes(metric.name) && metric.unit === '%' && metric.status === 'available' && metric.value !== null && ev?.status === 'available' && ev.kind === 'calculation' && ev.value === metric.value && ev.input_evidence_ids.length === 2 && ev.input_evidence_ids.every(id => report.evidence.some(input => input.evidence_id === id && input.kind === 'source' && input.status === 'available'))
  })
  return {
    positive: eligible.filter(m => new Decimal(m.value!).gt(0)),
    negative: eligible.filter(m => new Decimal(m.value!).lt(0)),
    unknown: report.metrics.filter(m => m.status !== 'available' || m.value === null),
  }
}

export const planSchema = z.object({
  stock_code: stockCodeSchema, classification_source: z.string(), classification_source_url: z.string().url(),
  company_name: z.string(), company_type: z.string(), company_type_basis: z.string(), routing_method: z.string(),
  safety_notice: z.string().nullable(),
  dimensions: z.array(z.object({ id: z.string(), label: z.string(), reason: z.string(), availability: z.enum(['available', 'unavailable']) })),
})
const findingSchema = z.object({ id: z.string(), category: z.enum(['positive', 'negative', 'mixed', 'unknown']), kind: z.enum(['observation', 'limitation']), title: z.string(), text: z.string(), evidence_ids: z.array(z.string()), dimension: z.string() })
export const priceSchema = z.object({
  status: z.enum(['partial', 'unavailable']), requested_start: z.string(), requested_end: z.string(),
  actual_start: z.string().nullable(), actual_end: z.string().nullable(), currency: z.literal('CNY'),
  adjustment: z.literal('none'), interval: z.literal('1d'), coverage: z.literal('unverified'),
  retrieved_at: z.string().datetime({ offset: true }).nullable(), error_code: z.string().nullable(), issues: z.array(z.string()),
  observations: z.array(z.object({ date: z.string(), close: numeric, high: numeric, low: numeric, evidence_ids: z.array(z.string()) })),
  metrics: diagnosisSchema.shape.metrics, evidence: diagnosisSchema.shape.evidence, sources: diagnosisSchema.shape.sources,
})
export type PriceAnalysis = z.infer<typeof priceSchema>
export const reportEvidence = (report: { diagnosis: Diagnosis; price_analysis?: PriceAnalysis | null }) => [...report.diagnosis.evidence, ...(report.price_analysis?.evidence ?? [])]
export const reportSources = (report: { diagnosis: Diagnosis; price_analysis?: PriceAnalysis | null }) => [...report.diagnosis.sources, ...(report.price_analysis?.sources ?? [])]
const nonblank = z.string().trim().min(1)
const date = z.iso.date()
export const answerSchema = z.strictObject({
  intent_id: z.enum(['price_performance', 'growth_comparison', 'margin_meaning', 'valuation_evidence_gap', 'cashflow_support', 'manufacturing_evidence_gap', 'price_causality', 'unsupported']),
  answer_status: z.enum(['answered', 'partial', 'unavailable']),
  direct_answer: nonblank,
  supporting_evidence_ids: z.array(nonblank).default([]),
  missing_evidence: z.array(z.strictObject({ code: nonblank, description: nonblank, reason: z.enum(['not_supported', 'not_returned', 'invalid', 'period_mismatch', 'unverified', 'provider_failure']) })).default([]),
  scope: z.strictObject({
    stock_code: stockCodeSchema, reporting_periods: z.array(nonblank).default([]),
    price_requested_start: date.nullable().default(null), price_requested_end: date.nullable().default(null),
    price_observed_start: date.nullable().default(null), price_observed_end: date.nullable().default(null),
    time_zone: z.literal('Asia/Shanghai').default('Asia/Shanghai'), assumptions: z.array(nonblank).default([]),
  }),
}).superRefine((answer, context) => {
  const scope = answer.scope
  const intervals = [[scope.price_requested_start, scope.price_requested_end], [scope.price_observed_start, scope.price_observed_end]]
  if (new Set(answer.supporting_evidence_ids).size !== answer.supporting_evidence_ids.length ||
      (answer.answer_status !== 'answered' && !answer.missing_evidence.length) ||
      intervals.some(([start, end]) => (start === null) !== (end === null) || (start !== null && end !== null && start > end)) ||
      (scope.price_requested_start && scope.price_observed_start && (scope.price_observed_start < scope.price_requested_start || scope.price_observed_end! > scope.price_requested_end!))) {
    context.addIssue({ code: 'custom', message: '主答案范围或缺口说明无效' })
  }
})
export type Answer = z.infer<typeof answerSchema>
export const researchSchema = z.object({
  question: z.string(), answer: answerSchema.nullable().optional(), plan: planSchema, diagnosis: diagnosisSchema, price_analysis: priceSchema.nullable().optional(),
  findings: z.array(findingSchema), observations: z.array(findingSchema),
  interpretation_mode: z.enum(['llm', 'deterministic']), interpretation_status: z.string(),
  interpretations: z.array(z.object({ id: z.string(), text: z.string(), evidence_ids: z.array(z.string()) })),
  freshness: z.string(), freshness_status: z.enum(['recent_annual_period', 'stale', 'unknown']),
  follow_up_suggestions: z.array(z.object({ id: z.string(), question: z.string(), dimension: z.string(), availability: z.enum(['supported', 'pending']), stock_code: stockCodeSchema, evidence_ids: z.array(z.string()), reporting_periods: z.array(z.string()) })).max(4).optional(),
  follow_up_mode: z.enum(['llm', 'deterministic']).optional(),
  follow_up_questions: z.array(z.string()), disclaimer: z.string(),
}).superRefine((report, context) => {
  const evidence = reportEvidence(report)
  const sources = reportSources(report)
  const metrics = [...report.diagnosis.metrics, ...(report.price_analysis?.metrics ?? [])]
  const ids = new Set(evidence.map(e => e.evidence_id))
  const sourceIds = new Set(sources.map(s => s.source_id))
  if (report.answer) {
    const byId = new Map(evidence.map(item => [item.evidence_id, item]))
    // Validate the entire input chain, including availability and stock ownership.
    const valid = (id: string, ancestors = new Set<string>()): boolean => {
      const item = byId.get(id)
      if (!item || ancestors.has(id) || item.status !== 'available' || item.value === null) return false
      const source = sources.find(source => source.source_id === item.source_id)
      if (!source || source.parameters.thscode !== report.diagnosis.stock_code || source.endpoint !== item.endpoint || source.retrieved_at !== item.retrieved_at) return false
      return item.input_evidence_ids.every(input => valid(input, new Set([...ancestors, id])))
    }
    if (report.answer.scope.stock_code !== report.diagnosis.stock_code || report.answer.supporting_evidence_ids.some(id => !valid(id))) {
      context.addIssue({ code: 'custom', message: '主答案证据引用无效' })
    }
  }

  if (report.follow_up_suggestions?.some(s => s.stock_code !== report.diagnosis.stock_code || s.evidence_ids.some(id => !evidence.some(e => e.evidence_id === id && e.status === 'available'))) ||
      new Set(report.follow_up_suggestions?.map(s => s.id)).size !== (report.follow_up_suggestions?.length ?? 0) ||
      report.plan.stock_code !== report.diagnosis.stock_code || sources.some(s => s.parameters.thscode !== report.diagnosis.stock_code) ||
      ids.size !== evidence.length || sourceIds.size !== sources.length ||
      metrics.some(m => !ids.has(m.evidence_id)) ||
      evidence.some(e => !sourceIds.has(e.source_id) || e.input_evidence_ids.some(id => !ids.has(id))) ||
      (report.price_analysis?.observations.some(o => o.evidence_ids.some(id => !ids.has(id))) ?? false) ||
      [...report.findings, ...report.observations, ...report.interpretations].some(f => f.evidence_ids.some(id => !ids.has(id)))) {
    context.addIssue({ code: 'custom', message: '证据引用无效' })
  }
})
export type Plan = z.infer<typeof planSchema>
export type ResearchReport = z.infer<typeof researchSchema>
export type Finding = z.infer<typeof findingSchema>

async function post<T>(path: string, question: string, schema: z.ZodType<T>, signal: AbortSignal, stockCode: StockCode): Promise<T> {
  const response = await fetch(path, { method: 'POST', signal, headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ stock_code: stockCode, question }) })
  let body: unknown
  try { body = await response.json() } catch { throw new Error('服务响应无法解析，请确认后端服务已启动。') }
  if (!response.ok) {
    const parsed = z.object({ error: z.object({ code: z.string(), message: z.string() }) }).safeParse(body)
    throw new Error(parsed.success ? apiErrorText(parsed.data.error.code, response.status) : `研究请求未完成（HTTP ${response.status}），请检查后端服务后重试。`)
  }
  const parsed = schema.safeParse(body)
  if (!parsed.success) throw new Error('响应未通过格式或证据引用校验，本次未展示财务报告。')
  return parsed.data
}
export async function fetchPlan(question: string, signal: AbortSignal, stockCode: StockCode = '600519.SH') {
  const plan = await post('/api/plan', question, planSchema, signal, stockCode)
  if (plan.stock_code !== stockCode) throw new Error('研究计划股票身份不匹配。')
  return plan
}
export async function fetchResearch(question: string, signal: AbortSignal, stockCode: StockCode = '600519.SH') {
  const report = await post('/api/research', question, researchSchema, signal, stockCode)
  if (report.diagnosis.stock_code !== stockCode) throw new Error('响应股票身份不匹配，本次未展示结果。')
  return report
}
export async function fetchStocks(signal: AbortSignal): Promise<Stock[]> {
  const response = await fetch('/api/stocks', { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error('股票目录暂不可用，请刷新页面重试。')
  const parsed = z.array(stockSchema).length(3).safeParse(await response.json())
  if (!parsed.success || new Set(parsed.data.map(s => s.stock_code)).size !== 3) throw new Error('股票目录校验失败。')
  return parsed.data
}
