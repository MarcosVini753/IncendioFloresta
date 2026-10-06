import { afterEach, describe, expect, it, vi } from 'vitest'
import manifestText from '../../../incendio/produtos/clima/v1/2025/manifest.json?raw'
import scarsText from '../../../incendio/produtos/clima/v1/2025/scars.geojson?raw'
import { loadScarProduct, validateClimateManifest, validateScarCollection } from './climate'

const manifest = JSON.parse(manifestText)
const scars = JSON.parse(scarsText)
afterEach(() => vi.unstubAllGlobals())

describe('cicatrizes anuais sobre o risco', () => {
  it('carrega apenas manifesto e cicatrizes, sem matrizes climáticas ou filtro diário', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(manifestText)).mockResolvedValueOnce(new Response(scarsText))
    vi.stubGlobal('fetch', fetchMock)
    const product = await loadScarProduct()
    expect(product.scars.features).toHaveLength(59)
    expect(new Set(product.scars.features.map((feature) => feature.properties.date)).size).toBeGreaterThan(1)
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(['/data/climate/v1/2025/manifest.json', '/data/climate/v1/2025/scars.geojson'])
  })

  it('aceita inventário vazio e rejeita contagem ou data inválida', () => {
    const emptyManifest = validateClimateManifest({ ...manifest, scars: { ...manifest.scars, feature_count: 0 } })
    expect(validateScarCollection({ type: 'FeatureCollection', features: [] }, emptyManifest).features).toHaveLength(0)
    expect(() => validateClimateManifest({ ...manifest, scars: { ...manifest.scars, feature_count: -1 } })).toThrow(/Metadados/)
    const invalid = structuredClone(scars)
    invalid.features[0].properties.date = '2024-01-22'
    expect(() => validateScarCollection(invalid, manifest)).toThrow(/data inválida/)
    for (const day of [0, -1, 366]) {
      const invalidDay = structuredClone(scars)
      invalidDay.features[0].properties.day_of_year = day
      delete invalidDay.features[0].properties.date
      expect(() => validateScarCollection(invalidDay, manifest)).toThrow(/data inválida/)
    }
  })

  it('informa HTTP ausente, falha de rede e GeoJSON inválido', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(manifestText)).mockResolvedValueOnce(new Response('', { status: 404 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(loadScarProduct()).rejects.toThrow(/HTTP 404/)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await expect(loadScarProduct()).rejects.toThrow(/offline/)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(manifestText)).mockResolvedValueOnce(new Response(JSON.stringify({ type: 'FeatureCollection', features: [] }))))
    await expect(loadScarProduct()).rejects.toThrow(/incompletas/)
  })
})
