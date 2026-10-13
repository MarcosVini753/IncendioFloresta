interface MapLegendProps {
  modelLabel: string
  aggregated?: boolean
  showScars?: boolean
}

export function MapLegend({ modelLabel, aggregated = false, showScars = false }: MapLegendProps) {
  return (
    <div className="map-legend-stack">
      <div className="map-legend" aria-label={`Escala de índice percentil de risco: ${modelLabel}`}>
        <strong>Índice percentil de Risco · {modelLabel}</strong>
        <div className="legend-gradient" />
        <div className="legend-scale">
          <span>0 · menor</span>
          <span>100 · maior</span>
        </div>
        <small>Posição relativa no ranking; não é chance de incêndio.</small>
        <small>{aggregated ? 'Célula grande: cor da célula menor de maior risco.' : 'Grade original: cor pelo percentil de cada célula.'}</small>
      </div>
      {showScars && <div className="scar-legend risk-scar-legend"><strong><i className="scar-swatch risk-scar-swatch" /> Cicatrizes observadas · 2025</strong><span>Pixels do inventário anual; contorno ao aproximar</span></div>}
    </div>
  )
}
