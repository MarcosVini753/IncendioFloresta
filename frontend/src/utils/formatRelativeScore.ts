const percentFormatter = new Intl.NumberFormat('pt-BR', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

export function formatRelativeScorePercent(value: number) {
  return percentFormatter.format(value)
}

export function formatModelScorePercent(value: number) {
  const percent = value * 100
  if (value > 0 && percent < 0.0001) return '<0,0001%'
  return new Intl.NumberFormat('pt-BR', {
    style: 'percent', minimumFractionDigits: 1,
    maximumFractionDigits: percent < 0.1 ? 4 : percent < 1 ? 3 : 1,
  }).format(value)
}

export function formatRiskPercentile(value: number) {
  return new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value)
}
