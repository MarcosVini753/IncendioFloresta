import { afterEach, describe, expect, it, vi } from 'vitest'
import manifestText from '../../../incendio/produtos/risco/v2/2025/aggregated/manifest.json?raw'
import { loadSusceptibilityProduct, scoreForModel, validateManifest } from './susceptibility'
import { SCORE_PROPERTIES } from '../types/susceptibility'
import { riskPriorityResults } from './riskEvaluation'

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
    expect(() => validateManifest({ ...manifest, models: [] })).toThrow(/quatro/)
    expect(() => validateManifest({ ...manifest, scenarios: [{ id: 'todos' }, { id: 'todos' }] })).toThrow(/Cenários/)
    expect(() => validateManifest({ ...manifest, value: { semantics: 'relative_score', domain: [0, 100], calibrated_probability: false } })).toThrow(/semântica/)
    expect(() => validateManifest({ ...manifest, provenance: {} })).toThrow(/Proveniência/)
  })

  it('seleciona escores locais dos quatro modelos e quatro cenários', () => {
    const props = Object.fromEntries(SCORE_PROPERTIES.map((property, index) => [property, index / 16])) as Record<typeof SCORE_PROPERTIES[number], number>
    expect(scoreForModel(props, 'random_forest', 'todos')).toBe(1 / 16)
    expect(scoreForModel(props, 'random_forest', 'todos_regional')).toBe(5 / 16)
    expect(scoreForModel(props, 'xgboost', 'todos_regional')).toBe(7 / 16)
  })

  it('informa produto ausente e falha de rede', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 404 })))
    await expect(loadSusceptibilityProduct()).rejects.toThrow(/HTTP 404/)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await expect(loadSusceptibilityProduct()).rejects.toThrow(/offline/)
  })

  it('usa o teste territorial do modelo e cenário ativos, antes de agregar a grade', () => {
    const validated = validateManifest(manifest)
    const regional = riskPriorityResults(validated.evaluation.historical_test_2025.todos_regional.random_forest, validated.evaluation.test_positive_cells)
    const statewide = riskPriorityResults(validated.evaluation.historical_test_2025.todos.random_forest, validated.evaluation.test_positive_cells)
    expect(regional.find((row) => row.cut === 10)?.found).toBe(Math.round(validated.evaluation.historical_test_2025.todos_regional.random_forest['det@10%'] * validated.evaluation.test_positive_cells))
    expect(statewide.find((row) => row.cut === 10)?.found).toBe(Math.round(validated.evaluation.historical_test_2025.todos.random_forest['det@10%'] * validated.evaluation.test_positive_cells))
    expect(regional.map((row) => row.found)).toEqual([...regional.map((row) => row.found)].sort((a, b) => a - b))
    expect(validated.counts.source_cells).toBe(307410)
    expect(validated.evaluation.test_positive_cells).toBe(39)
  })

  it('rejeita avaliação ausente, modelo ausente e teste dentro do treino', () => {
    const missingModel = structuredClone(manifest) as typeof manifest & { evaluation: { historical_test_2025: { todos_regional: Record<string, unknown> } } }
    delete missingModel.evaluation.historical_test_2025.todos_regional.random_forest
    expect(() => validateManifest(missingModel)).toThrow(/Métricas inválidas/)
    expect(() => validateManifest({ ...manifest, evaluation: undefined })).toThrow(/Avaliação histórica/)
    expect(() => validateManifest({ ...manifest, training: { ...(manifest.training as object), evaluation: 'in_sample' } })).toThrow(/fora do treino/)
  })

  it('rejeita valores não finitos, prevalência divergente e detecções inconsistentes', () => {
    for (const change of [{ roc_auc: NaN }, { pr_auc: 1.1 }, { prevalencia: 0.5 }, { 'det@10%': 0.123 }, { 'det@5%': 20 / 39 }]) {
      const invalid = structuredClone(manifest) as typeof manifest & { evaluation: { historical_test_2025: { todos_regional: Record<string, object> } } }
      Object.assign(invalid.evaluation.historical_test_2025.todos_regional.random_forest, change)
      expect(() => validateManifest(invalid)).toThrow(/Métricas inválidas|Prevalência|Contagens/)
    }
  })
})
