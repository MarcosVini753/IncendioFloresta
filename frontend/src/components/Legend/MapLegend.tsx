import { RISK_CLASSES } from '../../data/riskClasses'

interface MapLegendProps {
  modelLabel: string
  aggregated?: boolean
  showScars?: boolean
  rasterReduced?: boolean
}

export function MapLegend({
  modelLabel,
  aggregated = false,
  showScars = false,
  rasterReduced = false,
}: MapLegendProps) {
  const interpretation = aggregated
    ? 'Cada grupo de 5 km recebe a classe da média dos percentis dos seus pixels válidos.'
    : rasterReduced
      ? 'A cor representa a média dos percentis na versão reduzida do raster.'
      : 'A cor representa o percentil do pixel científico original.'

  return (
    <div className="map-legend-stack">
      <section className="map-legend" aria-label={`Legenda de índice percentil: ${modelLabel}`}>
        <div className="map-legend-heading">
          <strong>Índice percentil</strong>
          <span>{modelLabel}</span>
        </div>
        <div className="risk-legend-swatches" role="img" aria-label="Cinco classes de índice percentil: muito baixo, baixo, moderado, alto e muito alto">
          {RISK_CLASSES.map((riskClass) => (
            <span
              key={riskClass.id}
              style={{ backgroundColor: riskClass.color }}
              title={`${riskClass.label}: ${riskClass.lower} a ${riskClass.upper}`}
            />
          ))}
        </div>
        <div className="risk-legend-extremes">
          <span>Menor índice</span>
          <span>Maior índice</span>
        </div>
        <details className="map-legend-help">
          <summary>Entenda as classes</summary>
          <p>{interpretation}</p>
          <ul>
            {RISK_CLASSES.map((riskClass) => (
              <li key={riskClass.id}>
                <i style={{ backgroundColor: riskClass.color }} aria-hidden="true" />
                <span>{riskClass.label}: {riskClass.lower}–{riskClass.upper === 100 ? '100' : `<${riskClass.upper}`}</span>
              </li>
            ))}
          </ul>
          <p>Percentil é posição no ranking estadual, não probabilidade de incêndio.</p>
        </details>
      </section>
      {showScars && (
        <div className="scar-legend risk-scar-legend">
          <strong><i className="scar-swatch risk-scar-swatch" aria-hidden="true" /> Cicatrizes · 2025</strong>
          <span>Observações históricas, não incêndios confirmados.</span>
        </div>
      )}
    </div>
  )
}
