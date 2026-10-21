import { useEffect, useRef, useState } from 'react'
import { ArrowDownRight, ArrowRight, ArrowUpRight, BookOpen, Check, ChevronRight, CircleHelp, Clock3, Database, ExternalLink, FileSearch, FlaskConical, Layers3, LoaderCircle, PanelRightOpen, ScanLine, Search, ShieldCheck, Sparkles, X } from 'lucide-react'
import { fetchStocks, type Stock, type StockCode, reportEvidence, reportSources, fetchPlan, fetchResearch, formatDate, formatMetric, labels, reasonText, requestErrorText, type Evidence, type Plan, type ResearchReport } from './api'
import PriceSection from './PriceSection'
import { researchFocus } from './presentation'
import { dimensionLabels, dimensionReason, disclaimer, findingCopy, followUpText, freshnessText, interpretationStatus, interpretationText, metadataLabel, periodText, safetyNotice, sourceName, unitBasisText, unitText } from './zh-CN'

const suggestions = ['过去一个月的股价表现如何？', '营业收入与净利润的同比增长表现有何差异？', '净利润率能说明什么？', '评估估值水平还缺少哪些证据？']
const categories = [
  { id: 'positive', title: '正面证据', subtitle: '有数据支持的上升变化', icon: ArrowUpRight },
  { id: 'negative', title: '负面证据', subtitle: '有数据支持的下降变化', icon: ArrowDownRight },
  { id: 'mixed', title: '矛盾与混合证据', subtitle: '需要结合观察的不同信号', icon: Layers3 },
  { id: 'unknown', title: '未知与待验证信息', subtitle: '明确现有证据的边界', icon: CircleHelp },
] as const

function EvidenceDrawer({ report, ids, title, description, close }: { report: ResearchReport; ids: string[]; title: string; description?: string; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [active, setActive] = useState(ids[0])
  useEffect(() => {
    const prior = document.activeElement as HTMLElement
    dialog.current?.showModal()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previousOverflow; prior?.focus() }
  }, [])
  const evidence = reportEvidence(report).find(item => item.evidence_id === active)
  const source = reportSources(report).find(item => item.source_id === evidence?.source_id)
  function field(label: string, value: string | null | undefined) { return <div className="detail-row" key={label}><dt>{label}</dt><dd>{value ?? '未提供'}</dd></div> }
  function selectEvidence(item: Evidence) { return <button className="input-ref" key={item.evidence_id} onClick={() => setActive(item.evidence_id)}><span>{item.original_field_name ?? (item.kind === 'source' ? '来源字段' : '计算指标')}<small>{periodText(item.reporting_period)} · {item.value ?? '暂不可用'} {unitText(item.unit)}</small></span><ChevronRight size={16} /></button> }
  return <dialog className="evidence-dialog" ref={dialog} onCancel={close} onClick={event => { if (event.target === event.currentTarget) close() }} aria-labelledby="drawer-title">
    <div className="drawer-body">
      <div className="flex items-center justify-between"><span className="eyebrow"><ShieldCheck size={15} /> 核验证据</span><button className="icon-button" aria-label="关闭证据面板" onClick={close}><X size={20} /></button></div>
      <h2 id="drawer-title">{title}</h2><p className="muted">{description ?? '沿计算过程追溯至原始数据字段。'}</p>
      {ids.length > 1 && <div className="evidence-tabs">{ids.map((id, index) => <button key={id} className={active === id ? 'selected' : ''} onClick={() => setActive(id)}>证据 {index + 1}</button>)}</div>}
      {!evidence ? <div className="notice">该限制尚无对应来源证据，当前应用未获取该维度的数据。</div> : <>
        <div className="drawer-label">{evidence.kind === 'calculation' ? '计算事实' : '原始来源字段'}<span className="pill">{evidence.status === 'available' ? '已获取' : '暂不可用'}</span></div>
        <dl>{field('证据 ID', evidence.evidence_id)}{field('数据来源', sourceName(evidence.data_source))}{field('原始 API 接口', evidence.endpoint)}{field('原始字段名', evidence.original_field_name ?? '派生指标，请查看下方计算输入的原始字段')}{field('JSON 路径', evidence.json_path ?? '派生指标，请查看下方计算输入的原始字段')}{field('报告期', periodText(evidence.reporting_period))}{field('报告期末', evidence.period_end)}{field('数值（完整精度）', evidence.value)}{field('单位', unitText(evidence.unit))}{field('计算公式', evidence.formula ?? '不适用：此项为原始来源数值')}{field('数据获取时间', formatDate(evidence.retrieved_at))}{field('原始获取时间戳', evidence.retrieved_at)}{evidence.reason && field('不可用原因', reasonText(evidence.reason))}</dl>
        {evidence.input_evidence_ids.length > 0 && <section className="drawer-section"><h3>计算输入</h3><p className="muted text-sm">输入顺序请结合公式核验；区间收益率为结束收盘价在前、开始收盘价在后。</p>{evidence.input_evidence_ids.map(id => <div key={id}><code className="ref-id">{id}</code>{reportEvidence(report).filter(item => item.evidence_id === id).map(selectEvidence)}</div>)}</section>}
        {evidence.kind === 'source' && <dl>{Object.entries(evidence.metadata_json_paths).map(([name, path]) => field(metadataLabel(name), path))}</dl>}
        {source && <section className="drawer-section"><h3>原始响应</h3><p className="muted text-sm">以下为未经修改的数据源 JSON，保留原始数值及已提供的披露日期。数据获取时间不等于披露时间。</p><details><summary>查看原始 JSON</summary><pre>{source.raw_json}</pre></details><dl>{field('来源 ID', source.source_id)}{field('SHA-256', source.sha256)}{field('报表口径', source.reporting_basis === 'consolidated' ? '合并报表' : source.reporting_basis === 'daily_unadjusted' ? '日线 · 不复权 · 人民币' : '报表口径待核验')}{field('单位核验', unitBasisText(source.unit_basis))}{field('接口说明', source.contract_url)}{field('计算版本', report.diagnosis.calculation_version)}{field('十进制计算精度', String(report.diagnosis.decimal_precision))}</dl></section>}
        {active !== ids[0] && <button className="secondary-button" onClick={() => setActive(ids[0])}>返回结论证据</button>}
      </>}
    </div>
  </dialog>
}

export default function App() {
  const [stocks, setStocks] = useState<Stock[]>([])
  const [stockCode, setStockCode] = useState<StockCode>('600519.SH')
  const stock = stocks.find(item => item.stock_code === stockCode)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  useEffect(() => {
    const request = new AbortController()
    void fetchStocks(request.signal).then(setStocks).catch(failure => { if (!request.signal.aborted) setCatalogError(requestErrorText(failure)) })
    return () => request.abort()
  }, [])
  const [question, setQuestion] = useState('')
  const [report, setReport] = useState<ResearchReport | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [phase, setPhase] = useState<'idle' | 'plan' | 'diagnose'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<{ ids: string[]; title: string; description?: string } | null>(null)
  const controller = useRef<AbortController | null>(null)
  const resultHeading = useRef<HTMLHeadingElement>(null)
  const busy = phase !== 'idle'
  useEffect(() => () => controller.current?.abort(), [])
  function selectStock(code: StockCode) {
    controller.current?.abort()
    controller.current = null
    setStockCode(code); setQuestion(''); setReport(null); setPlan(null); setError(null); setDrawer(null); setPhase('idle')
  }
  async function research(input = question) {
    if (!stock) return
    const value = input.trim()
    if (!value) { setError('请输入研究问题。'); return }
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    const timeout = window.setTimeout(() => current.abort(), 65000)
    setQuestion(value); setReport(null); setPlan(null); setDrawer(null); setError(null); setPhase('plan')
    try {
      const nextPlan = await fetchPlan(value, current.signal, stockCode)
      if (current.signal.aborted || controller.current !== current) return
      if (nextPlan.company_name !== stock.name || nextPlan.company_type !== stock.company_type) throw new Error('研究计划公司信息与股票目录不一致。')
      setPlan(nextPlan); setPhase('diagnose')
      const nextReport = await fetchResearch(value, current.signal, stockCode)
      if (current.signal.aborted || controller.current !== current) return
      if (nextReport.plan.company_name !== stock.name || nextReport.plan.company_type !== stock.company_type) throw new Error('报告公司信息与股票目录不一致。')
      setReport(nextReport); setPlan(nextReport.plan)
      window.setTimeout(() => { if (controller.current === current && !current.signal.aborted) resultHeading.current?.focus() }, 0)
    } catch (failure) {
      if (controller.current !== current) return
      setError(current.signal.aborted ? '请求超时，本次未生成报告，请重试。' : requestErrorText(failure))
    } finally { window.clearTimeout(timeout); if (controller.current === current) setPhase('idle') }
  }
  function inspect(ids: string[], title: string, description?: string) { setDrawer({ ids, title, description }) }
  const diagnosis = report?.diagnosis
  const source = diagnosis?.sources[0]
  const followUps = report?.follow_up_suggestions?.length ? report.follow_up_suggestions : (report?.follow_up_questions.map(followUpText).filter((item): item is string => item !== null) ?? []).map(question => ({ id: question, question, availability: 'supported' as const }))
  const focus = report ? researchFocus(report.question) : 'financial'
  const financialContent = report && diagnosis ? <section aria-label="年度财务分析">
    <h3 className="diagnosis-section-title">年度财务指标</h3>
          <div className="report-meta"><span><Database size={14} />{diagnosis.evidence[0] ? sourceName(diagnosis.evidence[0].data_source) : '数据来源暂不可用'}</span><span><FileSearch size={14} />{diagnosis.current_year ? `${diagnosis.current_year} 年度` : '报告期暂不可用'}{diagnosis.previous_year ? ` · 对比 ${diagnosis.previous_year} 年度` : ''}</span><span><Clock3 size={14} />{source ? `${formatDate(source.retrieved_at)}` : '获取时间暂不可用'}</span></div>
          <div className={`freshness ${report.freshness_status === 'stale' ? 'stale' : ''}`}><Clock3 size={15} /><p>{freshnessText(report)}</p></div>
          <div className="metric-grid">{['revenue_growth', 'net_profit_growth', 'net_profit_margin'].map(name => { const metric = diagnosis.metrics.find(item => item.name === name); const ev = diagnosis.evidence.find(item => item.evidence_id === metric?.evidence_id); return <button className="metric-card" key={name} onClick={() => inspect(metric ? [metric.evidence_id] : [], labels[name])}><div className="flex items-center justify-between"><span>{labels[name]}</span><PanelRightOpen size={15} /></div><strong>{metric ? formatMetric(metric) : '暂不可用'}</strong><p>{ev ? periodText(ev.reporting_period) : '报告期暂不可用'}</p><div className="metric-foot">{metric?.status === 'available' ? '计算事实' : reasonText(metric?.reason ?? null)}<ArrowUpRight size={13} /></div></button> })}</div>
  </section> : null
  const priceContent = report?.price_analysis ? <PriceSection prices={report.price_analysis} inspect={inspect} /> : null
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#ask"><span className="brand-mark"><ScanLine size={23} /></span>StockLens<span className="brand-dot" /></a>
      <div className="workspace-label">研究工作台</div>
      <a className="nav-item active" href="#ask"><Search size={18} />个股研究<span className="nav-dot" /></a>
      <a className="nav-item" href="#method"><BookOpen size={18} />研究方法</a>
      <div className="sidebar-note"><div className="tiny-logo"><ShieldCheck size={20} /></div><h3>以证据为先。</h3><p>每个数值都有来源，每项解读都有边界。</p><div className="flex items-center gap-2"><span className="status-dot" /> 当前支持 3 家 A 股公司</div></div>
      <div className="sidebar-footer"><div className="avatar">SL</div><div>StockLens 研究室<small>A 股研究</small></div><span className="pill">试用版</span></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb">工作台<ChevronRight size={14} /><span>个股研究</span></div><div className="topbar-right"><span className="source-label"><Database size={14} /> Fuyao 财务数据</span><span className="divider" /><span className="text-xs muted">以证据为先的研究</span></div></header>
      <main>
        <section className="intro" id="ask"><div className="eyebrow"><span className="status-dot" /> 从证据出发，理解企业经营</div><h1>看清企业经营，<br /><span>追溯每条结论。</span></h1><p>从一个问题开始，逐步核验财务证据。<br className="desktop-break" /> 看懂数据能够说明什么，也明确它无法回答什么。</p></section>
        <section className="research-box" aria-label="研究输入">
          <div className="research-box-top"><span className="research-label"><Sparkles size={17} /> 从这里开始研究</span><span className="pill">A 股 · 财务与历史价格</span></div>
          <form onSubmit={event => { event.preventDefault(); void research() }}>
            <label className="sr-only" htmlFor="stock">选择股票</label><div className="stock-row"><div className="company-monogram">{stock?.name.slice(0, 1) ?? '股'}</div><select id="stock" aria-label="选择股票" value={stockCode} disabled={!stocks.length} onChange={event => selectStock(event.target.value as StockCode)}>{stocks.length ? stocks.map(item => <option key={item.stock_code} value={item.stock_code}>{item.name} · {item.stock_code}</option>) : <option value="600519.SH">正在加载股票目录…</option>}</select><span className="stock-exchange">{stock?.exchange ?? '交易所待加载'}</span></div>
            <label className="sr-only" htmlFor="question">研究问题</label><textarea id="question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="关于这家企业，你希望了解什么？" maxLength={1000} rows={2} disabled={busy} />
            <div className="input-footer"><span><ShieldCheck size={14} /> 客观计算有依据，分析解读可追溯。</span><button className="primary-button" disabled={busy || !question.trim() || !stock} type="submit">{busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}{busy ? '研究中…' : '开始研究'}</button></div>
          </form>
          <div className="suggestions"><span>试着提问</span>{suggestions.map(item => <button disabled={busy} key={item} onClick={() => { setQuestion(item); document.getElementById('question')?.focus() }}>{item}<ArrowUpRight size={12} /></button>)}</div>
        </section>
        <div className="journey" aria-label="研究流程">{['提问', '规划', '诊断', '核验', '探索'].map((step, index) => <div key={step} className={(report || index === 0 || (plan && index <= 2)) ? 'reached' : ''}><span>{report && index < 3 ? <Check size={12} /> : `0${index + 1}`}</span>{step}{index < 4 && <div className="journey-line" />}</div>)}</div>
        {catalogError && <div role="alert" className="error-box">{catalogError}</div>}
        {error && <div role="alert" className="error-box"><CircleHelp size={20} /><div><h3>本次研究未能完成</h3><p>{error}</p><button className="text-link" disabled={busy} onClick={() => void research()}>重试 <ArrowRight size={14} /></button></div></div>}
        {plan && <section className="plan-section" aria-label="研究计划"><div className="section-kicker">01 / 规划</div><div className="section-heading"><h2>围绕问题，明确研究重点</h2><span className="pill">基于规则选择维度</span></div><div className="muted text-sm" aria-label="公司分类与诊断重点">
          <p><strong>公司名称：</strong><span>{plan.company_name}</span></p>
          <p><strong>研究分类：</strong><span>{plan.company_type}</span></p>
          <p><strong>分类依据：</strong>{plan.company_type_basis} <a className="company-profile-link" href={plan.classification_source_url} target="_blank" rel="noopener noreferrer"><span>查看公司简介</span><ExternalLink size={14} aria-hidden="true" /></a></p>
          <p><strong>当前诊断重点：</strong>{plan.dimensions.filter(item => item.availability === 'available').map(item => dimensionLabels[item.id] ?? '待核验维度').join('、') || '暂无已支持维度'}{plan.dimensions.some(item => item.availability === 'unavailable') && '；未支持的维度见下方待验证说明。'}</p>
          <p>研究分类根据企业公开业务资料人工设置，不代表官方行业分类。</p>
        </div><div className="dimension-grid">{plan.dimensions.map(item => <article key={item.id}><div className="flex items-center justify-between"><h3>{dimensionLabels[item.id] ?? '待核验维度'}</h3><span className={item.availability === 'available' ? 'availability' : 'muted text-xs'}>{item.availability === 'available' ? (item.id === 'price' ? '历史日线价格' : '年度财务背景') : '暂不可用'}</span></div><p>{dimensionReason(item)}</p></article>)}</div>{plan.safety_notice && <div className="notice">{safetyNotice}</div>}</section>}
        {busy && <section role="status" className="loading-state"><LoaderCircle className="spin" size={23} /><div><h3>{phase === 'plan' ? '正在选择相关研究维度' : '正在获取财务报表并核验证据'}</h3><p>获取真实财务数据 → 精确计算指标 → 核验证据 → 按配置提供 AI 解读，不使用占位财务结果。</p></div></section>}
        {report && diagnosis && <div className="report" id="report">
          <div className="report-top"><div><div className="section-kicker">02 / 诊断</div><h2 ref={resultHeading} tabIndex={-1}>个股研究简报</h2><p className="report-question">“{report.question}”</p></div><span className="report-status"><span className="status-dot" />{focus === 'price' ? (report.price_analysis?.observations.length ? '历史价格已获取 · 覆盖范围待核验' : '历史价格暂不可用') : diagnosis.status === 'complete' ? '财务指标已获取' : diagnosis.status === 'partial' ? '部分财务证据可用' : '财务数据暂不可用'}</span></div>
          {focus === 'price' ? <>
            {priceContent}
            <details className="supplementary-context"><summary>补充财务背景</summary>{financialContent}</details>
          </> : <>
            {financialContent}
            {priceContent && (focus === 'both' ? priceContent : <details className="supplementary-context"><summary>补充历史价格背景</summary>{priceContent}</details>)}
          </>}
          <section className="summary-section"><div className="summary-icon"><Sparkles size={21} /></div><div className="summary-content"><div className="section-heading"><h3>研究解读</h3><span className="pill">{report.interpretation_mode === 'llm' ? 'AI 选取 · 证据已核验' : '客观事实摘要'}</span></div><p className="muted text-sm">{interpretationStatus(report.interpretation_status)}</p>{report.interpretation_mode === 'llm' ? report.interpretations.map(item => <button className="summary-line" key={item.id} onClick={() => inspect(item.evidence_ids, '有证据约束的分析解读', interpretationText(item.text))}><span className="type-label">分析解读</span><span>{interpretationText(item.text)}</span><ArrowUpRight size={15} /></button>) : report.observations.length ? report.observations.map(item => <button className="summary-line" key={item.id} onClick={() => inspect(item.evidence_ids, findingCopy(item, report).title)}><span className="type-label">客观事实</span><span>{findingCopy(item, report).text}</span><ArrowUpRight size={15} /></button>) : <p>暂无通过核验的数值事实，请查看下方数据限制。</p>}</div></section>
          <section id="evidence"><div className="section-kicker">03 / 核验</div><div className="section-heading"><h2>结合背景，逐条核验证据。</h2><span className="muted text-xs">点击任一条目，查看来源与计算依据</span></div><p className="muted section-description">正负方向仅描述相应区间的财务或价格变化，不代表评级或投资建议。</p><div className="evidence-grid">{categories.map(category => { const items = report.findings.filter(item => item.category === category.id); const Icon = category.icon; return <section className={`evidence-category ${category.id}`} key={category.id}><div className="category-heading"><span className="category-icon"><Icon size={18} /></span><h3>{category.title}</h3><span className="count">{items.length}</span></div><p className="category-subtitle">{category.subtitle}</p>{items.length ? items.map(item => <button className="finding" key={item.id} onClick={() => inspect(item.evidence_ids, findingCopy(item, report).title, findingCopy(item, report).text)}><div><span className="type-label">{item.kind === 'observation' ? '客观事实' : '待核验信息'}</span><ArrowUpRight size={14} /></div><h4>{findingCopy(item, report).title}</h4><p>{findingCopy(item, report).text}</p><span className="finding-source">{item.evidence_ids.length ? `${item.evidence_ids.length} 条证据引用` : '数据覆盖限制'}<ChevronRight size={12} /></span></button>) : <div className="empty-category"><span>证据不足，暂未形成相关判断</span><p>所选维度下暂无证据支持的相关结论。此处为空，不代表相关情况不存在。</p></div>}</section> })}</div></section>
          {diagnosis.issues.length > 0 && <details className="data-issues"><summary>数据质量说明（{diagnosis.issues.length}）</summary><ul>{diagnosis.issues.map((issue, index) => <li key={index}>{reasonText(issue)}</li>)}</ul></details>}
          {diagnosis.evidence.length === 0 && <div className="notice">未返回证据记录，暂时无法核验来源。</div>}
          <section className="explore-section"><div><div className="section-kicker">04 / 探索</div><h2>沿着问题，继续研究。</h2><p className="muted">点击问题，发起新一轮分析并生成对应研究计划。{report.follow_up_mode === 'llm' ? ' 建议由 AI 从审核目录中选取。' : ' 建议按本轮上下文确定性排序。'}</p></div><div className="follow-ups">{followUps.length ? followUps.map(item => <button key={item.id} disabled={busy} onClick={() => void research(item.question)}>{item.question}{item.availability === 'pending' && '（待验证）'}<ArrowRight size={17} /></button>) : <p className="muted">暂无可用的后续研究问题。</p>}</div></section>
          <p className="disclaimer"><ShieldCheck size={15} />{disclaimer}</p>
        </div>}
        {!report && !busy && !error && <section className="empty-report"><div className="empty-icon"><FileSearch size={27} /></div><h2>好的研究，从一个具体问题开始。</h2><p>研究简报将在这里呈现真实财务指标、<br className="desktop-break" /> 明确的数据限制，以及每条结论的来源。</p><div className="empty-tags"><span><Check size={13} /> 真实来源数据</span><span><Check size={13} /> 确定性计算</span><span><Check size={13} /> 可核验的证据</span></div></section>}
        <section className="method-section" id="method"><div><span className="eyebrow"><FlaskConical size={14} /> STOCKLENS 研究方法</span><h2>围绕问题展开，<br />以真实证据为本。</h2></div><div className="method-items"><article><span>01</span><h3>先看事实，再作解读</h3><p>指标由 Python 确定性计算。AI 仅选取已核验的解读；不可用时回退为客观事实摘要。</p></article><article><span>02</span><h3>未知之处，明确标注</h3><p>缺失的估值、价格覆盖范围和现金流证据均明确展示，不用推测填补。</p></article><article><span>03</span><h3>每条结论，均可追溯</h3><p>通过证据 ID、原始字段、日期、单位与公式，逐步核验研究依据。</p></article></div></section>
        <footer className="page-footer"><span>StockLens <span className="muted">/ 以证据为先的 A 股研究</span></span><span>让研究更清晰。</span></footer>
      </main>
    </div>
    {report && drawer && <EvidenceDrawer key={drawer.title + drawer.ids.join()} report={report} {...drawer} close={() => setDrawer(null)} />}
  </div>
}
