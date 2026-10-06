import {
  RISK_PRIORITY_CUTS,
  type RiskEvaluationMetrics,
} from '../types/susceptibility'

export function riskPriorityResults(metrics: RiskEvaluationMetrics, positiveCells: number) {
  return RISK_PRIORITY_CUTS.map((cut) => ({
    cut,
    fraction: metrics[`det@${cut}%`],
    found: Math.round(metrics[`det@${cut}%`] * positiveCells),
  }))
}
