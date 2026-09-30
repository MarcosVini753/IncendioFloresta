import { describe, expect, it } from 'vitest'
import manifestText from '../../../incendio/produtos/suscetibilidade/v1/aggregated/manifest.json?raw'
import { validateManifest } from './susceptibility'

const manifest = JSON.parse(manifestText) as Record<string, unknown>

describe('manifesto de suscetibilidade anual', () => {
  it('aceita o produto do ano mais recente como um único ano', () => {
    expect(validateManifest(manifest).source_period).toBe('2016')
  })

  it('rejeita o produto plurianual e divergência entre ano e alvo', () => {
    expect(() => validateManifest({ ...manifest, source_period: '2006-2016' })).toThrow(/único ano/)
    expect(() => validateManifest({
      ...manifest,
      training: { ...(manifest.training as object), target: 'burned_in_2015' },
    })).toThrow(/alvo não corresponde/)
  })
})
