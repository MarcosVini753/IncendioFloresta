import { SUMMARY_METHODS, needsStats, summaryDefinition, summarize, type AggregationStats, type SummaryMethod } from '../../data/riskAggregation'
import { RISK_DISPLAY_CLASSES } from '../../data/riskDisplayPalette'
import type { RiskV4Cell, RiskV4Model } from '../../types/riskV4'
import { MethodExplanation } from './CalculationDetails'
export { Calculation } from './CalculationDetails'

export const summaryNumber = (n: number) => n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export function AggregationControl({ method, onChange, native, comparison, available, loading, error, retry, notice }: {
  method: SummaryMethod; onChange: (m: SummaryMethod) => void; native: boolean; comparison: boolean
  available: boolean; loading: boolean; error: string; retry: () => void; notice: string
}) {
  return <section className="control-group aggregation-control">
    <label className="control-label" htmlFor="risk-summary">Como resumir os grupos de 5 km?</label>
    <select id="risk-summary" value={method} disabled={native || comparison} onChange={(e) => onChange(e.target.value as SummaryMethod)}>
      {[false, true].map((advanced) => <optgroup key={String(advanced)} label={advanced ? 'Análise avançada — experimental' : 'Uso principal'}>
        {SUMMARY_METHODS.filter((m) => m.advanced === advanced).map((m) => <option key={m.id} value={m.id} disabled={needsStats(m.id) && !available}>{m.label}</option>)}
      </optgroup>)}
    </select>
    <small>{comparison ? 'A comparação usa exclusivamente médias dos percentis.' : native ? 'Os resumos se aplicam aos grupos de 5 km. Aqui são exibidos os pixels originais; sua escolha será mantida ao afastar.' : summaryDefinition(method).description}</small>
    {!native && !comparison && <details className="aggregation-method-overview">
      <summary>Entenda tecnicamente este resumo</summary>
      <MethodExplanation method={method} />
      <p>Selecione um grupo no mapa para consultar a memória de cálculo com suas contagens, pesos e valores reais.</p>
    </details>}
    {loading && <small role="status">Carregando estatísticas adicionais…</small>}
    {notice && <p role="status" className="aggregation-notice">{notice}</p>}
    {error && <div className="overlay-error" role="alert">{error} Média, moda e concentração continuam disponíveis. <button type="button" onClick={retry}>Tentar novamente</button></div>}
  </section>
}

export function Composition({ cell, model }: { cell: RiskV4Cell; model: RiskV4Model }) {
  const result = summarize(cell, model, 'mode', null)
  return <section className="risk-class-shares aggregation-composition">
    <h3>Composição dos pixels do grupo</h3>
    <small>{model === 'random_forest' ? 'Random Forest' : 'XGBoost'} · classes originais dos pixels</small>
    <p><strong>{summaryNumber(result.concentration)}%</strong> em Alto ou Muito alto · cobertura aproximada da área válida.</p>
    <div className="aggregation-composition-bar" role="img" aria-label="Distribuição dos pixels nas cinco classes">
      {RISK_DISPLAY_CLASSES.map((c, i) => <span key={c.id} style={{ width: `${100 * result.counts[i] / cell.n_source_pixels}%`, backgroundColor: c.color }} title={`${c.label}: ${summaryNumber(100 * result.counts[i] / cell.n_source_pixels)}%`} />)}
    </div>
    {RISK_DISPLAY_CLASSES.map((c, i) => <div className="risk-class-share" key={c.id}>
      <i className="risk-class-swatch" style={{ backgroundColor: c.color }} aria-hidden="true" />
      <span className="risk-class-name">{c.label}</span>
      <strong>{summaryNumber(100 * result.counts[i] / cell.n_source_pixels)}%</strong>
      <small>{result.counts[i].toLocaleString('pt-BR')} pixels</small>
    </div>)}
  </section>
}

export function SummaryValue({ cell, model, method, stats }: { cell: RiskV4Cell; model: RiskV4Model; method: SummaryMethod; stats: AggregationStats | null }) {
  const r = summarize(cell, model, method, stats)
  return <>
    <span className="risk-score-topline"><strong>{method === 'mode' ? RISK_DISPLAY_CLASSES[r.classIndex!].label : r.value === null ? 'Indisponível' : `${summaryNumber(r.value)}${method === 'concentration' ? '%' : ''}`}</strong></span>
    <span className="risk-score-class">{method === 'mode' ? `Classe mais frequente: ${summaryNumber(r.dominantShare * 100)}% dos pixels.`
      : method === 'concentration' ? 'Pixels Alto + Muito alto; não é chance de incêndio.'
        : r.classIndex !== null ? `Classe deste resumo: ${RISK_DISPLAY_CLASSES[r.classIndex].label}` : ''}</span>
    {method === 'mode' && r.mixed && <p className="aggregation-notice" style={{ color: '#573d13' }}>Grupo misto: nenhuma classe ultrapassa 50%.</p>}
    {method === 'mode' && r.tied && <p>Há empate entre classes mais frequentes; é exibida a menor classe.</p>}
  </>
}
