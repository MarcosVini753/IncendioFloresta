import { afterEach, describe, expect, it, vi } from 'vitest'
import manifestText from '../../../incendio/produtos/risco/v6/2026/manifest.json?raw'
import gridText from '../../../incendio/produtos/risco/v6/2026/grid.geojson?raw'
import boundaryText from '../../../incendio/produtos/risco/v6/2026/boundary.geojson?raw'
import indexText from '../../../incendio/produtos/risco/v6/2026/index.json?raw'
import { loadRiskV6, validateRiskV6Deployment, validateRiskV6Manifest, validateRiskV6Product } from './riskV6'

afterEach(() => vi.unstubAllGlobals())

const config = (mode: string, base: string | null) => ({
  schema_version: '1.0',
  year: 2026,
  raster_mode: mode,
  raster_base_url: base,
})

describe('publicação independente dos setores raster', () => {
  it('rejeita contrato antigo, clima, cenário ou modelo não recebido', () => {
    for (const mutate of [
      (v: any) => { v.schema_version = '4.0' },
      (v: any) => { v.scenario = 'AB30C_suave' },
      (v: any) => { v.training.uses_climate = true },
      (v: any) => { v.training.climate_year = 2025 },
      (v: any) => { v.training.predictors.pop() },
      (v: any) => { v.models.push({ ...v.models[0], id: 'xgboost' }) },
      (v: any) => { v.models.pop() },
      (v: any) => { v.models[1].calibrated = true },
      (v: any) => { v.models[1].calibration = [0, 1] },
      (v: any) => { v.territory.year = 2007 },
    ]) {
      const value = JSON.parse(manifestText)
      mutate(value)
      expect(() => validateRiskV6Manifest(value)).toThrow()
    }
  })

  it('exige cobertura completa e quatro bandas RF/XGBoost, sem misturar setores v4', () => {
    const manifest = validateRiskV6Manifest(JSON.parse(manifestText))
    const grid = JSON.parse(gridText), boundary = JSON.parse(boundaryText)
    for (const mutate of [
      (v: any) => { v.bands.push('value_xgboost', 'percentile_xgboost') },
      (v: any) => { v.valid_pixels-- },
      (v: any) => { v.sectors[0].id = 'AC-V4-R000C000' },
      (v: any) => { v.sectors[0].window[0] = 1 },
    ]) {
      const index = JSON.parse(indexText)
      mutate(index)
      expect(() => validateRiskV6Product(manifest, grid, boundary, index)).toThrow()
    }
    const product = validateRiskV6Product(manifest, grid, boundary, JSON.parse(indexText))
    expect(product.manifest.counts.source_pixels).toBe(185661783)
    expect(product.index.bands).toEqual(['value_random_forest', 'percentile_random_forest', 'value_xgboost', 'percentile_xgboost'])
  })

  it('explica produto ausente e falha HTTP sem aceitar HTML do fallback SPA', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('missing', { status: 404 }))
    vi.stubGlobal('fetch', fetcher)
    await expect(loadRiskV6(2026)).rejects.toThrow('ausente')
    fetcher.mockResolvedValue(new Response('<html/>', { headers: { 'content-type': 'text/html' } }))
    await expect(loadRiskV6(2026)).rejects.toThrow('inválida')
    fetcher.mockRejectedValue(new TypeError('network unavailable'))
    await expect(loadRiskV6(2026)).rejects.toThrow('network unavailable')
  })

  it('distingue agregado, local e externo sem trocar de ano', () => {
    expect(
      validateRiskV6Deployment(config('aggregated', null), 2026),
    ).toBeNull()
    expect(
      validateRiskV6Deployment(config('local', '/data/risk/v6/2026/'), 2026),
    ).toBe('/data/risk/v6/2026/')
    expect(
      validateRiskV6Deployment(
        config('remote', 'https://assets.example/risk/v6/2026/'),
        2026,
      ),
    ).toBe('https://assets.example/risk/v6/2026/')
    expect(() =>
      validateRiskV6Deployment(config('local', '/data/risk/v6/2025/'), 2026),
    ).toThrow()
    expect(() =>
      validateRiskV6Deployment(config('aggregated', null), 2025),
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
      expect(() => validateRiskV6Deployment(value, 2026)).toThrow()
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
    const product = await loadRiskV6(2026)
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
