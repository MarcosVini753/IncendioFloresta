import { describe, it, expect } from 'vitest'
import { COMPARISON_STOPS, rankingDifference, formatRankingDifference } from './riskComparison'
import type { RiskV4Values } from '../types/riskV4'

const values = (rf: number, xgb: number): RiskV4Values => ({
  percentile_random_forest: rf,
  percentile_xgboost: xgb,
  value_random_forest: 0.4,
  value_xgboost: 20,
})

describe('comparação de rankings científicos', () => {
  it('compara percentis e nunca valores brutos diferentes', () => {
    expect(rankingDifference(values(75, 60))).toBe(15)
    expect(rankingDifference(values(40, 70))).toBe(-30)
  })
  it('explica o sentido da diferença e lida com empate', () => {
    expect(formatRankingDifference(0)).toBe('Praticamente iguais')
    expect(formatRankingDifference(12)).toContain('Random Forest')
    expect(formatRankingDifference(-12)).toContain('XGBoost')
  })
  it('tem centro neutro e ordem crescente de intensidades', () => {
    expect(COMPARISON_STOPS.find((stop) => stop.value === 0)?.color).toBe('#f0f1eb')
    expect(COMPARISON_STOPS.map((stop) => stop.value)).toEqual(
      [...COMPARISON_STOPS.map((stop) => stop.value)].sort((a, b) => a - b),
    )
  })
})
