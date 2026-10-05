import { afterEach, describe, expect, it, vi } from 'vitest'
import manifestText from '../../../incendio/produtos/risco/v1/2025/aggregated/manifest.json?raw'
import { loadSusceptibilityProduct, scoreForModel, validateManifest } from './susceptibility'
import { SCORE_PROPERTIES } from '../types/susceptibility'

const manifest = JSON.parse(manifestText) as Record<string, unknown>
afterEach(() => vi.unstubAllGlobals())

describe('manifesto de suscetibilidade anual', () => {
  it('aceita o produto do ano mais recente como um único ano', () => {
    expect(validateManifest(manifest).source_period).toBe('2025')
  })

  it('rejeita o produto plurianual e divergência entre ano e alvo', () => {
    expect(() => validateManifest({ ...manifest, source_period: '2006-2016' })).toThrow(/único ano/)
    expect(() => validateManifest({
      ...manifest,
      training: { ...(manifest.training as object), target: 'burned_in_2015' },
    })).toThrow(/alvo não corresponde/)
  })

  it('rejeita modelo ausente, cenários inválidos e domínio incorreto', () => {
    expect(() => validateManifest({ ...manifest, models: [] })).toThrow(/cinco/)
    expect(() => validateManifest({ ...manifest, scenarios: [{ id: 'unico' }, { id: 'unico' }] })).toThrow(/Cenários/)
    expect(() => validateManifest({ ...manifest, value: { semantics: 'relative_score', domain: [0, 100], calibrated_probability: false } })).toThrow(/semântica/)
    expect(() => validateManifest({ ...manifest, provenance: {} })).toThrow(/Proveniência/)
  })

  it('seleciona escores locais dos cinco modelos e dois cenários', () => {
    const props = Object.fromEntries(SCORE_PROPERTIES.map((property, index) => [property, index / 10])) as Record<typeof SCORE_PROPERTIES[number], number>
    expect(scoreForModel(props, 'random_forest', 'unico')).toBe(0.1)
    expect(scoreForModel(props, 'random_forest', 'regional')).toBe(0.6)
    expect(scoreForModel(props, 'xgboost', 'regional')).toBe(0.9)
  })

  it('informa produto ausente e falha de rede', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404 })))
    await expect(loadSusceptibilityProduct()).rejects.toThrow(/HTTP 404/)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await expect(loadSusceptibilityProduct()).rejects.toThrow(/offline/)
  })
})
