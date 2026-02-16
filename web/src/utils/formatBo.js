export function formatBoType(boType) {
  if (boType == null || boType === '') return 'Bo?'
  const s = String(boType).toLowerCase()
  if (s.includes('5')) return 'Bo5'
  if (s.includes('3')) return 'Bo3'
  return 'Bo?'
}

export function resolveBoType(boType, score1, score2) {
  const fromApi = formatBoType(boType)
  if (fromApi !== 'Bo?') return fromApi
  const s1 = Number(score1)
  const s2 = Number(score2)
  if (Number.isFinite(s1) && Number.isFinite(s2) && s1 + s2 > 3) return 'Bo5'
  if (Number.isFinite(s1) && Number.isFinite(s2)) return 'Bo3'
  return 'Bo?'
}

const BO3_ORDER = ['2-0', '2-1', '1-2', '0-2']
const BO5_ORDER = ['3-0', '3-1', '3-2', '2-3', '1-3', '0-3']

export function inferSeriesFormatFromScoreProbs(scoreProbs) {
  if (!scoreProbs || typeof scoreProbs !== 'object') return 'Bo3'
  const keys = Object.keys(scoreProbs)
  const hasThree = keys.some((k) => k.startsWith('3-') || k.endsWith('-3'))
  return hasThree ? 'Bo5' : 'Bo3'
}

export function seriesChartData(scoreProbs, format) {
  if (!scoreProbs || typeof scoreProbs !== 'object') return []
  const order = format === 'Bo5' ? BO5_ORDER : BO3_ORDER
  const ordered = order.filter((s) => scoreProbs[s] != null)
  const rest = Object.keys(scoreProbs).filter((s) => !order.includes(s)).sort()
  const allKeys = [...ordered, ...rest]
  return allKeys.map((score) => ({
    score,
    probability: Number(((scoreProbs[score] ?? 0) * 100).toFixed(2))
  }))
}
