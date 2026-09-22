interface MapLegendProps {
  modelLabel: string
  showHotspots: boolean
}

export function MapLegend({ modelLabel, showHotspots }: MapLegendProps) {
  return (
    <div className="map-legend-stack">
      <div className="map-legend" aria-label={`Legenda de suscetibilidade: ${modelLabel}`}>
        <strong>Suscetibilidade · {modelLabel}</strong>
        <div className="legend-gradient" />
        <div className="legend-scale">
          <span>0 · menor</span>
          <span>1 · maior</span>
        </div>
      </div>

      {showHotspots ? (
        <div className="hotspot-legend" aria-label="Legenda dos focos de calor do INPE">
          <strong>Focos de calor — INPE</strong>
          <span><i className="hotspot-legend-point" aria-hidden="true" /> Foco individual</span>
          <span><i className="hotspot-legend-cluster" aria-hidden="true" /> Agrupamento de focos</span>
        </div>
      ) : null}
    </div>
  )
}
