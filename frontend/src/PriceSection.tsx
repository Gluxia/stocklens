import Decimal from 'decimal.js'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiErrorText, formatDate, type PriceAnalysis } from './api'

const labels: Record<string, string> = { price_return: '观测区间价格涨跌幅', price_high: '观测区间最高价', price_low: '观测区间最低价', price_count: '有效交易观测数' }
const issues: Record<string, string> = {
  coverage_unverified: '尚未核验交易日历，无法确认数据覆盖完整性。', no_price_data: '该请求区间未返回有效价格。',
  invalid_price_date: '部分记录日期无效，已排除。', invalid_price_value: '部分价格缺失、非正或无效，已排除。',
  invalid_price_range: '部分记录开高低收不一致，已排除。', out_of_range_price: '已排除请求范围外的记录。',
  stale_price_data: '最新返回价格距请求结束日超过 7 天，可能已过时。', insufficient_price_observations: '不足两条有效观测，无法计算区间涨跌幅。',
  duplicate_price_date: '存在重复日期，无法确定适用的价格记录。', unverified_price_metadata: '股票、日线周期或复权方式未通过核验。',
}
export default function PriceSection({ prices, inspect }: { prices: PriceAnalysis; inspect: (ids: string[], title: string) => void }) {
  // Conversion to Number is chart-only; source evidence retains full decimal precision.
  const data = prices.observations.map(o => ({ date: o.date, close: Number(o.close), evidence_ids: o.evidence_ids }))
  return <section className="price-section" aria-label="历史股价分析">
    <div className="section-heading"><h2>历史股价表现</h2><span className="pill">日线 · 不复权 · 人民币元</span></div>
    <p className="muted">默认范围：过去一个自然月，不含今日未结束日线。请求区间：{prices.requested_start} 至 {prices.requested_end}（上海时区）。暂不解析其他时间范围。</p>
    <p className="muted">实际观测：{prices.actual_start && prices.actual_end ? `${prices.actual_start} 至 ${prices.actual_end}` : '暂无'} · 来源：Fuyao（扶摇）{prices.retrieved_at ? ` · 获取于 ${formatDate(prices.retrieved_at)}` : ''}</p>
    {prices.error_code && <p role="status" className="notice">{issues[prices.error_code] ?? apiErrorText(prices.error_code, 502)}未展示替代价格数据。</p>}
    {prices.issues.length > 0 && <ul className="price-notices">{[...new Set(prices.issues)].map(issue => <li key={issue}>{issues[issue] ?? '数据源暂不可用，请稍后重试。'}</li>)}</ul>}
    {data.length ? <>
      <div className="price-chart" role="img" aria-label="历史收盘价折线图，具体数值可在下方价格记录中核验"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 12, right: 20, bottom: 8, left: 10 }}><CartesianGrid stroke="#E5E8EF" strokeDasharray="3 3" /><XAxis dataKey="date" tick={{ fontSize: 13 }} minTickGap={38} /><YAxis domain={['auto', 'auto']} tick={{ fontSize: 13 }} width={72} /><Tooltip formatter={value => [`${new Decimal(String(value)).toFixed(2)} 元`, '收盘价']} /><Line type="linear" dataKey="close" name="收盘价" stroke="#C92339" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>
      <div className="metric-grid price-metrics">{prices.metrics.map(m => <button key={m.name} className="metric-card" onClick={() => inspect([m.evidence_id], labels[m.name])}><span>{labels[m.name]}</span><strong>{m.value !== null && m.status === 'available' ? `${new Decimal(m.value).toFixed(m.name === 'price_count' ? 0 : 2)}${m.unit === '%' ? '%' : m.unit === 'observations' ? ' 条' : ' 元'}` : '暂不可用'}</strong><p>点击核验原始数值与计算公式</p></button>)}</div>
      <details className="data-issues"><summary>查看每日价格记录与证据（{data.length} 条）</summary><div className="price-observations">{prices.observations.map(o => <button className="secondary-button" key={o.date} onClick={() => inspect(o.evidence_ids, `${o.date} 日线价格`)}>{o.date} · 收盘 {new Decimal(o.close).toFixed(2)} 元</button>)}</div></details>
    </> : <div className="notice">暂无通过核验的历史价格，不生成价格图表。</div>}
    <p className="muted">涨跌幅 =（结束收盘价 ÷ 开始收盘价 − 1）× 100%。最高／最低为有效日线的最高／最低成交价；不含分红收益，不说明价格变化的成因。图表仅连接返回的观测点，不补齐缺失交易日。</p>
  </section>
}
