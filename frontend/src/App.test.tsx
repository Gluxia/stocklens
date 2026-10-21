import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { researchSchema, type ResearchReport } from './api'

// These are synthetic test amounts and dates, not real company financials.
const timestamp = '2025-10-20T00:00:00Z'
const plan = { stock_code: '600519.SH', classification_source: '已审阅测试配置', classification_source_url: 'https://example.test/profile', company_name: '贵州茅台', company_type: '白酒消费企业', company_type_basis: '主营茅台酒及茅台酱香系列酒的生产与销售。', routing_method: 'Deterministic', safety_notice: null, dimensions: [{ id: 'growth', label: 'Growth', reason: 'The question matched growth keywords.', availability: 'available' }] }
const source = { source_id: 'source-1', endpoint: 'https://fuyao.aicubes.cn/api/a-share/financials/income-statements', parameters: { thscode: '600519.SH' }, retrieved_at: timestamp, sha256: 'synthetic-checksum', raw_json: '{"synthetic":true}', contract_url: 'https://fuyao.aicubes.cn/docs/api-reference/financials/', reporting_basis: 'consolidated', unit_basis: 'Original currency yuan' }
const evidence = { evidence_id: 'metric-1', kind: 'calculation', source_id: source.source_id, data_source: 'Fuyao', endpoint: source.endpoint, original_field_name: null, json_path: null, reporting_period: '2024 FY vs 2023 FY', period_end: '2024-12-31', value: '20', unit: '%', formula: '(current - previous) / previous * 100', input_evidence_ids: ['input-1', 'input-2'], retrieved_at: timestamp, status: 'available', reason: null, metadata_json_paths: {} }
export const fixture = researchSchema.parse({
  question: 'Compare growth', plan,
  diagnosis: { stock_code: '600519.SH', status: 'partial', current_year: 2024, previous_year: 2023, calculation_version: '1', decimal_precision: 38, rounding: 'ROUND_HALF_EVEN', issues: ['missing profit'], metrics: [{ name: 'revenue_growth', value: '20', unit: '%', status: 'available', reason: null, evidence_id: 'metric-1' }],
    evidence: [evidence, { ...evidence, evidence_id: 'input-1', kind: 'source', original_field_name: 'operating_income', json_path: '$.data.item[0].operating_income', reporting_period: '2024 FY', value: '120', unit: 'CNY yuan', input_evidence_ids: [], formula: null }, { ...evidence, evidence_id: 'input-2', kind: 'source', original_field_name: 'operating_income', json_path: '$.data.item[1].operating_income', reporting_period: '2023 FY', value: '100', unit: 'CNY yuan', input_evidence_ids: [], formula: null }], sources: [source] },
  findings: [{ id: 'revenue_growth', category: 'positive', kind: 'observation', title: 'Revenue increased year over year', text: 'Synthetic annual comparison.', evidence_ids: ['metric-1'], dimension: 'growth' }],
  observations: [{ id: 'revenue_growth', category: 'unknown', kind: 'observation', title: 'Revenue growth', text: 'Revenue growth is 20% for the synthetic annual comparison.', evidence_ids: ['metric-1'], dimension: 'growth' }],
  interpretation_mode: 'deterministic', interpretation_status: 'AI is not configured; displaying deterministic factual observations.', interpretations: [], freshness: 'Annual results are not current operations.', freshness_status: 'recent_annual_period', follow_up_questions: ['What evidence is missing to assess valuation?'], disclaimer: 'Research only. No recommendations.',
})
const mockFetch = vi.fn()
const catalog = [
  { stock_code: '600519.SH', name: '贵州茅台', company_type: '白酒消费企业', exchange: '上海证券交易所' },
  { stock_code: '300750.SZ', name: '宁德时代', company_type: '电池与储能制造企业', exchange: '深圳证券交易所' },
  { stock_code: '002594.SZ', name: '比亚迪', company_type: '汽车及多元制造企业', exchange: '深圳证券交易所' },
].map(item => ({ ...item, classification_basis: '预设研究分类', source: '已审阅测试配置', source_url: 'https://example.test/profile', identity_source_url: 'https://example.test/identity', default_dimensions: ['growth', 'profitability'] }))
const mockCatalog = vi.fn()
beforeEach(() => {
  mockFetch.mockReset(); mockCatalog.mockReset()
  mockCatalog.mockResolvedValue({ ok: true, json: async () => catalog })
  vi.stubGlobal('fetch', (input: string, init?: RequestInit) => input === '/api/stocks' ? mockCatalog(input, init) : mockFetch(input, init))
})
function mockJourney(report: ResearchReport = fixture) {
  mockFetch.mockResolvedValueOnce({ ok: true, json: async () => report.plan }).mockResolvedValueOnce({ ok: true, json: async () => report })
}
async function start() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('研究问题'), 'Compare growth')
  await user.click(screen.getByRole('button', { name: '开始研究' }))
  return user
}

describe('Research journey', () => {
  it('starts without financial placeholders and supports suggestions', async () => {
    const user = userEvent.setup(); render(<App />)
    expect(screen.queryByText('20.00%')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始研究' })).toBeDisabled()
    expect(screen.getByText('当前支持 3 家 A 股公司')).toBeInTheDocument()
    expect(screen.queryByText(/白名单|MVP 配置/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /营业收入与净利润的同比增长表现有何差异/ }))
    expect(screen.getByLabelText('研究问题')).toHaveValue('营业收入与净利润的同比增长表现有何差异？')
    expect(mockFetch).not.toHaveBeenCalled()
  })
  it('plans, diagnoses, verifies inputs, and launches a followup', async () => {
    mockJourney(); render(<App />); const user = await start()
    expect(await screen.findByText('20.00%')).toBeInTheDocument()
    expect(screen.getByText('问题中包含与成长能力相关的关键词，因此纳入研究。')).toBeInTheDocument()
    expect(screen.getByText('客观事实摘要')).toBeInTheDocument()
    expect(screen.getByText('2025年10月20日 08:00（北京时间）')).toBeInTheDocument()
    expect(screen.queryByText(/本地时间/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /营业收入同比增长率 20.00%/ }))
    const drawer = screen.getByRole('dialog')
    expect(within(drawer).getByText('(current - previous) / previous * 100')).toBeInTheDocument()
    expect(within(drawer).getByText('2025年10月20日 08:00（北京时间）')).toBeInTheDocument()
    expect(within(drawer).getByText(timestamp)).toBeInTheDocument()
    await user.click(within(drawer).getByRole('button', { name: /operating_income 2024 年度/ }))
    expect(within(drawer).getByText('$.data.item[0].operating_income')).toBeInTheDocument()
    expect(within(drawer).getByText('人民币元（CNY）')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '关闭证据面板' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    mockJourney()
    await user.click(screen.getAllByRole('button', { name: '评估估值水平还缺少哪些证据？' })[1])
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(4))
    expect(JSON.parse(mockFetch.mock.calls[3][1].body).question).toContain('估值')
  })
  it('shows missing data and empty evidence without invented findings', async () => {
    const empty = structuredClone(fixture)
    empty.diagnosis.metrics = []; empty.diagnosis.evidence = []; empty.diagnosis.status = 'unavailable'; empty.findings = []; empty.observations = []
    mockJourney(empty); render(<App />); await start()
    expect(await screen.findByText('本轮暂无可供钻取的财务或行情证据。缺失或未支持的研究内容请查看对应说明。')).toBeInTheDocument()
    expect(screen.getAllByText('暂不可用')).toHaveLength(3)
    expect(screen.queryByText('20.00%')).not.toBeInTheDocument()
  })
  it('rejects invalid evidence references', async () => {
    const invalid = structuredClone(fixture)
    invalid.findings[0].evidence_ids = ['invented']
    mockJourney(invalid); render(<App />); await start()
    expect(await screen.findByRole('alert')).toHaveTextContent('响应未通过格式或证据引用校验')
    expect(screen.queryByText('20.00%')).not.toBeInTheDocument()
  })
  it('shows upstream errors and supports retry', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => plan }).mockResolvedValueOnce({ ok: false, status: 504, json: async () => ({ error: { code: 'upstream_timeout', message: 'Fuyao request timed out.' } }) })
    render(<App />); const user = await start()
    expect(await screen.findByRole('alert')).toHaveTextContent('Fuyao 数据请求超时')
    expect(screen.queryByText('20.00%')).not.toBeInTheDocument()
    mockJourney()
    await user.click(screen.getByRole('button', { name: /重试/ }))
    expect(await screen.findByText('20.00%')).toBeInTheDocument()
  })
  it('handles network failures and unsupported stock responses', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Failed to fetch'))
    render(<App />); const user = await start()
    expect(await screen.findByRole('alert')).toHaveTextContent('无法连接研究服务')
    mockFetch.mockResolvedValueOnce({ ok: false, status: 422, json: async () => ({ error: { code: 'unsupported_stock', message: 'Only 600519.SH is supported.' } }) })
    await user.click(screen.getByRole('button', { name: /重试/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('当前支持贵州茅台、宁德时代和比亚迪')
  })
  it('shows loading state without invented progress or financial values', async () => {
    mockFetch.mockReturnValue(new Promise(() => {}))
    render(<App />); await start()
    expect(screen.getByRole('status')).toHaveTextContent('正在选择相关研究维度')
    expect(screen.getByRole('button', { name: /研究中/ })).toBeDisabled()
    expect(screen.queryByText('20.00%')).not.toBeInTheDocument()
  })
  it('shows safety reframing and separates AI interpretation from observations', async () => {
    const ai = structuredClone(fixture)
    ai.plan.safety_notice = 'StockLens does not recommend trades.'
    ai.interpretation_mode = 'llm'
    ai.interpretation_status = 'AI selected validated interpretations.'
    ai.interpretations = [{ id: 'interpret_growth', text: 'The annual comparison shows expansion in this measure. It does not establish persistence, the underlying cause, or investment attractiveness.', evidence_ids: ['metric-1'] }]
    mockJourney(ai); render(<App />); const user = await start()
    expect(await screen.findByText(/本问题涉及投资操作或收益确定性/)).toBeInTheDocument()
    expect(screen.getByText('AI 选取 · 证据已核验')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /该指标在年度比较中上升/ }))
    expect(screen.getByRole('dialog')).toHaveTextContent('metric-1')
  })
})

describe('Simplified Chinese presentation', () => {
  it('uses the requested slogan, Chinese navigation, categories, and input labels', async () => {
    mockJourney(); render(<App />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('看清企业经营，追溯每条结论。')
    expect(screen.getByRole('link', { name: '个股研究' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '研究方法' })).toHaveAttribute('href', '#method')
    await waitFor(() => expect(screen.getByLabelText('选择股票')).toHaveDisplayValue('贵州茅台 · 600519.SH'))
    await start()
    for (const name of ['正面证据', '负面证据', '矛盾与混合证据', '未知与待验证信息']) expect(await screen.findByRole('heading', { name })).toBeInTheDocument()
    expect(screen.queryByText('Matched growth keywords.')).not.toBeInTheDocument()
    expect(screen.queryByText('Positive Evidence')).not.toBeInTheDocument()
  })
  it('rounds cards and factual narratives while preserving evidence precision and API objects', async () => {
    const precise = structuredClone(fixture)
    const value = '-1.2060035021223'
    precise.diagnosis.metrics[0].value = value
    precise.diagnosis.evidence[0].value = value
    precise.findings[0].category = 'negative'
    precise.observations[0].text = `Revenue growth is ${value}% for 2024 FY.`
    const before = JSON.stringify(precise)
    mockJourney(precise); render(<App />); const user = await start()
    expect(await screen.findByText('-1.21%')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /客观事实.*营业收入同比增长率为 -1.21%/ })).toHaveLength(2)
    expect(screen.queryByText(new RegExp(value.replace('.', '\\.')))).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /营业收入同比增长率 -1.21%/ }))
    const drawer = screen.getByRole('dialog')
    expect(within(drawer).getByText(value)).toBeInTheDocument()
    expect(within(drawer).getByText('metric-1')).toBeInTheDocument()
    expect(within(drawer).getByText('(current - previous) / previous * 100')).toBeInTheDocument()
    expect(JSON.stringify(precise)).toBe(before)
    await user.click(within(drawer).getByText('查看原始 JSON'))
    expect(within(drawer).getByText(source.raw_json)).toBeInTheDocument()
  })
  it('does not expose unknown English model output or translate unsupported claims into conclusions', async () => {
    const untrusted = structuredClone(fixture)
    untrusted.interpretation_mode = 'llm'
    untrusted.interpretations = [{ id: 'unknown-template', text: 'Guaranteed future return of 123.456789%!', evidence_ids: ['metric-1'] }]
    mockJourney(untrusted); render(<App />); const user = await start()
    const fallback = await screen.findByRole('button', { name: /该项解读尚无经核验的中文版本/ })
    expect(screen.queryByText(/Guaranteed future return/)).not.toBeInTheDocument()
    await user.click(fallback)
    expect(screen.getByRole('dialog')).toHaveTextContent('metric-1')
    expect(screen.getByRole('dialog')).not.toHaveTextContent('123.456789')
  })
  it('localizes provider quota errors without echoing raw provider prose', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 429, json: async () => ({ error: { code: 'upstream_rate_limited', message: 'Provider quota exhausted: internal details' } }) })
    render(<App />); await start()
    expect(await screen.findByRole('alert')).toHaveTextContent('Fuyao 请求频率或额度已达限制')
    expect(screen.queryByText(/internal details/)).not.toBeInTheDocument()
  })
  it('localizes unavailable dimensions, freshness warnings, and missing-input reasons', async () => {
    const partial = structuredClone(fixture)
    partial.diagnosis.metrics[0] = { ...partial.diagnosis.metrics[0], value: null, status: 'unavailable', reason: 'missing_previous_year' }
    partial.diagnosis.evidence[0] = { ...partial.diagnosis.evidence[0], value: null, status: 'unavailable', reason: 'missing_previous_year' }
    partial.observations = []
    partial.freshness_status = 'stale'
    partial.plan.dimensions.push({ id: 'valuation', label: 'Valuation', availability: 'unavailable', reason: 'The question matched valuation keywords.' })
    partial.findings = [{ id: 'missing_valuation', category: 'unknown', kind: 'limitation', title: 'Valuation not verified', text: 'This release has no verified data adapter.', evidence_ids: [], dimension: 'valuation' }]
    mockJourney(partial); render(<App />); await start()
    expect(await screen.findByText('估值水平尚未核验')).toBeInTheDocument()
    expect(screen.getByText(/早于上一自然年度/)).toBeInTheDocument()
    expect(screen.getByText('缺少相邻上一年度数据')).toBeInTheDocument()
    expect(screen.queryByText('Valuation not verified')).not.toBeInTheDocument()
  })
})

// Synthetic prices are fixtures, not company market observations.
function priceReport(): ResearchReport {
  const report = structuredClone(fixture)
  report.question = '贵州茅台过去一个月的股价表现如何？'
  const src = { ...source, source_id: 'price-source', endpoint: 'https://fuyao.aicubes.cn/api/a-share/prices/historical', reporting_basis: 'daily_unadjusted', unit_basis: 'A-share prices are CNY per the Fuyao prices contract.' }
  const raw = (id: string, value: string, index: number) => ({ ...fixture.diagnosis.evidence[1], evidence_id: id, source_id: src.source_id, endpoint: src.endpoint, value, original_field_name: 'close_price', json_path: `$.data.item[${index}].close_price`, reporting_period: index === 0 ? '2025-09-22' : '2025-10-17' })
  report.price_analysis = { status: 'partial', requested_start: '2025-09-20', requested_end: '2025-10-19', actual_start: '2025-09-22', actual_end: '2025-10-17', currency: 'CNY', adjustment: 'none', interval: '1d', coverage: 'unverified', retrieved_at: timestamp, error_code: null, issues: ['coverage_unverified'],
    observations: [{ date: '2025-09-22', close: '100', high: '120', low: '90', evidence_ids: ['price-first'] }, { date: '2025-10-17', close: '110.123456789', high: '120', low: '90', evidence_ids: ['price-last'] }],
    metrics: [{ name: 'price_return', value: '10.123456789', unit: '%', status: 'available', reason: null, evidence_id: 'price-return' }],
    evidence: [raw('price-first', '100', 0), raw('price-last', '110.123456789', 1), { ...fixture.diagnosis.evidence[0], evidence_id: 'price-return', source_id: src.source_id, endpoint: src.endpoint, value: '10.123456789', reporting_period: '2025-09-22 ~ 2025-10-17', formula: '(end_close / start_close - 1) * 100', input_evidence_ids: ['price-last', 'price-first'] }], sources: [src] }
  report.findings.unshift({ id: 'price_return', category: 'positive', kind: 'observation', title: 'price_return', text: 'Verified price', evidence_ids: ['price-return'], dimension: 'price' })
  return report
}

describe('Historical price research', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class {
      constructor(private callback: (entries: { contentRect: { width: number; height: number } }[]) => void) {}
      observe() { this.callback([{ contentRect: { width: 800, height: 300 } }]) }
      unobserve() {} disconnect() {}
    })
  })
  it('shows price fields, rounds summaries and opens source evidence', async () => {
    mockJourney(priceReport()); render(<App />); const user = await start()
    expect(await screen.findByRole('heading', { name: '历史股价表现' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /历史收盘价折线图/ })).toBeInTheDocument()
    expect(screen.getByText(/尚未核验交易日历/)).toBeInTheDocument()
    expect(screen.getByText(/请求区间：2025-09-20 至 2025-10-19（北京时间）/)).toBeInTheDocument()
    expect(screen.queryByText(/上海时区/)).not.toBeInTheDocument()
    expect(screen.getByText(/获取于 2025年10月20日 08:00（北京时间）/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /观测区间价格涨跌幅\s+10.12%/ }))
    const drawer = screen.getByRole('dialog')
    expect(within(drawer).getByText('10.123456789')).toBeInTheDocument()
    expect(within(drawer).getByText('(end_close / start_close - 1) * 100')).toBeInTheDocument()
    await user.click(within(drawer).getByRole('button', { name: /close_price 2025-10-17/ }))
    expect(within(drawer).getByText('$.data.item[1].close_price')).toBeInTheDocument()
    expect(within(drawer).getByText('110.123456789')).toBeInTheDocument()
  })
  it.each(['upstream_rate_limited', 'upstream_timeout'])('keeps financial results without a chart after %s', async code => {
    const report = priceReport()
    Object.assign(report.price_analysis!, { status: 'unavailable', observations: [], metrics: [], evidence: [], sources: [], actual_start: null, actual_end: null, error_code: code, issues: [code] })
    report.findings = fixture.findings
    mockJourney(report); render(<App />); await start()
    expect(await screen.findByText('暂无通过核验的历史价格，不生成价格图表。')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: '历史股价分析' })).queryByRole('list')).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /历史收盘价折线图/ })).not.toBeInTheDocument()
    expect(screen.getByText('20.00%')).toBeInTheDocument()
  })
  it('rejects fabricated price observation and calculation references', () => {
    const report = priceReport()
    expect(researchSchema.safeParse(report).success).toBe(true)
    report.price_analysis!.observations[0].evidence_ids = ['fabricated']
    expect(researchSchema.safeParse(report).success).toBe(false)
    report.price_analysis!.observations[0].evidence_ids = ['price-first']
    report.price_analysis!.evidence[2].input_evidence_ids = ['fabricated']
    expect(researchSchema.safeParse(report).success).toBe(false)
  })
  it('displays empty price data explicitly', async () => {
    const report = priceReport()
    Object.assign(report.price_analysis!, { status: 'unavailable', observations: [], metrics: [], evidence: [], sources: [], actual_start: null, actual_end: null, issues: ['no_price_data'] })
    report.findings = fixture.findings
    mockJourney(report); render(<App />); await start()
    expect(await screen.findByText('该请求区间未返回有效价格。')).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /历史收盘价折线图/ })).not.toBeInTheDocument()
  })
})


describe('Question-aware diagnosis presentation', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class {
      constructor(private callback: (entries: { contentRect: { width: number; height: number } }[]) => void) {}
      observe() { this.callback([{ contentRect: { width: 800, height: 300 } }]) }
      unobserve() {} disconnect() {}
    })
  })
  it('expands price research and exposes financial context through a keyboard-accessible disclosure', async () => {
    const report = priceReport()
    mockJourney(report); render(<App />); const user = await start()
    expect(await screen.findByRole('region', { name: '历史股价分析' })).toBeVisible()
    const summary = screen.getByText('补充财务背景')
    expect(summary.closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('年度财务指标')).not.toBeVisible()
    summary.focus()
    expect(summary).toHaveFocus()
    await user.keyboard('{Enter}')
    // jsdom does not emulate the browser's native Enter-to-toggle default action.
    await user.click(summary)
    expect(summary.closest('details')).toHaveAttribute('open')
    expect(screen.getByRole('region', { name: '年度财务分析' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: /营业收入同比增长率 20.00%/ }))
    expect(screen.getByRole('dialog')).toHaveTextContent('metric-1')
  })
  it('keeps financial research primary and collapses any returned price context', async () => {
    const report = priceReport()
    report.question = '营业收入和净利润增长如何？'
    mockJourney(report); render(<App />); const user = await start()
    const financial = await screen.findByRole('region', { name: '年度财务分析' })
    expect(financial).toBeVisible()
    const summary = screen.getByText('补充历史价格背景')
    expect(summary.closest('details')).not.toHaveAttribute('open')
    expect(screen.getByRole('region', { name: '历史股价分析' })).not.toBeVisible()
    await user.click(summary)
    const price = screen.getByRole('region', { name: '历史股价分析' })
    expect(price).toBeVisible()
    expect(financial.compareDocumentPosition(price) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
  it('shows both diagnoses expanded for an explicit financial-and-price question without inventing conflicts', async () => {
    const report = priceReport()
    report.question = '贵州茅台营业收入与净利润增长如何，过去一个月股价表现如何？'
    mockJourney(report); render(<App />); await start()
    expect(await screen.findByRole('region', { name: '年度财务分析' })).toBeVisible()
    expect(screen.getByRole('region', { name: '历史股价分析' })).toBeVisible()
    expect(screen.queryByText('补充财务背景')).not.toBeInTheDocument()
    expect(screen.queryByText('补充历史价格背景')).not.toBeInTheDocument()
    expect(report.findings.filter(f => f.category === 'mixed')).toHaveLength(0)
    expect(screen.getAllByText('证据不足，暂未形成相关判断')).toHaveLength(3)
  })
})


function reportForStock(code: '600519.SH' | '300750.SZ' | '002594.SZ'): ResearchReport {
  const report = structuredClone(fixture)
  const stock = catalog.find(s => s.stock_code === code)!
  Object.assign(report.plan, { stock_code: code, company_name: stock.name, company_type: stock.company_type })
  report.diagnosis.stock_code = code
  report.diagnosis.sources.forEach(s => { s.parameters.thscode = code })
  return report
}

describe('Three-stock scope and isolation', () => {
  it.each(['600519.SH', '300750.SZ', '002594.SZ'] as const)('requests and explores only the selected stock: %s', async code => {
    render(<App />); const user = userEvent.setup()
    await waitFor(() => expect(screen.getByLabelText('选择股票')).toBeEnabled())
    expect(screen.getAllByRole('option')).toHaveLength(3)
    await user.selectOptions(screen.getByLabelText('选择股票'), code)
    const report = reportForStock(code)
    mockJourney(report)
    await user.type(screen.getByLabelText('研究问题'), '营收与利润增长如何？')
    await user.click(screen.getByRole('button', { name: '开始研究' }))
    expect(await screen.findByText('20.00%')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: '研究计划' })).getByText(report.plan.company_name, { exact: true })).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: '研究计划' })).getByText(report.plan.company_type, { exact: true })).toBeInTheDocument()
    expect(mockFetch.mock.calls.every(call => JSON.parse(call[1].body).stock_code === code)).toBe(true)
    mockJourney(report)
    await user.click(screen.getAllByRole('button', { name: '评估估值水平还缺少哪些证据？' })[1])
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(4))
    expect(JSON.parse(mockFetch.mock.calls[3][1].body).stock_code).toBe(code)
  })
  it('clears an old report, evidence drawer and input when changing company', async () => {
    mockJourney(); render(<App />); const user = await start()
    await screen.findByText('20.00%')
    await user.click(screen.getByRole('button', { name: /营业收入同比增长率 20.00%/ }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('选择股票'), '002594.SZ')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('20.00%')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('研究计划')).not.toBeInTheDocument()
    expect(screen.getByLabelText('研究问题')).toHaveValue('')
    expect(screen.getByRole('button', { name: '开始研究' })).toBeDisabled()
  })
  it.each(['plan', 'report', 'failure'])('late %s from the previous stock cannot overwrite the new diagnosis', async stage => {
    let resolveOld!: (response: unknown) => void
    let rejectOld!: (reason: Error) => void
    const pending = new Promise((resolve, reject) => { resolveOld = resolve; rejectOld = reject })
    if (stage === 'plan') mockFetch.mockReturnValueOnce(pending)
    else mockFetch.mockResolvedValueOnce({ ok: true, json: async () => fixture.plan }).mockReturnValueOnce(pending)
    render(<App />); const user = await start()
    await user.selectOptions(screen.getByLabelText('选择股票'), '300750.SZ')
    const next = reportForStock('300750.SZ'); next.question = '净利润增长如何？'; mockJourney(next)
    await user.type(screen.getByLabelText('研究问题'), '净利润增长如何？')
    await user.click(screen.getByRole('button', { name: '开始研究' }))
    await screen.findByText('20.00%')
    await act(async () => {
      if (stage === 'failure') rejectOld(new Error('old network failure'))
      else resolveOld({ ok: true, json: async () => stage === 'plan' ? fixture.plan : fixture })
    })
    expect(screen.getByLabelText('选择股票')).toHaveValue('300750.SZ')
    expect(within(screen.getByRole('region', { name: '研究计划' })).getByText('宁德时代', { exact: true })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('“Compare growth”')).not.toBeInTheDocument()
  })
  it('rejects a wrong-stock plan before requesting research', async () => {
    mockJourney(reportForStock('300750.SZ')); render(<App />); await start()
    expect(await screen.findByRole('alert')).toHaveTextContent('股票身份不匹配')
    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('20.00%')).not.toBeInTheDocument()
  })
  it('rejects a wrong-stock research response even when its internal references are valid', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => fixture.plan }).mockResolvedValueOnce({ ok: true, json: async () => reportForStock('300750.SZ') })
    render(<App />); await start()
    expect(await screen.findByRole('alert')).toHaveTextContent('股票身份不匹配')
    expect(screen.queryByText('20.00%')).not.toBeInTheDocument()
  })
  it('rejects cross-stock financial and price sources', () => {
    const report = reportForStock('300750.SZ')
    report.diagnosis.sources[0].parameters.thscode = '600519.SH'
    expect(researchSchema.safeParse(report).success).toBe(false)
    const price = priceReport()
    price.price_analysis!.sources[0].parameters.thscode = '002594.SZ'
    expect(researchSchema.safeParse(price).success).toBe(false)
  })
  it('clears an old error when switching company', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Failed'))
    render(<App />); const user = await start()
    await screen.findByRole('alert')
    await user.selectOptions(screen.getByLabelText('选择股票'), '002594.SZ')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('does not invent a stock catalog if its request fails', async () => {
    mockCatalog.mockResolvedValueOnce({ ok: false })
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('股票目录暂不可用')
    expect(screen.getByLabelText('选择股票')).toBeDisabled()
    expect(screen.getByRole('button', { name: '开始研究' })).toBeDisabled()
    expect(mockFetch).not.toHaveBeenCalled()
  })
})

it.each(['600519.SH', '300750.SZ', '002594.SZ'] as const)('presents the same four classification fields for %s without claiming automatic classification', async code => {
  render(<App />); const user = userEvent.setup()
  await waitFor(() => expect(screen.getByLabelText('选择股票')).toBeEnabled())
  await user.selectOptions(screen.getByLabelText('选择股票'), code)
  const report = reportForStock(code)
  mockJourney(report)
  await user.type(screen.getByLabelText('研究问题'), '营收增长如何？')
  await user.click(screen.getByRole('button', { name: '开始研究' }))
  const planning = await screen.findByRole('region', { name: '研究计划' })
  for (const label of ['公司名称：', '研究分类：', '分类依据：', '当前诊断重点：']) {
    expect(within(planning).getByText(label)).toBeInTheDocument()
  }
  expect(within(planning).getByText(report.plan.company_name, { exact: true })).toBeInTheDocument()
  expect(within(planning).getByText(report.plan.company_type, { exact: true })).toBeInTheDocument()
  const profileLink = within(planning).getByRole('link', { name: '查看公司简介' })
  expect(profileLink).toHaveAttribute('href', report.plan.classification_source_url)
  expect(profileLink).toHaveAttribute('target', '_blank')
  expect(profileLink).toHaveAttribute('rel', 'noopener noreferrer')
  expect(profileLink).toHaveClass('company-profile-link')
  expect(profileLink.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  expect(planning).toHaveTextContent('当前诊断重点：成长能力')
  expect(within(planning).getAllByText('研究分类根据企业公开业务资料人工设置，不代表官方行业分类。')).toHaveLength(1)
  expect(planning).not.toHaveTextContent('非自动行业识别')
  expect(planning).not.toHaveTextContent('MVP')
})


it.each(['600519.SH', '300750.SZ', '002594.SZ'] as const)('launches a curated follow-up with the current stock and labels pending data: %s', async code => {
  render(<App />); const user = userEvent.setup()
  await waitFor(() => expect(screen.getByLabelText('选择股票')).toBeEnabled())
  await user.selectOptions(screen.getByLabelText('选择股票'), code)
  const report = reportForStock(code)
  report.follow_up_mode = 'llm'
  report.follow_up_suggestions = [
    { id: 'margin_limits', question: '年度净利润率反映什么？', dimension: 'profitability', availability: 'supported', stock_code: code, evidence_ids: ['metric-1'], reporting_periods: ['2024 FY vs 2023 FY'] },
    { id: 'valuation_gap', question: '估值还缺哪些数据？', dimension: 'valuation', availability: 'pending', stock_code: code, evidence_ids: [], reporting_periods: [] },
  ]
  mockJourney(report)
  await user.type(screen.getByLabelText('研究问题'), '营收如何？')
  await user.click(screen.getByRole('button', { name: '开始研究' }))
  expect(await screen.findByRole('button', { name: /估值还缺哪些数据？（待验证）/ })).toBeInTheDocument()
  expect(screen.getByText(/建议由 AI 从审核目录中选取/)).toBeInTheDocument()
  mockJourney(report)
  await user.click(screen.getByRole('button', { name: /年度净利润率反映什么/ }))
  await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(4))
  expect(JSON.parse(mockFetch.mock.calls[3][1].body)).toEqual({ stock_code: code, question: '年度净利润率反映什么？' })
})

it('rejects follow-up suggestions with foreign stock or invalid evidence', () => {
  const report = reportForStock('300750.SZ')
  report.follow_up_suggestions = [{ id: 'bad', question: '问题', dimension: 'growth', availability: 'supported', stock_code: '002594.SZ', evidence_ids: [], reporting_periods: [] }]
  expect(researchSchema.safeParse(report).success).toBe(false)
  report.follow_up_suggestions[0].stock_code = '300750.SZ'
  report.follow_up_suggestions[0].evidence_ids = ['foreign-evidence']
  expect(researchSchema.safeParse(report).success).toBe(false)
})

// Answer fixtures test presentation and references, not new financial calculations.
const answerIntents = ['price_performance', 'growth_comparison', 'margin_meaning', 'valuation_evidence_gap', 'cashflow_support', 'manufacturing_evidence_gap', 'price_causality', 'unsupported'] as const
function answeredReport(intent: typeof answerIntents[number] = 'growth_comparison', code: '600519.SH' | '300750.SZ' | '002594.SZ' = '600519.SH'): ResearchReport {
  const price = ['price_performance', 'price_causality'].includes(intent)
  const report = structuredClone(price ? priceReport() : reportForStock(code))
  report.diagnosis.sources.forEach(source => { source.parameters.thscode = code })
  report.price_analysis?.sources.forEach(source => { source.parameters.thscode = code })
  const supported = ['growth_comparison', 'margin_meaning', 'valuation_evidence_gap'].includes(intent)
  const gapOnly = ['valuation_evidence_gap', 'cashflow_support', 'manufacturing_evidence_gap', 'unsupported'].includes(intent)
  report.answer = {
    intent_id: intent, answer_status: supported ? 'answered' : price ? 'partial' : 'unavailable',
    direct_answer: `本轮确定性主答案：${intent}。`,
    supporting_evidence_ids: gapOnly ? [] : [price ? 'price-return' : 'metric-1'],
    missing_evidence: gapOnly || price ? [{ code: 'test_gap', description: '尚缺经核验的相关证据，不能作出进一步判断。', reason: 'unverified' }] : [],
    scope: { stock_code: code, reporting_periods: price || gapOnly ? [] : ['2024 FY vs 2023 FY'],
      price_requested_start: price ? '2025-09-20' : null, price_requested_end: price ? '2025-10-19' : null,
      price_observed_start: price ? '2025-09-22' : null, price_observed_end: price ? '2025-10-17' : null,
      time_zone: 'Asia/Shanghai', assumptions: ['仅解释本轮证据，不构成因果判断或投资建议。'] },
  }
  return report
}

describe('Unified question answers', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class {
      constructor(private callback: (entries: { contentRect: { width: number; height: number } }[]) => void) {}
      observe() { this.callback([{ contentRect: { width: 800, height: 300 } }]) }
      unobserve() {} disconnect() {}
    })
  })
  it.each(answerIntents)('puts %s before all financial and price context', async intent => {
    const report = answeredReport(intent)
    expect(researchSchema.safeParse(report).error?.issues).toBeUndefined()
    mockJourney(report); render(<App />); await start()
    const answer = await screen.findByRole('region', { name: '针对你的问题' })
    expect(within(answer).getByText(report.answer!.direct_answer)).toBeVisible()
    const financial = screen.getByRole('region', { name: '年度财务分析', hidden: true })
    expect(answer.compareDocumentPosition(financial) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const details = financial.closest('details')
    if (['growth_comparison', 'margin_meaning'].includes(intent)) expect(details).toBeNull()
    else expect(details).not.toHaveAttribute('open')
    expect(screen.getByText('补充研究解读').closest('details')).not.toHaveAttribute('open')
    for (const label of ['正面证据', '负面证据', '矛盾与混合证据', '未知与待验证信息']) expect(screen.getByRole('heading', { name: label })).toBeInTheDocument()
    if (intent.startsWith('price_')) {
      const chart = screen.getByRole('heading', { name: '历史股价表现' })
      expect(chart.closest('details')).toBeNull()
      expect(answer.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      expect(within(answer).getByText(/实际有效观测区间：/)).toHaveTextContent('北京时间')
    }
  })
  it.each(['answered', 'partial', 'unavailable'] as const)('shows independent answer status %s', async status => {
    const report = answeredReport(status === 'answered' ? 'growth_comparison' : status === 'partial' ? 'price_performance' : 'cashflow_support')
    report.diagnosis.status = 'complete'
    mockJourney(report); render(<App />); await start()
    const region = await screen.findByRole('region', { name: '针对你的问题' })
    expect(within(region).getByText({ answered: '已回答', partial: '部分回答', unavailable: '暂无法回答' }[status])).toBeVisible()
    if (status !== 'answered') expect(within(region).getByRole('heading', { name: '尚缺的证据' })).toBeVisible()
  })
  it('opens real answer evidence and restores keyboard focus', async () => {
    mockJourney(answeredReport()); render(<App />); const user = await start()
    const button = await screen.findByRole('button', { name: '查看依据' })
    button.focus(); await user.keyboard('{Enter}')
    expect(within(screen.getByRole('dialog')).getByText('metric-1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '关闭证据面板' }))
    expect(button).toHaveFocus()
  })
  it('shows gaps without an empty evidence action', async () => {
    mockJourney(answeredReport('cashflow_support')); render(<App />); await start()
    const region = await screen.findByRole('region', { name: '针对你的问题' })
    expect(within(region).queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it.each([undefined, null])('supports legacy answer value %s', async answer => {
    const report = structuredClone(fixture); report.answer = answer
    mockJourney(report); render(<App />); await start()
    expect(await screen.findByText('20.00%')).toBeVisible()
    expect(screen.queryByRole('region', { name: '针对你的问题' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '研究解读' })).toBeVisible()
  })
  it('keeps Gemini output supplementary without changing it', async () => {
    const report = answeredReport('cashflow_support'); report.interpretation_mode = 'llm'
    report.interpretations = [{ id: 'test', text: '年度背景解读', evidence_ids: ['metric-1'] }]
    mockJourney(report); render(<App />); const user = await start()
    await screen.findByRole('region', { name: '针对你的问题' })
    const details = screen.getByText('补充研究解读').closest('details')!
    expect(details).not.toHaveAttribute('open')
    await user.click(screen.getByText('补充研究解读'))
    expect(details).toHaveAttribute('open')
    expect(screen.getByText('AI 选取 · 证据已核验')).toBeVisible()
  })
  it.each(['600519.SH', '300750.SZ', '002594.SZ'] as const)('clears answers and drawer, and explores with current stock %s', async code => {
    render(<App />); const user = userEvent.setup()
    await waitFor(() => expect(screen.getByLabelText('选择股票')).toBeEnabled())
    await user.selectOptions(screen.getByLabelText('选择股票'), code)
    mockJourney(answeredReport('growth_comparison', code)); await start()
    await user.click(await screen.findByRole('button', { name: '查看依据' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '关闭证据面板' }))
    const next = answeredReport('valuation_evidence_gap', code); mockJourney(next)
    await user.click(screen.getAllByRole('button', { name: '评估估值水平还缺少哪些证据？' }).at(-1)!)
    expect(await screen.findByText(next.answer!.direct_answer)).toBeVisible()
    expect(screen.queryByText('本轮确定性主答案：growth_comparison。')).not.toBeInTheDocument()
    expect(JSON.parse(mockFetch.mock.calls[3][1].body).stock_code).toBe(code)
    await user.selectOptions(screen.getByLabelText('选择股票'), code === '600519.SH' ? '300750.SZ' : '600519.SH')
    expect(screen.queryByRole('region', { name: '针对你的问题' })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('rejects a broken answer before displaying any report', async () => {
    const report = answeredReport(); report.answer!.supporting_evidence_ids = ['invented']
    mockJourney(report); render(<App />); await start()
    expect(await screen.findByRole('alert')).toHaveTextContent('响应未通过格式或证据引用校验')
    expect(screen.queryByRole('region', { name: '针对你的问题' })).not.toBeInTheDocument()
  })
  it('scopes financial failures without hiding available price evidence', async () => {
    const report = answeredReport('price_performance')
    Object.assign(report.diagnosis, { status: 'unavailable', current_year: null, previous_year: null, metrics: [], evidence: [], sources: [], issues: ['upstream_timeout'] })
    report.findings = report.findings.filter(item => item.dimension === 'price'); report.observations = []
    mockJourney(report); render(<App />); const user = await start()
    await screen.findByRole('region', { name: '针对你的问题' })
    expect(screen.queryByText(/本轮暂无可供钻取/)).not.toBeInTheDocument()
    expect(screen.queryByText(/未返回证据记录/)).not.toBeInTheDocument()
    expect(screen.getByText('年度财务数据说明（1）')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '查看依据' }))
    expect(within(screen.getByRole('dialog')).getByText('price-return')).toBeInTheDocument()
  })
  it('does not treat unsupported answer dimensions as global evidence failures', async () => {
    const report = answeredReport('cashflow_support'); report.diagnosis.issues = []
    mockJourney(report); render(<App />); const user = await start()
    const answer = await screen.findByRole('region', { name: '针对你的问题' })
    expect(within(answer).queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByText(/本轮暂无可供钻取|未返回证据记录|年度财务数据说明/)).not.toBeInTheDocument()
    await user.click(screen.getByText('补充财务背景'))
    await user.click(screen.getByRole('button', { name: /营业收入同比增长率 20.00%/ }))
    expect(within(screen.getByRole('dialog')).getByText('metric-1')).toBeInTheDocument()
  })
  it('opens price answer inputs with full original precision', async () => {
    mockJourney(answeredReport('price_causality')); render(<App />); const user = await start()
    await user.click(await screen.findByRole('button', { name: '查看依据' }))
    const drawer = screen.getByRole('dialog')
    expect(within(drawer).getByText('10.123456789')).toBeInTheDocument()
    expect(within(drawer).getByText('(end_close / start_close - 1) * 100')).toBeInTheDocument()
    await user.click(within(drawer).getByRole('button', { name: /close_price.*110.123456789/ }))
    expect(within(drawer).getByText('$.data.item[1].close_price')).toBeInTheDocument()
  })
  it('closes an open answer drawer when changing company', async () => {
    mockJourney(answeredReport()); render(<App />); const user = await start()
    await user.click(await screen.findByRole('button', { name: '查看依据' }))
    await user.selectOptions(screen.getByLabelText('选择股票'), '002594.SZ')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '针对你的问题' })).not.toBeInTheDocument()
  })
  it('offers financial comparison without a pending label after a price-causality evidence gap', async () => {
    const first = answeredReport('price_causality')
    Object.assign(first.diagnosis, { status: 'unavailable', current_year: null, previous_year: null, metrics: [], evidence: [], sources: [], issues: ['upstream_timeout'] })
    first.findings = first.findings.filter(item => item.dimension === 'price'); first.observations = []
    first.follow_up_suggestions = [{ id: 'annual_comparison', question: '年度营业收入与净利润的增长表现有何差异？', dimension: 'growth', availability: 'supported', stock_code: '600519.SH', evidence_ids: [], reporting_periods: [] }]
    mockJourney(first); render(<App />); const user = await start()
    const followup = await screen.findByRole('button', { name: '年度营业收入与净利润的增长表现有何差异？' })
    expect(followup).not.toHaveTextContent('待验证')
    expect(screen.getByText(/结果视数据而定/)).toBeInTheDocument()
    const second = answeredReport('growth_comparison'); mockJourney(second)
    await user.click(followup)
    expect(await screen.findByText(second.answer!.direct_answer)).toBeVisible()
    expect(screen.queryByText(first.answer!.direct_answer)).not.toBeInTheDocument()
    expect(JSON.parse(mockFetch.mock.calls[3][1].body)).toEqual({ stock_code: '600519.SH', question: first.follow_up_suggestions[0].question })
    await user.click(screen.getByRole('button', { name: '查看依据' }))
    expect(within(screen.getByRole('dialog')).getByText('metric-1')).toBeInTheDocument()
    expect(within(screen.getByRole('dialog')).queryByText('price-return')).not.toBeInTheDocument()
  })
  it('retains supported financial followups after a price timeout without a fabricated chart', async () => {
    const report = answeredReport('price_causality')
    Object.assign(report.price_analysis!, { status: 'unavailable', observations: [], metrics: [], evidence: [], sources: [], actual_start: null, actual_end: null, error_code: 'upstream_timeout', issues: ['upstream_timeout', 'upstream_timeout'] })
    report.answer!.answer_status = 'unavailable'; report.answer!.supporting_evidence_ids = []
    report.answer!.direct_answer = '本轮行情请求超时，无法核验价格变化或解释原因。'
    report.answer!.scope.price_observed_start = null; report.answer!.scope.price_observed_end = null
    report.findings = fixture.findings
    report.follow_up_suggestions = [
      { id: 'annual_comparison', question: '年度营业收入与净利润的增长表现有何差异？', dimension: 'growth', availability: 'supported', stock_code: '600519.SH', evidence_ids: [], reporting_periods: [] },
      { id: 'margin_limits', question: '怎样理解这家公司的盈利能力，净利润率不能说明哪些问题？', dimension: 'profitability', availability: 'supported', stock_code: '600519.SH', evidence_ids: [], reporting_periods: [] },
    ]
    mockJourney(report); render(<App />); const user = await start()
    expect(await screen.findByText(report.answer!.direct_answer)).toBeVisible()
    const price = screen.getByRole('region', { name: '历史股价分析' })
    expect(within(price).getByRole('status')).toHaveTextContent('Fuyao 数据请求超时')
    expect(within(price).queryByRole('list')).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /历史收盘价折线图/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: report.follow_up_suggestions[1].question })).not.toHaveTextContent('待验证')
    const next = answeredReport('growth_comparison'); mockJourney(next)
    await user.click(screen.getByRole('button', { name: report.follow_up_suggestions[0].question }))
    expect(await screen.findByText(next.answer!.direct_answer)).toBeVisible()
    expect(JSON.parse(mockFetch.mock.calls[3][1].body).stock_code).toBe('600519.SH')
  })
  it('ignores a late answer from another stock', async () => {
    let resolveOld!: (value: unknown) => void
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => fixture.plan }).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
    render(<App />); const user = await start()
    await user.selectOptions(screen.getByLabelText('选择股票'), '300750.SZ')
    const next = answeredReport('margin_meaning', '300750.SZ'); mockJourney(next)
    await user.type(screen.getByLabelText('研究问题'), '净利润率能说明什么？'); await user.click(screen.getByRole('button', { name: '开始研究' }))
    await screen.findByText(next.answer!.direct_answer)
    await act(async () => resolveOld({ ok: true, json: async () => answeredReport() }))
    expect(screen.getByText(next.answer!.direct_answer)).toBeVisible()
    expect(screen.queryByText('本轮确定性主答案：growth_comparison。')).not.toBeInTheDocument()
  })
})

describe('Answer contract and evidence validation', () => {
  it.each(['missing', 'unavailable', 'input_unavailable', 'cycle', 'foreign_scope', 'foreign_source', 'duplicate', 'blank', 'endpoint', 'timestamp'])( 'rejects %s references', kind => {
    const report = answeredReport()
    if (kind === 'missing') report.answer!.supporting_evidence_ids = ['invented']
    if (kind === 'unavailable') report.diagnosis.evidence[0].status = 'unavailable'
    if (kind === 'input_unavailable') report.diagnosis.evidence[1].status = 'unavailable'
    if (kind === 'cycle') report.diagnosis.evidence[1].input_evidence_ids = ['metric-1']
    if (kind === 'foreign_scope') report.answer!.scope.stock_code = '300750.SZ'
    if (kind === 'foreign_source') report.diagnosis.sources[0].parameters.thscode = '300750.SZ'
    if (kind === 'duplicate') report.answer!.supporting_evidence_ids.push('metric-1')
    if (kind === 'blank') report.answer!.supporting_evidence_ids = [' ']
    if (kind === 'endpoint') report.diagnosis.evidence[0].endpoint = 'https://example.test/other'
    if (kind === 'timestamp') report.diagnosis.evidence[0].retrieved_at = '2025-10-21T00:00:00Z'
    expect(researchSchema.safeParse(report).success).toBe(false)
  })
  it.each(['intent', 'status', 'text', 'gap', 'date', 'order', 'pair', 'range', 'zone', 'extra'])('rejects malformed %s', kind => {
    const report = answeredReport('price_performance')
    const answer = report.answer! as unknown as Record<string, unknown>
    if (kind === 'intent') answer.intent_id = 'invented'
    if (kind === 'status') answer.answer_status = 'complete'
    if (kind === 'text') answer.direct_answer = ' '
    if (kind === 'gap') answer.missing_evidence = []
    if (kind === 'date') report.answer!.scope.price_requested_start = '2025-02-30'
    if (kind === 'order') report.answer!.scope.price_requested_start = '2026-01-01'
    if (kind === 'pair') report.answer!.scope.price_requested_end = null
    if (kind === 'range') report.answer!.scope.price_observed_end = '2026-01-01'
    if (kind === 'zone') answer.scope = { ...report.answer!.scope, time_zone: 'Australia/Sydney' }
    if (kind === 'extra') answer.unreviewed_field = 'extra'
    expect(researchSchema.safeParse(report).success).toBe(false)
  })
})
