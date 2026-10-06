interface MapLegendProps {
  modelLabel: string
  showScars?: boolean
}

export function MapLegend({ modelLabel, showScars = false }: MapLegendProps) {
  return (
    <div className="map-legend-stack">
      <div className="map-legend" aria-label={`Escala percentual do escore relativo de risco: ${modelLabel}`}>
        <strong>Escore relativo de Risco · {modelLabel}</strong>
        <div className="legend-gradient" />
        <div className="legend-scale">
          <span>0% · menor</span>
          <span>100% · maior</span>
        </div>
      </div>
      {showScars && <div className="scar-legend risk-scar-legend"><strong><i className="scar-swatch risk-scar-swatch" /> Cicatrizes observadas · 2025</strong><span>Pixels do inventário anual; contorno ao aproximar</span></div>}
    </div>
  )
}
