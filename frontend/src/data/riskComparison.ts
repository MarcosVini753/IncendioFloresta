import type { RiskV4Values } from '../types/riskV4'

// Diferença entre posições percentílicas, nunca entre probabilidades ou valores brutos.
// Um número positivo indica RF acima de XGBoost no ranking daquele ano.
export const rankingDifference = (values: RiskV4Values): number =>
  values.percentile_random_forest - values.percentile_xgboost

export const COMPARISON_STOPS = [
  { value: -40, color: '#406d94' },
  { value: -15, color: '#81a6bc' },
  { value: -4, color: '#d3e1e5' },
  { value: 0, color: '#f0f1eb' },
  { value: 4, color: '#f3dfc2' },
  { value: 15, color: '#dbac7c' },
  { value: 40, color: '#af6549' },
] as const

export const formatRankingDifference = (difference: number): string => {
  if (Math.abs(difference) < 0.05) return 'Praticamente iguais'
  const amount = Math.abs(difference).toLocaleString('pt-BR', { maximumFractionDigits: 1 })
  return difference > 0
    ? `Random Forest: ${amount} pontos acima`
    : `XGBoost: ${amount} pontos acima`
}

export const comparisonColorExpression = [
  'interpolate',
  ['linear'],
  ['-', ['get', 'percentile_random_forest'], ['get', 'percentile_xgboost']],
  ...COMPARISON_STOPS.flatMap((stop) => [stop.value, stop.color]),
]
