import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { researchSchema, type ResearchReport } from './api'

// These are synthetic test amounts and dates, not real company financials.
const timestamp = '2025-10-20T00:00:00Z'
const plan = { stock_code: '600519.SH', classification_source: '已审阅测试配置', classification_source_url: 'https://example.test/profile', company_name: '贵州茅台', company_type: '白酒消费企业', company_type_basis: '依据公开业务资料人工审阅；非自动行业识别。', routing_method: 'Deterministic', safety_notice: null, dimensions: [{ id: 'growth', label: 'Growth', reason: 'The question matched growth keywords.', availability: 'available' }] }
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
    await user.click(screen.getByRole('button', { name: /营业收入与净利润的同比增长表现有何差异/ }))
    expect(screen.getByLabelText('研究问题')).toHaveValue('营业收入与净利润的同比增长表现有何差异？')
    expect(mockFetch).not.toHaveBeenCalled()
  })
  it('plans, diagnoses, verifies inputs, and launches a followup', async () => {
    mockJourney(); render(<App />); const user = await start()
    expect(await screen.findByText('20.00%')).toBeInTheDocument()
    expect(screen.getByText('问题中包含与成长能力相关的关键词，因此纳入研究。')).toBeInTheDocument()
    expect(screen.getByText('客观事实摘要')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /营业收入同比增长率 20.00%/ }))
    const drawer = screen.getByRole('dialog')
    expect(within(drawer).getByText('(current - previous) / previous * 100')).toBeInTheDocument()
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
    expect(await screen.findByText('未返回证据记录，暂时无法核验来源。')).toBeInTheDocument()
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
    expect(await screen.findByRole('alert')).toHaveTextContent('三股票白名单')
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
  expect(within(planning).getByRole('link', { name: report.plan.classification_source })).toHaveAttribute('href', report.plan.classification_source_url)
  expect(planning).toHaveTextContent('当前诊断重点：成长能力')
  expect(planning).toHaveTextContent('人工审阅公开业务资料')
  expect(planning).toHaveTextContent('不是自动行业识别或官方行业分类')
  expect(planning).not.toHaveTextContent('MVP')
})
