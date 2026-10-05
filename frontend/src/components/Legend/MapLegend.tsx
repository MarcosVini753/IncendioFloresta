interface MapLegendProps {
  modelLabel: string
}

export function MapLegend({ modelLabel }: MapLegendProps) {
  return (
    <div className="map-legend-stack">
      <div className="map-legend" aria-label={`Legenda de risco: ${modelLabel}`}>
        <strong>Risco · {modelLabel}</strong>
        <div className="legend-gradient" />
        <div className="legend-scale">
          <span>0 · menor</span>
          <span>1 · maior</span>
        </div>
      </div>

    </div>
  )
}
