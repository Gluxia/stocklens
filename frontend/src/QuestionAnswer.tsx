import type { Answer } from './api'
import { periodText } from './zh-CN'

export const answerStatusLabels = { answered: '已回答', partial: '部分回答', unavailable: '暂无法回答' } as const

export default function QuestionAnswer({ answer, inspect }: { answer: Answer; inspect: (ids: string[], title: string, description?: string) => void }) {
  const { scope } = answer
  return <section className="question-answer" aria-labelledby="question-answer-title">
    <div className="section-heading"><h3 id="question-answer-title">针对你的问题</h3><span className="pill">{answerStatusLabels[answer.answer_status]}</span></div>
    <p className="direct-answer">{answer.direct_answer}</p>
    {answer.missing_evidence.length > 0 && <div className="answer-gaps"><h4>尚缺的证据</h4><ul>{answer.missing_evidence.map(gap => <li key={gap.code}>{gap.description}</li>)}</ul></div>}
    <div className="answer-scope">
      <h4>回答范围与边界</h4>
      {scope.reporting_periods.length > 0 && <p>财务报告期：{scope.reporting_periods.map(periodText).join('；')}</p>}
      {scope.price_requested_start && <p>行情请求区间：{scope.price_requested_start} 至 {scope.price_requested_end}（北京时间）</p>}
      {scope.price_observed_start && <p>实际有效观测区间：{scope.price_observed_start} 至 {scope.price_observed_end}（北京时间）</p>}
      {scope.assumptions.map((assumption, index) => <p key={index}>{assumption}</p>)}
      {!scope.reporting_periods.length && !scope.price_requested_start && !scope.price_observed_start && !scope.assumptions.length && <p>仅针对当前问题及本轮已核验的数据作答。</p>}
    </div>
    {answer.supporting_evidence_ids.length > 0 && <button className="answer-evidence" onClick={() => inspect(answer.supporting_evidence_ids, '主答案依据', answer.direct_answer)}>查看依据</button>}
  </section>
}
