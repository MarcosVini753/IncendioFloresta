import type { RiskV4Cell, RiskV4Model, RiskV4Product } from '../types/riskV4'
import { RISK_V4_CLASSES, RISK_V4_MODELS } from '../types/riskV4'
import { riskV4Base } from './riskV4'

export const SUMMARY_METHODS = [
  { id: 'mean', label: 'Média dos percentis', advanced: false, description: 'Cada pixel válido tem o mesmo peso. O número é a média das posições dos pixels no estado.', formula: 'Σ índice do pixel / n' },
  { id: 'mode', label: 'Moda — classe mais frequente', advanced: false, description: 'A cor representa a classe com mais pixels. Mais frequente não significa maioria absoluta.', formula: 'classe com maior contagem; empate pela menor classe' },
  { id: 'median', label: 'Mediana', advanced: false, description: 'Valor do pixel na posição central dos índices ordenados, sem interpolação.', formula: 'índice ordenado na posição ceil(0,5 × n)' },
  { id: 'concentration', label: 'Concentração de índices ≥90', advanced: false, description: 'Parcela dos pixels válidos em Alto ou Muito alto. Aproxima cobertura da área, não chance de incêndio.', formula: '100 × (n Alto + n Muito alto) / n' },
  { id: 'p75', label: 'P75', advanced: true, description: 'Quartil superior dos índices ordenados. Realça valores altos e não representa necessariamente a maioria.', formula: 'índice ordenado na posição ceil(0,75 × n)' },
  { id: 'area_mean', label: 'Média ponderada por área', advanced: true, description: 'A área geodésica WGS84 de cada pixel determina seu peso. As áreas locais são quase iguais.', formula: 'Σ (área do pixel × índice) / área válida total' },
  { id: 'local_rarity', label: 'Média por raridade local', advanced: true, description: 'Cada classe ocupada recebe o mesmo peso total, independentemente de sua quantidade de pixels. Índice experimental.', formula: 'Σ média de cada classe ocupada / número de classes ocupadas' },
  { id: 'state_rarity', label: 'Média por raridade estadual', advanced: true, description: 'Cada pixel recebe peso inverso à frequência estadual de sua classe no mesmo ano e modelo. Índice experimental.', formula: 'Σ (n da classe × média da classe / frequência estadual) / Σ (n da classe / frequência estadual)' },
  { id: 'state_cdf', label: 'CDF estadual do valor médio', advanced: true, description: 'Posição do valor médio da banda 1 perante os pixels estaduais. Usa CDF exata ≤, diferente dos empates do histograma recebido; não ranqueia grupos.', formula: '100 × pixels estaduais com valor ≤ valor médio do grupo / N estadual' },
] as const
export type SummaryMethod = typeof SUMMARY_METHODS[number]['id']
export const summaryDefinition = (method: SummaryMethod) => SUMMARY_METHODS.find((m) => m.id === method)!
export const parseSummaryMethod = (value: string | null): SummaryMethod =>
  SUMMARY_METHODS.some((m) => m.id === value) ? value as SummaryMethod : 'mean'
export const needsStats = (method: SummaryMethod) => !['mean', 'mode', 'concentration'].includes(method)
export const COVERAGE_STOPS = [
  { value: 0, color: '#ffffcc' }, { value: 25, color: '#fed976' },
  { value: 50, color: '#fd8d3c' }, { value: 75, color: '#e31a1c' },
  { value: 100, color: '#800026' },
]
export interface GroupModelStats {
  median: number
  p75: number
  area_mean: number
  local_rarity: number
  state_rarity: number
  state_cdf: number
  state_cdf_count_le: number
  class_counts: number[]
  class_means: (number | null)[]
}
export interface AggregationStats {
  schema_version: '1.0'
  product: 'risk_v4_aggregation_stats'
  year: 2025 | 2026
  source_identity: string
  input_sha256: Record<string, string>
  counts: { groups: number; source_pixels: number }
  state_class_counts: Record<RiskV4Model, number[]>
  state_frequencies: Record<RiskV4Model, number[]>
  groups: Record<string, {
    n_source_pixels: number
    valid_area_m2: number
    models: Record<RiskV4Model, GroupModelStats>
  }>
}
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const index = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 100
const integer = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0
const close = (a: number, b: number) => Math.abs(a - b) <= 1e-7
export function classCounts(cell: RiskV4Cell, model: RiskV4Model): number[] {
  return RISK_V4_CLASSES.map((c) => Math.round(Number(cell[`share_${model}_${c.id}`]) * cell.n_source_pixels))
}
export function validateAggregationStats(value: unknown, product: RiskV4Product): AggregationStats {
  const fail = (): never => { throw new Error('Estatísticas de resumo inválidas ou incompatíveis com este produto.') }
  if (!record(value) || value.schema_version !== '1.0' || value.product !== 'risk_v4_aggregation_stats' ||
      value.year !== product.manifest.year || value.source_identity !== product.manifest.provenance.identity ||
      !record(value.counts) || value.counts.groups !== product.cells.features.length ||
      value.counts.source_pixels !== product.manifest.counts.source_pixels ||
      value.quantile_method !== 'inverted_cdf' || value.area_method !== 'WGS84_geodesic_pixel_corners' ||
      value.cdf_method !== 'empirical_less_or_equal' || !record(value.groups) ||
      Object.keys(value.groups).length !== product.cells.features.length ||
      !record(value.input_sha256) || !['manifest.json', 'index.json', 'grid.geojson'].every((k) =>
        typeof value.input_sha256 === 'object' && /^[a-f0-9]{64}$/.test(String((value.input_sha256 as Record<string, unknown>)[k])))) fail()
  const stats = value as unknown as AggregationStats
  for (const model of RISK_V4_MODELS) {
    const frequency = stats.state_frequencies?.[model]
    const statewide = stats.state_class_counts?.[model]
    if (!Array.isArray(frequency) || frequency.length !== 5 || !Array.isArray(statewide) || statewide.length !== 5 ||
        !frequency.every((f) => typeof f === 'number' && Number.isFinite(f) && f >= 0 && f <= 1) ||
        !statewide.every(integer)) fail()
    const accumulated = [0, 0, 0, 0, 0]
    for (const { properties: cell } of product.cells.features) {
      const group = stats.groups[cell.id]
      const s = group?.models?.[model]
      const expected = classCounts(cell, model)
      if (!group || group.n_source_pixels !== cell.n_source_pixels || !Number.isFinite(group.valid_area_m2) || group.valid_area_m2 <= 0 || !s ||
          ![s.median, s.p75, s.area_mean, s.local_rarity, s.state_rarity, s.state_cdf].every(index) || s.median > s.p75 ||
          !integer(s.state_cdf_count_le) || s.state_cdf_count_le > stats.counts.source_pixels ||
          !close(s.state_cdf, 100 * s.state_cdf_count_le / stats.counts.source_pixels) ||
          !Array.isArray(s.class_counts) || s.class_counts.length !== 5 ||
          !s.class_counts.every((n, i) => integer(n) && n === expected[i]) ||
          !Array.isArray(s.class_means) || s.class_means.length !== 5) fail()
      let sum = 0, local = 0, occupied = 0, weighted = 0, weight = 0
      for (let i = 0; i < 5; i++) {
        const n = s.class_counts[i], mean = s.class_means[i]
        accumulated[i] += n
        if (!n) { if (mean !== null) fail(); continue }
        const c = RISK_V4_CLASSES[i]
        if (!index(mean) || mean < c.lower || (i < 4 ? mean >= c.upper : mean > c.upper) || frequency[i] === 0) fail()
        const m = mean as number
        sum += n * m; local += m; occupied++; weighted += n * m / frequency[i]; weight += n / frequency[i]
      }
      if (!close(sum / cell.n_source_pixels, cell[`percentile_${model}`]) ||
          !close(local / occupied, s.local_rarity) || !close(weighted / weight, s.state_rarity)) fail()
      for (const [q, v] of [[.5, s.median], [.75, s.p75]]) {
        const target = Math.ceil(q * cell.n_source_pixels)
        let cumulative = 0
        const cls = s.class_counts.findIndex((n) => (cumulative += n) >= target)
        if (summaryClass(v) !== cls) fail()
      }
    }
    if (!accumulated.every((n, i) => n === statewide[i] && close(n / stats.counts.source_pixels, frequency[i]))) fail()
  }
  return stats
}
export async function loadAggregationStats(product: RiskV4Product, signal?: AbortSignal): Promise<AggregationStats> {
  const response = await fetch(`${riskV4Base(product.manifest.year)}aggregation-stats.json`, { signal })
  if (!response.ok || !response.headers.get('content-type')?.includes('json'))
    throw new Error('Não foi possível carregar as estatísticas adicionais deste ano.')
  return validateAggregationStats(await response.json(), product)
}
export const summaryClass = (value: number) => RISK_V4_CLASSES.findIndex((c, i) => value >= c.lower && (i === 4 || value < c.upper))
export function summarize(cell: RiskV4Cell, model: RiskV4Model, method: SummaryMethod, stats: AggregationStats | null) {
  const counts = classCounts(cell, model), n = cell.n_source_pixels
  const maximum = Math.max(...counts), dominantClass = counts.indexOf(maximum)
  const concentration = 100 * (counts[3] + counts[4]) / n
  const extra = stats?.groups[cell.id]?.models[model]
  const value = method === 'mean' ? cell[`percentile_${model}`]
    : method === 'mode' ? null : method === 'concentration' ? concentration : extra?.[method] ?? null
  return { value, classIndex: method === 'mode' ? dominantClass : value === null || method === 'concentration' ? null : summaryClass(value),
    dominantShare: maximum / n, concentration, mixed: maximum <= n / 2,
    tied: counts.filter((v) => v === maximum).length > 1, counts }
}
export function displayGrid(product: RiskV4Product, model: RiskV4Model, method: SummaryMethod, stats: AggregationStats | null) {
  return { ...product.cells, features: product.cells.features.map((feature) => {
    const result = summarize(feature.properties, model, method, stats)
    return { ...feature, properties: { ...feature.properties, display_value: result.value, display_class: result.classIndex } }
  }) }
}
