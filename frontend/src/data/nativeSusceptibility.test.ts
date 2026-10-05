import { afterEach, describe, expect, it, vi } from 'vitest'
import manifestText from '../../../incendio/produtos/risco/v1/2025/native_sharded_grid/manifest.json?raw'
import { SCORE_PROPERTIES } from '../types/susceptibility'
import {
  loadNativeSector,
  nativeFeatureIntersectsViewport,
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

const manifest = JSON.parse(manifestText) as NativeSusceptibilityManifest

const collection: NativeCellCollection = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [[[-74, -11], [-73.99, -11], [-73.99, -10.99], [-74, -10.99], [-74, -11]]] },
    properties: {
      id: 'AC-Y1-X2', grid_x: 2, grid_y: 1, centroid: [-73.995, -10.995], aggregation: 'none',
      ...Object.fromEntries(SCORE_PROPERTIES.map((property) => [property, 0.5])) as Record<typeof SCORE_PROPERTIES[number], number>,
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
      product: 'wildfire_annual_risk_native_index',
      feature_count: 307410,
      sectors: [emptyEntry],
    }, { ...manifest, counts: { ...manifest.counts, sectors: 1 } })).toThrow(/vazio/)
    expect(() => validateNativeSector({ type: 'FeatureCollection', features: [] }, entry)).toThrow(/vazio/)
  })

  it('aceita uma feature nativa válida', () => {
    expect(validateNativeSector(collection, entry).features).toHaveLength(1)
  })

  it('limita as células à viewport, incluindo interseções na borda', () => {
    const feature = collection.features[0]
    expect(nativeFeatureIntersectsViewport(feature, [-74, -11, -73.99, -10.99])).toBe(true)
    expect(nativeFeatureIntersectsViewport(feature, [-74, -11, -73.999, -10.999])).toBe(true)
    expect(nativeFeatureIntersectsViewport(feature, [-70, -10, -69, -9])).toBe(false)
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
