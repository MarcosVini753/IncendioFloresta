import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  loadNativeSector,
  NativeSectorCache,
  validateNativeIndex,
  validateNativeManifest,
  validateNativeSector,
} from './nativeSusceptibility'
import { validateManifest } from './susceptibility'
import type {
  NativeCellCollection,
  NativeSectorIndexEntry,
  NativeSusceptibilityManifest,
} from '../types/susceptibility'

const entry: NativeSectorIndexEntry = {
  id: 'AC-R01C01',
  url: 'sectors/AC-R01C01.geojson',
  bbox: [-74, -11, -73.72, -10.72],
  feature_count: 1,
}

const manifest: NativeSusceptibilityManifest = {
  schema_version: '1.0',
  product: 'wildfire_susceptibility',
  label: 'Suscetibilidade',
  generated_at: '2026-09-22T00:00:00Z',
  source_period: '2006-2016',
  crs: 'EPSG:4326',
  default_model: 'gradboost',
  models: [
    ['gradboost', 'score_gradboost'],
    ['random_forest', 'score_random_forest'],
    ['logistic_regression', 'score_logistic_regression'],
    ['fuzzy_knn_k29', 'score_fuzzy_knn_k29'],
  ].map(([id, property]) => ({
    id: id as NativeSusceptibilityManifest['models'][number]['id'],
    label: id,
    property: property as NativeSusceptibilityManifest['models'][number]['property'],
    validation: { protocol: 'spatial_group_kfold_25km', folds: 5, roc_auc: 0.8, pr_auc: 0.7 },
  })),
  value: { semantics: 'relative_score', domain: [0, 1], calibrated_probability: false },
  original_grid: { crs: 'EPSG:31979', cell_width_m: 892.98, cell_height_m: 598.16, cell_count: 307410 },
  representation: { type: 'native_sharded_grid', aggregation: 'none', sector_step_degrees: 0.28 },
  counts: { source_cells: 307410, features: 307410, sectors: 212 },
  bounds: [-74, -11.2, -66.6, -7.1],
  files: { index: 'index.json' },
}

const collection: NativeCellCollection = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [[[-74, -11], [-73.99, -11], [-73.99, -10.99], [-74, -10.99], [-74, -11]]] },
    properties: {
      id: 'AC-Y1-X2', grid_x: 2, grid_y: 1, centroid: [-73.995, -10.995], aggregation: 'none',
      score_gradboost: 0.4,
      score_random_forest: 0.5,
      score_logistic_regression: 0.6,
      score_fuzzy_knn_k29: 0.7,
    },
  }],
}

afterEach(() => vi.restoreAllMocks())

describe('contratos públicos', () => {
  it('rejeita manifesto agregado incompatível', () => {
    expect(() => validateManifest({ schema_version: '2.0' })).toThrow(/compatível|inválido/)
  })

  it('rejeita manifesto nativo incompatível', () => {
    expect(() => validateNativeManifest({ ...manifest, crs: 'EPSG:31979' })).toThrow(/CRS/)
  })

  it('rejeita setor vazio no índice e no arquivo', () => {
    const emptyEntry = { ...entry, feature_count: 0 }
    expect(() => validateNativeIndex({
      schema_version: '1.0',
      product: 'wildfire_susceptibility_native_index',
      feature_count: 307410,
      sectors: [emptyEntry],
    }, { ...manifest, counts: { ...manifest.counts, sectors: 1 } })).toThrow(/vazio/)
    expect(() => validateNativeSector({ type: 'FeatureCollection', features: [] }, entry)).toThrow(/vazio/)
  })

  it('aceita uma feature nativa válida', () => {
    expect(validateNativeSector(collection, entry).features).toHaveLength(1)
  })
})

describe('falhas de aquisição', () => {
  it('expõe HTTP 404 como arquivo ausente', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404 })))
    await expect(loadNativeSector(entry)).rejects.toThrow(/HTTP 404/)
  })

  it('propaga falha de rede', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))
    await expect(loadNativeSector(entry)).rejects.toThrow(/network down/)
  })
})

describe('cache LRU', () => {
  it('mantém no máximo 32 setores e promove acessos recentes', () => {
    const cache = new NativeSectorCache(32)
    for (let index = 0; index < 32; index += 1) cache.set(String(index), collection)
    expect(cache.get('0')).toBe(collection)
    cache.set('32', collection)
    expect(cache.size).toBe(32)
    expect(cache.get('1')).toBeUndefined()
    expect(cache.get('0')).toBe(collection)
  })
})
