import { afterEach, describe, expect, it, vi } from 'vitest'
import manifestText from '../../../incendio/produtos/clima/v1/2015/manifest.json?raw'
import gridText from '../../../incendio/produtos/clima/v1/2015/grid.geojson?raw'
import boundaryText from '../../../incendio/produtos/clima/v1/2015/boundary.geojson?raw'
import humidityText from '../../../incendio/produtos/clima/v1/2015/humidity.json?raw'
import precipitationText from '../../../incendio/produtos/clima/v1/2015/precipitation.json?raw'
import scarsText from '../../../incendio/produtos/clima/v1/2015/scars.geojson?raw'
import { loadClimateProduct, validateClimateManifest, validateClimateMatrix, validateScarCollection } from './climate'
import type { ClimateManifest } from '../types/climate'

const dates = Array.from({ length: 365 }, (_, index) => new Date(Date.UTC(2015, 0, index + 1)).toISOString().slice(0, 10))
const cellOrder = Array.from({ length: 212 }, (_, index) => `AC-R${index + 1}`)
const manifest: ClimateManifest = {
  schema_version: '1.0', product: 'historical_climate_and_scars', year: 2015,
  generated_at: '2026-09-28T00:00:00Z', crs: 'EPSG:4326', dates,
  cell_order: cellOrder, n_valid_pixels: Array(212).fill(3),
  bounds: [-74, -11.2, -66.6, -7.1], grid: { step_degrees: 0.28, source_step_degrees: 0.1 },
  statistics: { scope: 'spatial_per_day', mean: 'pixel_overlap_area_weighted', extrema: 'intersecting_valid_pixels' },
  variables: { humidity: { unit: '%', source: 'humidity.tif' }, precipitation: { unit: 'mm', source: 'precipitation.tif' } },
  scars: { source: 'scars.tif', meaning: 'day_of_year_of_detection', feature_count: 0 },
  files: { grid: 'grid.geojson', boundary: 'boundary.geojson', humidity: 'humidity.json', precipitation: 'precipitation.json', scars: 'scars.geojson' },
}

afterEach(() => vi.unstubAllGlobals())

describe('clima diário de 2015', () => {
  it('rejeita uma data ausente e um arquivo externo no manifesto', () => {
    expect(() => validateClimateManifest({ ...manifest, dates: dates.slice(1) })).toThrow(/Calendário/)
    expect(() => validateClimateManifest({ ...manifest, files: { ...manifest.files, grid: '../outro.geojson' } })).toThrow(/Arquivos/)
  })

  it('rejeita matriz truncada e extremos invertidos', () => {
    const values = Array.from({ length: 365 }, () => Array.from({ length: 212 }, () => [50, 60, 70]))
    expect(() => validateClimateMatrix({ variable: 'humidity', values: values.slice(0, -1) }, 'humidity', manifest)).toThrow(/incompleta/)
    values[0][0] = [70, 60, 50]
    expect(() => validateClimateMatrix({ variable: 'humidity', values }, 'humidity', manifest)).toThrow(/inválido/)
  })

  it('aceita dia sem cicatriz, mas rejeita contagem divergente', () => {
    expect(validateScarCollection({ type: 'FeatureCollection', features: [] }, manifest).features).toHaveLength(0)
    expect(() => validateScarCollection({ type: 'FeatureCollection', features: [] }, { ...manifest, scars: { ...manifest.scars, feature_count: 1 } })).toThrow(/incompletas/)
  })

  it('informa HTTP ausente e falha de rede', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404 })))
    await expect(loadClimateProduct()).rejects.toThrow(/HTTP 404/)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await expect(loadClimateProduct()).rejects.toThrow(/offline/)
  })

  it('carrega o produto canônico completo e uma célula sem dado', async () => {
    const files: Record<string, string> = {
      'manifest.json': manifestText, 'grid.geojson': gridText, 'boundary.geojson': boundaryText,
      'humidity.json': humidityText, 'precipitation.json': precipitationText, 'scars.geojson': scarsText,
    }
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const filename = url.split('/').at(-1)
      return Promise.resolve(new Response(files[String(filename)], { status: 200 }))
    }))
    const product = await loadClimateProduct()
    expect(product.manifest.dates).toHaveLength(365)
    expect(product.grid.features).toHaveLength(212)
    expect(product.scars.features).toHaveLength(425)
    const emptyIndex = product.manifest.n_valid_pixels.findIndex((count) => count === 0)
    expect(emptyIndex).toBeGreaterThanOrEqual(0)
    expect(product.humidity.values[0][emptyIndex]).toEqual([null, null, null])
  })
})
