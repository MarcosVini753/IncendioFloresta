import { afterEach, describe, expect, it, vi } from 'vitest'
import manifestText from '../../../incendio/produtos/risco/v4/2026/manifest.json?raw'
import gridText from '../../../incendio/produtos/risco/v4/2026/grid.geojson?raw'
import boundaryText from '../../../incendio/produtos/risco/v4/2026/boundary.geojson?raw'
import indexText from '../../../incendio/produtos/risco/v4/2026/index.json?raw'
import { loadRiskV4, validateRiskV4Deployment } from './riskV4'

afterEach(() => vi.unstubAllGlobals())

const config = (mode: string, base: string | null) => ({
  schema_version: '1.0',
  year: 2026,
  raster_mode: mode,
  raster_base_url: base,
})

describe('publicação independente dos setores raster', () => {
  it('distingue agregado, local e externo sem trocar de ano', () => {
    expect(
      validateRiskV4Deployment(config('aggregated', null), 2026),
    ).toBeNull()
    expect(
      validateRiskV4Deployment(config('local', '/data/risk/v4/2026/'), 2026),
    ).toBe('/data/risk/v4/2026/')
    expect(
      validateRiskV4Deployment(
        config('remote', 'https://assets.example/risk/v4/2026/'),
        2026,
      ),
    ).toBe('https://assets.example/risk/v4/2026/')
    expect(() =>
      validateRiskV4Deployment(config('local', '/data/risk/v4/2025/'), 2026),
    ).toThrow()
    expect(() =>
      validateRiskV4Deployment(config('aggregated', null), 2025),
    ).toThrow()
  })

  it('rejeita configuração incompleta, credenciais e protocolos não HTTP', () => {
    for (const value of [
      null,
      {},
      config('local', null),
      config('aggregated', '/data/'),
      config('remote', 'file:///2026/'),
      config('remote', 'https://user:secret@assets.example/2026/'),
    ])
      expect(() => validateRiskV4Deployment(value, 2026)).toThrow()
  })

  it('carrega valores científicos reais em modo agregado sem solicitar TIFF', async () => {
    const files: Record<string, string> = {
      'manifest.json': manifestText,
      'grid.geojson': gridText,
      'boundary.geojson': boundaryText,
      'index.json': indexText,
      'deployment.json': JSON.stringify(config('aggregated', null)),
    }
    const fetcher = vi.fn((url: string) =>
      Promise.resolve(
        new Response(files[url.split('/').at(-1)!], {
          headers: { 'content-type': 'application/json' },
        }),
      ),
    )
    vi.stubGlobal('fetch', fetcher)
    const product = await loadRiskV4(2026)
    expect(product.rasterBase).toBeNull()
    expect(product.cells.features).toHaveLength(
      product.manifest.counts.features,
    )
    expect(fetcher).toHaveBeenCalledTimes(5)
    expect(fetcher.mock.calls.every(([url]) => !url.endsWith('.tif'))).toBe(
      true,
    )
  })
})
