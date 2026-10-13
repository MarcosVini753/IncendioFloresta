import { RISK_CLASSES } from '../../data/riskClasses'

interface MapLegendProps {
  modelLabel: string
  aggregated?: boolean
  showScars?: boolean
}
export function MapLegend({ modelLabel, aggregated = false, showScars = false }: MapLegendProps) {
  return (
    <div className="map-legend-stack">
      <div className="map-legend" aria-label={`Escala de índice percentil de risco: ${modelLabel}`}>
        <strong>Risco por classes · {modelLabel}</strong>
        {aggregated
          ? <small>Cor pela classe da média dos percentis das células do quadrado.</small>
          : <small>Cor pelo percentil da célula científica.</small>}
        <div className="risk-class-legend">
          {RISK_CLASSES.map((riskClass) => <span key={riskClass.id}><i style={{ backgroundColor: riskClass.color }} />{riskClass.label} · {riskClass.lower}–{riskClass.upper === 100 ? '100' : `<${riskClass.upper}`}</span>)}
        </div>
        <small>Faixas fixas de posição no ranking; não representam chance de incêndio.</small>
      </div>
      {showScars && <div className="scar-legend risk-scar-legend"><strong><i className="scar-swatch risk-scar-swatch" /> Cicatrizes observadas · 2025</strong><span>Pixels do inventário anual; contorno ao aproximar</span></div>}
    </div>
  )
}
