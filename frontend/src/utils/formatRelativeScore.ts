const percentFormatter = new Intl.NumberFormat('pt-BR', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

export function formatRelativeScorePercent(value: number) {
  return percentFormatter.format(value)
}
