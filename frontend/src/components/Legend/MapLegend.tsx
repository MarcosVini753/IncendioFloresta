import { RISK_DISPLAY_CLASSES } from '../../data/riskDisplayPalette'
import { COMPARISON_STOPS } from '../../data/riskComparison'

interface MapLegendProps {
  modelLabel: string
  aggregated?: boolean
  showScars?: boolean
  rasterReduced?: boolean
  highlightClass?: string | null
  onHighlightClassChange?: (id: string | null) => void
  comparisonMode?: boolean
}

export function MapLegend({
  modelLabel,
  aggregated = false,
  showScars = false,
  rasterReduced = false,
  highlightClass = null,
  onHighlightClassChange,
  comparisonMode = false,
}: MapLegendProps) {
  const description = aggregated
    ? 'A cor representa a classificação da média dos pixels de cada área de 5 km.'
    : rasterReduced
      ? 'Ao aproximar, as cores resumem pixels menores.'
      : 'As cores representam a classificação dos pixels individuais.'

  if (comparisonMode) {
    return (
      <div className="map-legend-stack">
        <section className="map-legend map-legend-comparison" aria-label="Legenda da diferença entre modelos">
          <div className="map-legend-heading">
            <strong>Onde os modelos discordam</strong>
            <span>Mesmo ano · áreas de 5 km</span>
          </div>
          <div className="risk-difference-scale" role="img" aria-label="Azul indica ranking mais alto no XGBoost; terracota indica ranking mais alto no Random Forest; centro claro indica valores próximos">
            {COMPARISON_STOPS.map((stop) => (
              <span key={stop.value} style={{ backgroundColor: stop.color }} />
            ))}
          </div>
          <div className="risk-difference-labels">
            <span>Mais alto no<br/>XGBoost</span>
            <span>Valores<br/>próximos</span>
            <span>Mais alto no<br/>Random Forest</span>
          </div>
          <details className="map-legend-help">
            <summary>O que significa?</summary>
            <p>Uma cor mais forte significa maior distância entre as posições no ranking dos modelos. Não indica o risco verdadeiro nem qual modelo é melhor.</p>
          </details>
        </section>
        {showScars && (
          <div className="scar-legend risk-scar-legend">
            <strong><i className="scar-swatch risk-scar-swatch" aria-hidden="true" /> Áreas queimadas · 2025</strong>
            <span>Registros históricos de áreas queimadas.</span>
          </div>
        )}
      </div>
    )
  }
  return (
    <div className="map-legend-stack">
      <section className="map-legend" aria-label={`Legenda do risco: ${modelLabel}`}>
        <div className="map-legend-heading">
          <strong>Risco relativo</strong>
          <span>{modelLabel}</span>
        </div>
        <div className="risk-legend-swatches" aria-hidden="true">
          {RISK_DISPLAY_CLASSES.map((riskClass) => (
            <span key={riskClass.id} style={{ backgroundColor: riskClass.color }} />
          ))}
        </div>
        <div className="risk-legend-extremes">
          <span>Menor posição</span>
          <span>Maior posição</span>
        </div>
        <details className="map-legend-help">
          <summary>Entenda as cores</summary>
          <p>{description} Os valores indicam posição no ranking, não a chance de um incêndio.</p>
          <div className="risk-legend-filter" role="group" aria-label="Destacar uma classe de risco">
            {RISK_DISPLAY_CLASSES.map((riskClass) => (
              <button
                type="button"
                key={riskClass.id}
                disabled={!aggregated || !onHighlightClassChange}
                aria-pressed={aggregated && highlightClass === riskClass.id}
                onClick={() => onHighlightClassChange?.(
                  highlightClass === riskClass.id ? null : riskClass.id,
                )}
                title={aggregated && onHighlightClassChange ? `Destacar áreas da classe ${riskClass.label}` : 'Destaque disponível no mapa anual com grupos de 5 km'}
              >
                <i style={{ backgroundColor: riskClass.color }} aria-hidden="true" />
                <span>{riskClass.label}</span>
                <small>{riskClass.lower}–{riskClass.upper === 100 ? '100' : `<${riskClass.upper}`}</small>
              </button>
            ))}
            {highlightClass && aggregated && onHighlightClassChange && (
              <button type="button" className="risk-legend-reset" onClick={() => onHighlightClassChange(null)}>
                Mostrar todas as classes
              </button>
            )}
          </div>
          {(!aggregated || !onHighlightClassChange) && <small>O destaque por classe está disponível na visão geral do mapa anual.</small>}
        </details>
      </section>
      {showScars && (
        <div className="scar-legend risk-scar-legend">
          <strong><i className="scar-swatch risk-scar-swatch" aria-hidden="true" /> Áreas queimadas · 2025</strong>
          <span>Marcas no mapa obtidas de um inventário histórico, não contagem de incêndios.</span>
        </div>
      )}
    </div>
  )
}
