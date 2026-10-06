import { riskPriorityResults } from '../../data/riskEvaluation'
import type { RiskScenario, SusceptibilityManifest, SusceptibilityModelId } from '../../types/susceptibility'
import { formatRelativeScorePercent } from '../../utils/formatRelativeScore'

interface RiskEvaluationProps {
  manifest: SusceptibilityManifest
  model: SusceptibilityModelId
  scenario: RiskScenario
}

function decimal(value: number, digits: number) {
  return new Intl.NumberFormat('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)
}

export function RiskEvaluation({ manifest, model, scenario }: RiskEvaluationProps) {
  const metrics = manifest.evaluation.historical_test_2025[scenario][model]
  const positiveCells = manifest.evaluation.test_positive_cells
  const priorities = riskPriorityResults(metrics, positiveCells)
  const topTen = priorities.find((item) => item.cut === 10)!
  const modelLabel = manifest.models.find((item) => item.id === model)?.label ?? model
  const scenarioLabel = manifest.scenarios.find((item) => item.id === scenario)?.label ?? scenario

  return (
    <section className="risk-evaluation" aria-labelledby="risk-evaluation-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Avaliação histórica · {manifest.source_period}</span>
          <h2 id="risk-evaluation-title">Como o modelo se saiu em 2025</h2>
        </div>
      </div>
      <p className="risk-evaluation-model"><strong>{modelLabel}</strong> · {scenarioLabel} · ano de teste fora do treino de {manifest.training.train_years.join('–')}</p>

      <dl className="risk-evaluation-stats">
        <div className="risk-evaluation-highlight">
          <dt>Positivas encontradas nos 10% de células com maiores escores</dt>
          <dd data-metric="top10" aria-live="polite">{topTen.found} de {positiveCells}</dd>
          <small>{formatRelativeScorePercent(topTen.fraction)} das células positivas registradas</small>
        </div>
        <div>
          <dt>AUC-ROC</dt>
          <dd data-metric="roc-auc">{decimal(metrics.roc_auc, 3)}</dd>
          <small>Ordenação dos escores entre células positivas e negativas no conjunto</small>
        </div>
        <div>
          <dt>Precisão média (AP)</dt>
          <dd data-metric="average-precision">{decimal(metrics.pr_auc, 6)}</dd>
          <small>Resumo de precisão e recuperação das células positivas registradas</small>
        </div>
      </dl>

      <p className="risk-evaluation-coverage">Teste na grade original de {manifest.counts.source_cells.toLocaleString('pt-BR')} células, com {positiveCells} positivas no inventário. Estas métricas permanecem iguais ao mudar o zoom ou selecionar uma célula.</p>
      <p className="risk-evaluation-limit">O inventário é limitado. Células positivas e pixels de cicatriz são unidades diferentes; nenhuma dessas contagens representa incêndios confirmados. A ausência de registro não comprova ausência de fogo.</p>

      <details className="scientific-note-details">
        <summary>Outros cortes e leitura das métricas</summary>
        <div className="evaluation-table-wrapper">
          <table className="evaluation-priority-table">
            <caption>Cobertura das células positivas ao priorizar os maiores escores</caption>
            <thead><tr><th scope="col">Células priorizadas</th><th scope="col">Positivas encontradas</th><th scope="col">Fração das positivas</th></tr></thead>
            <tbody>{priorities.map((item) => (
              <tr key={item.cut}><th scope="row">{item.cut}% com maiores escores</th><td>{item.found} de {positiveCells}</td><td>{formatRelativeScorePercent(item.fraction)}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <p>AUC-ROC e precisão média (AP) são métricas de desempenho, não probabilidades de incêndio. O campo PR-AUC do produto foi calculado como precisão média (AP). A proporção de positivas no conjunto é {decimal(metrics.prevalencia * 100, 4)}%. As métricas de validação com amostra balanceada e os relatórios de outros anos usam protocolos diferentes e não são comparados diretamente a este teste.</p>
      </details>
    </section>
  )
}
