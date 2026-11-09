import { afterEach, describe, expect, it, vi } from 'vitest'
import m25 from '../../../incendio/produtos/risco/v6/2025/manifest.json'
import g25 from '../../../incendio/produtos/risco/v6/2025/grid.geojson?raw'
import b25 from '../../../incendio/produtos/risco/v6/2025/boundary.geojson?raw'
import i25 from '../../../incendio/produtos/risco/v6/2025/index.json'
import s25Text from '../../../incendio/produtos/risco/v6/2025/aggregation-stats.json?raw'
import m26 from '../../../incendio/produtos/risco/v6/2026/manifest.json'
import g26 from '../../../incendio/produtos/risco/v6/2026/grid.geojson?raw'
import b26 from '../../../incendio/produtos/risco/v6/2026/boundary.geojson?raw'
import i26 from '../../../incendio/produtos/risco/v6/2026/index.json'
import s26Text from '../../../incendio/produtos/risco/v6/2026/aggregation-stats.json?raw'
import { validateRiskV6Manifest, validateRiskV6Product } from './riskV6'
import { displayGrid, loadAggregationStats, parseSummaryMethod, summarize, validateAggregationStats, type AggregationStats } from './riskAggregation'
import type { RiskV6Cell } from '../types/riskV6'

const p25 = validateRiskV6Product(validateRiskV6Manifest(m25), JSON.parse(g25), JSON.parse(b25), i25)
const p26 = validateRiskV6Product(validateRiskV6Manifest(m26), JSON.parse(g26), JSON.parse(b26), i26)
const s25 = JSON.parse(s25Text) as AggregationStats
const s26 = JSON.parse(s26Text) as AggregationStats
afterEach(() => vi.unstubAllGlobals())

describe('resumos dos pixels científicos', () => {
  it('valida ambos os anos, todos os grupos e os dois modelos da v6', () => {
    expect(validateAggregationStats(s25, p25).year).toBe(2025)
    expect(validateAggregationStats(s26, p26).year).toBe(2026)
  })
  it('reproduz os nove resultados e preserva campos científicos', () => {
    const stats = validateAggregationStats(s26, p26)
    const cell = p26.cells.features.find((f) => f.properties.id === 'AC-5KM-E105N1773')!.properties
    const expected = { mean: 86.98490649364909, median: 94.470703125, p75: 98.50530242919922, concentration: 58.44187675070028, area_mean: 86.9847612700371, local_rarity: 83.87652609306727, state_rarity: 93.6610835989248, state_cdf: 98.28536333726797 } as const
    for (const [method, value] of Object.entries(expected)) {
      expect(summarize(cell, 'random_forest', method as keyof typeof expected, stats).value).toBeCloseTo(value, 5)
    }
    const mode = summarize(cell, 'random_forest', 'mode', null)
    expect(mode.value).toBeNull()
    expect(mode.classIndex).toBe(4)
    expect(mode.dominantShare).toBeCloseTo(.49327731092436977)
    expect(mode.mixed).toBe(true)
    const grid = displayGrid(p26, 'random_forest', 'median', stats)
    const displayed = grid.features.find((f) => f.properties.id === cell.id)!
    expect(displayed.properties.percentile_random_forest).toBe(cell.percentile_random_forest)
    expect(displayed.properties.display_value).toBeCloseTo(94.470703125)
    expect(cell).not.toHaveProperty('display_value')
  })
  it('basic methods work without the additional file and ties choose the lower class', () => {
    const cell: RiskV6Cell = { id: 'tie', centroid: [0,0], n_source_pixels: 2, aggregation: 'mean', value_random_forest: 1, percentile_random_forest: 60, value_xgboost: 2, percentile_xgboost: 70,
      share_random_forest_very_low: .5, share_random_forest_low: .5, share_random_forest_moderate: 0, share_random_forest_high: 0, share_random_forest_very_high: 0 }
    expect(summarize(cell, 'random_forest', 'mode', null)).toMatchObject({ classIndex: 0, tied: true, mixed: true })
    expect(summarize(cell, 'random_forest', 'concentration', null).value).toBe(0)
    expect(summarize(cell, 'random_forest', 'mean', null).value).toBe(60)
    expect(summarize(cell, 'random_forest', 'median', null).value).toBeNull()
    expect(parseSummaryMethod(null)).toBe('mean')
    expect(parseSummaryMethod('unknown')).toBe('mean')
    expect(parseSummaryMethod('p75')).toBe('p75')
  })
  it('reproduz XGBoost diretamente dos GeoTIFFs originais dos dois anos', () => {
    for (const [product, raw, expected] of [
      [p25, s25, [87.58593042090493, 94.31383514404297, 98.58039855957031, 58.83053221288515]],
      [p26, s26, [87.47408114935503, 95.0771255493164, 98.9540023803711, 58.66596638655462]],
    ] as const) {
      const stats = validateAggregationStats(raw, product)
      const cell = product.cells.features.find((f) => f.properties.id === 'AC-5KM-E105N1773')!.properties
      for (const [i, method] of (['mean', 'median', 'p75', 'concentration'] as const).entries())
        expect(summarize(cell, 'xgboost', method, stats).value).toBeCloseTo(expected[i], 7)
      const grid = displayGrid(product, 'xgboost', 'median', stats)
      expect(grid.features.find((f) => f.properties.id === cell.id)!.properties.display_value).toBe(expected[1])
      expect(cell.percentile_random_forest).not.toBe(cell.percentile_xgboost)
    }
  })
  it('rejects wrong year, provenance, missing model, invalid quantile, counts and CDF', () => {
    expect(() => validateAggregationStats(s25, p26)).toThrow()
    for (const mutate of [
      (s: typeof s26) => { s.source_identity = 'wrong' },
      (s: typeof s26) => { delete (s.groups as Record<string, unknown>)['AC-5KM-E105N1773'] },
      (s: typeof s26) => { s.groups['AC-5KM-E105N1773'].models.random_forest.median = -1 },
      (s: typeof s26) => { delete (s.groups['AC-5KM-E105N1773'].models as Record<string, unknown>).random_forest },
      (s: typeof s26) => { delete (s.groups['AC-5KM-E105N1773'].models as Record<string, unknown>).xgboost },
      (s: typeof s26) => { s.groups['AC-5KM-E105N1773'].models.random_forest.class_counts[0] = 1 },
      (s: typeof s26) => { s.groups['AC-5KM-E105N1773'].models.random_forest.state_cdf_count_le = 0 },
    ]) {
      const copy = structuredClone(s26); mutate(copy)
      expect(() => validateAggregationStats(copy, p26)).toThrow()
    }
  })
  it('reports missing file and invalid HTTP content, and forwards cancellation', async () => {
    const abort = new AbortController()
    const fetcher = vi.fn().mockResolvedValue(new Response('missing', { status: 404 }))
    vi.stubGlobal('fetch', fetcher)
    await expect(loadAggregationStats(p26, abort.signal)).rejects.toThrow('carregar')
    expect(fetcher).toHaveBeenCalledWith('/data/risk/v6/2026/aggregation-stats.json', { signal: abort.signal })
    fetcher.mockResolvedValue(new Response('<html/>', { headers: { 'content-type': 'text/html' } }))
    await expect(loadAggregationStats(p26)).rejects.toThrow('carregar')
    fetcher.mockRejectedValue(new TypeError('network'))
    await expect(loadAggregationStats(p26)).rejects.toThrow('network')
  })
})
