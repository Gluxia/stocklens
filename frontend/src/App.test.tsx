import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { researchSchema, type ResearchReport } from './api'

// These are synthetic test amounts and dates, not real company financials.
const timestamp = '2025-10-20T00:00:00Z'
const plan = { company_name: 'Kweichow Moutai', company_type: 'Non-financial operating company', company_type_basis: 'Reviewed MVP scope', routing_method: 'Deterministic', safety_notice: null, dimensions: [{ id: 'growth', label: 'Growth', reason: 'The question matched growth keywords.', availability: 'available' }] }
const source = { source_id: 'source-1', endpoint: 'https://fuyao.aicubes.cn/api/a-share/financials/income-statements', parameters: {}, retrieved_at: timestamp, sha256: 'synthetic-checksum', raw_json: '{"synthetic":true}', contract_url: 'https://fuyao.aicubes.cn/docs/api-reference/financials/', reporting_basis: 'consolidated', unit_basis: 'Original currency yuan' }
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
beforeEach(() => { vi.stubGlobal('fetch', mockFetch); mockFetch.mockReset() })
function mockJourney(report: ResearchReport = fixture) {
  mockFetch.mockResolvedValueOnce({ ok: true, json: async () => plan }).mockResolvedValueOnce({ ok: true, json: async () => report })
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
    expect(await screen.findByText(/当前版本仅支持贵州茅台/)).toBeInTheDocument()
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
    expect(screen.getByLabelText('选择股票')).toHaveDisplayValue('贵州茅台 · 600519.SH')
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
