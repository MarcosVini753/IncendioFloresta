import { afterEach, describe, expect, it, vi } from 'vitest'
import { dangerCellsForDate, dangerSeries, loadDangerProduct, validateDangerManifest, validateDangerScores } from './danger'
import type { DangerManifest, DangerProduct } from '../types/danger'
import type { SusceptibilityModelId } from '../types/susceptibility'

const models: SusceptibilityModelId[] = ['gradboost', 'random_forest', 'logistic_regression', 'fuzzy_knn_k29']
const dates = Array.from({ length: 365 }, (_, offset) => new Date(Date.UTC(2015, 0, offset + 1)).toISOString().slice(0, 10))
const cellOrder = Array.from({ length: 212 }, (_, index) => `AC-R${String(index + 1).padStart(3, '0')}`)

const manifest: DangerManifest = {
  schema_version: '1.0', product: 'wildfire_historical_daily_danger', label: 'Perigo histórico diário — 2015',
  generated_at: '2026-09-22T00:00:00Z', source_period: '2015-01-01/2015-12-31', crs: 'EPSG:4326',
  default_model: 'gradboost', default_date: '2015-08-25', dates, cell_order: cellOrder,
  models: models.map((id) => ({ id, label: id, file: `scores/${id}.json`,
    implementation: id === 'fuzzy_knn_k29'
      ? { backend: 'sklearn.neighbors.NearestNeighbors', search: 'exact', k: 29, m: 2 }
      : { backend: `sklearn.${id}`, random_state: 42 },
    validation_2013: { roc_auc: 0.9, pr_auc: 0.8 }, test_2014_2015: { roc_auc: 0.8, pr_auc: 0.7 } })),
  value: { semantics: 'relative_score', domain: [0, 1], calibrated_probability: false },
  protocol: { training: '2006-2012', validation: '2013', historical_test: '2014-2015', predictor_count: 44, seed: 42, fire_context: 'previous_days_only' },
  original_grid: { crs: 'EPSG:31979', cell_width_m: 893, cell_height_m: 598, cell_count: 307410 },
  representation: { type: 'aggregated_grid', step_degrees: 0.28, aggregation: 'mean' },
  counts: { dates: 365, features: 212, source_cells_per_date: 307410 }, bounds: [-74, -11, -66, -7],
  files: { grid: 'grid.geojson' },
  provenance: { checkpoint_schema_version: '1.0', checkpoint_contract_sha256: 'a'.repeat(64),
    training_rows: 196455, predictors: Array.from({ length: 44 }, (_, index) => `predictor_${index}`) },
}

const values = Array.from({ length: 365 }, () => Array.from({ length: 212 }, (_, index) => index / 212))
const grid = { type: 'FeatureCollection' as const, features: cellOrder.map((id, index) => ({
  type: 'Feature' as const,
  geometry: { type: 'Polygon' as const, coordinates: [[[-74, -11], [-73, -11], [-73, -10], [-74, -10], [-74, -11]]] },
  properties: { id, centroid: [-70, -9] as [number, number], n_source_cells: index === 0 ? 307199 : 1, aggregation: 'mean' as const },
})) }
const product: DangerProduct = {
  manifest, grid, bounds: [[-74, -11], [-66, -7]],
  scores: Object.fromEntries(models.map((model) => [model, values])) as DangerProduct['scores'],
}

afterEach(() => vi.restoreAllMocks())

describe('contrato anual de perigo', () => {
  it('aceita 365 datas contínuas e rejeita data ausente', () => {
    expect(validateDangerManifest(manifest).dates).toHaveLength(365)
    expect(() => validateDangerManifest({ ...manifest, dates: dates.slice(1) })).toThrow(/365 dias/)
  })

  it('rejeita modelo ausente e matriz incompleta', () => {
    expect(() => validateDangerManifest({ ...manifest, models: manifest.models.slice(1) })).toThrow(/quatro modelos/)
    expect(() => validateDangerManifest({ ...manifest, models: manifest.models.map((model, index) => index === 0 ? { ...model, id: 'fuzzy_knn_k29' } : model) })).toThrow(/duplicado|quatro modelos/)
    expect(() => validateDangerScores({ schema_version: '1.0', model: 'gradboost', values: values.slice(1) }, 'gradboost')).toThrow(/incompleta/)
  })

  it('rejeita proveniência ausente e busca Fuzzy aproximada', () => {
    expect(() => validateDangerManifest({ ...manifest, provenance: undefined })).toThrow(/proveniência/)
    const approximate = manifest.models.map((model) => model.id === 'fuzzy_knn_k29'
      ? { ...model, implementation: { ...model.implementation, search: 'approximate' } }
      : model)
    expect(() => validateDangerManifest({ ...manifest, models: approximate })).toThrow(/busca exata/)
  })

  it('monta a célula diária e séries estadual e local sem novas requisições', () => {
    const cells = dangerCellsForDate(product, '2015-08-25')
    expect(cells.features).toHaveLength(212)
    expect(cells.features[10].properties.score_gradboost).toBe(values[0][10])
    expect(dangerSeries(product, 'gradboost')).toHaveLength(365)
    expect(dangerSeries(product, 'gradboost')[0].value).toBeCloseTo(
      values[0].reduce((sum, score, index) => sum + score * grid.features[index].properties.n_source_cells, 0) / 307410,
    )
    expect(dangerSeries(product, 'gradboost', cellOrder[10])[0].value).toBe(values[0][10])
    expect(() => dangerCellsForDate(product, '2016-01-01')).toThrow(/Data ausente/)
  })
})

describe('falhas HTTP', () => {
  it('informa arquivo público ausente', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404 })))
    await expect(loadDangerProduct()).rejects.toThrow(/HTTP 404/)
  })

  it('propaga falha de rede', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))
    await expect(loadDangerProduct()).rejects.toThrow(/network down/)
  })

  it('explica quando o fallback da aplicação substitui um JSON ainda ausente', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<!doctype html>', {
      status: 200, headers: { 'content-type': 'text/html' },
    })))
    await expect(loadDangerProduct()).rejects.toThrow(/produto histórico ainda não está disponível/)
  })
})
