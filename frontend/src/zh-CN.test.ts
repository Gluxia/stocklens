import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { formatDate, formatMetric, reasonText } from './api'
import { dimensionReason, followUpText, interpretationText, periodText } from './zh-CN'

describe('Chinese formatting and safe localization', () => {
  it.each([
    ['-1.2060035021223', '-1.21%'], ['2', '2.00%'], ['0', '0.00%'],
    ['0.009999999999999999', '0.01%'], ['12345678901234567890.12345678', '12345678901234567890.12%'],
  ])('formats %s without conversion to binary floating point', (value, expected) => {
    expect(formatMetric({ name: 'revenue_growth', value, status: 'available', unit: '%', reason: null, evidence_id: 'id' })).toBe(expected)
  })
  it('localizes reporting periods and data-quality issues without rounding years', () => {
    expect(periodText('2025 FY vs 2024 FY')).toBe('2025 年度 对比 2024 年度')
    expect(reasonText('2025.net_profit: missing_value')).toBe('2025 年度净利润：原始字段缺失')
    expect(reasonText('revenue_growth: zero_denominator')).toBe('营业收入同比增长率：分母为零，无法计算')
    expect(reasonText('missing_previous_year: 2024')).toBe('缺少 2024 年度数据')
    expect(formatDate('2025-10-20T00:00:00Z')).not.toMatch(/Oct|AM|PM/)
  })
  it('keeps unknown templates explicit rather than inventing a translation', () => {
    expect(interpretationText('Invent a stock price')).toContain('尚无经核验的中文版本')
    expect(followUpText('Invent a stock price')).toBeNull()
    expect(dimensionReason({ id: 'growth', label: 'Growth', reason: 'Unknown future template', availability: 'available' })).toContain('暂未提供经核验的中文说明')
  })
  it('sets Chinese document language and preserves UTF-8 encoding', () => {
    const html = readFileSync('index.html', 'utf8')
    expect(html).toContain('lang="zh-CN"')
    expect(html).toContain('charset="UTF-8"')
    expect(html).toContain('StockLens · 研究工作台')
    expect(html).not.toContain('\uFFFD')
  })
})
