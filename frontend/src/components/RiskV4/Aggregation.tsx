import { SUMMARY_METHODS, needsStats, summaryDefinition, summarize, type AggregationStats, type SummaryMethod } from '../../data/riskAggregation'
import { RISK_DISPLAY_CLASSES } from '../../data/riskDisplayPalette'
import type { RiskV4Cell, RiskV4Model } from '../../types/riskV4'

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

export function Calculation({ cell, model, method, stats }: { cell: RiskV4Cell; model: RiskV4Model; method: SummaryMethod; stats: AggregationStats | null }) {
  const definition = summaryDefinition(method), result = summarize(cell, model, method, stats)
  const group = stats?.groups[cell.id], extra = group?.models[model]
  const n = cell.n_source_pixels
  return <details className="aggregation-calculation">
    <summary>Como este resultado foi calculado?</summary>
    <p>{definition.description}</p>
    <p>Grupo {cell.id} · {n.toLocaleString('pt-BR')} pixels válidos · {model === 'random_forest' ? 'Random Forest' : 'XGBoost'}.</p>
    <details><summary>Fórmula, variáveis e exemplo desta área</summary>
      <code>{definition.formula}</code>
      <p>n = {n.toLocaleString('pt-BR')}{stats ? `; N estadual = ${stats.counts.source_pixels.toLocaleString('pt-BR')}` : ''}.</p>
      {method === 'mean' && <p>Soma dos percentis = {(cell[`percentile_${model}`] * n).toLocaleString('pt-BR', { maximumFractionDigits: 6 })}; dividida por n = {summaryNumber(cell[`percentile_${model}`])}. Este é o percentil médio dos pixels; o grupo não foi ranqueado novamente.</p>}
      {method === 'mode' && <p>A maior contagem é {Math.max(...result.counts).toLocaleString('pt-BR')} pixels: {RISK_DISPLAY_CLASSES[result.classIndex!].label}, com {summaryNumber(result.dominantShare * 100)}% do grupo.</p>}
      {method === 'concentration' && <p>100 × ({result.counts[3].toLocaleString('pt-BR')} + {result.counts[4].toLocaleString('pt-BR')}) / {n.toLocaleString('pt-BR')} = {summaryNumber(result.concentration)}% dos pixels.</p>}
      {(method === 'median' || method === 'p75') && <p>q = {method === 'median' ? '0,5' : '0,75'}; posição = {Math.ceil(n * (method === 'median' ? .5 : .75)).toLocaleString('pt-BR')}. O pixel nessa posição tem índice {result.value?.toLocaleString('pt-BR', { maximumFractionDigits: 8 })}. Calculado dos pixels originais, sem interpolação.</p>}
      {method === 'area_mean' && group && result.value !== null && <p>Área válida = {summaryNumber(group.valid_area_m2)} m²; soma ponderada = {(result.value * group.valid_area_m2).toLocaleString('pt-BR', { maximumFractionDigits: 3 })} índice·m². Divisão pela área válida = {result.value.toLocaleString('pt-BR', { maximumFractionDigits: 8 })}.</p>}
      {(method === 'local_rarity' || method === 'state_rarity') && extra && <>
        <table className="aggregation-formula-table"><thead><tr><th>Classe</th><th>Pixels</th><th>Média do índice</th>{method === 'state_rarity' && <th>Frequência estadual</th>}</tr></thead><tbody>
          {RISK_DISPLAY_CLASSES.map((c, i) => <tr key={c.id}><td>{c.label}</td><td>{extra.class_counts[i].toLocaleString('pt-BR')}</td><td>{extra.class_means[i]?.toLocaleString('pt-BR', { maximumFractionDigits: 6 }) ?? 'Sem pixels'}</td>{method === 'state_rarity' && <td>{summaryNumber(stats!.state_frequencies[model][i] * 100)}%</td>}</tr>)}
        </tbody></table>
        <p>{method === 'local_rarity' ? `${extra.class_counts.filter((v) => v > 0).length} classes ocupadas recebem o mesmo peso total.` : 'Pesos por pixel: inverso das frequências estaduais da tabela, específicas deste ano/modelo.'} Classes vazias não participam. Resultado: {summaryNumber(result.value!)}. Esta ponderação não é uma calibração de probabilidade.</p>
      </>}
      {method === 'state_cdf' && extra && stats && <p>Valor médio da banda 1: {cell[`value_${model}`].toLocaleString('pt-BR', { maximumFractionDigits: 8 })}%. Há {extra.state_cdf_count_le.toLocaleString('pt-BR')} pixels estaduais com valor menor ou igual a essa média. 100 × contagem / {stats.counts.source_pixels.toLocaleString('pt-BR')} = {summaryNumber(extra.state_cdf)}. A CDF exata ≤ trata empates de forma diferente do histograma recebido. A referência são pixels, não grupos de 5 km.</p>}
    </details>
  </details>
}
