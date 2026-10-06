interface MapLegendProps {
  modelLabel: string
}

export function MapLegend({ modelLabel }: MapLegendProps) {
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

    </div>
  )
}
