/** Background dimensions added by the backend do not imply explicit user intent. */
export function researchFocus(question: string): 'price' | 'financial' | 'both' {
  const text = question.toLocaleLowerCase('zh-CN')
  const price = /股价|走势|行情|涨跌|价格|\b(price|trend|momentum)\b/.test(text)
  const financialText = text.replace(/(?:股价|价格)\s*增长|price\s+growth/g, '')
  const financial = /财务|经营|业绩|销售|营收|收入|利润|盈利|增长|现金流|负债|financial|operating performance|revenue|sales|profit|margin|earnings|growth|cash.flow|debt/.test(financialText)
  return price ? (financial ? 'both' : 'price') : 'financial'
}
