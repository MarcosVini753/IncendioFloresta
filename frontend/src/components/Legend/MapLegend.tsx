import type { LayerType } from '../../types/fire'

interface MapLegendProps {
  layer: LayerType
  showHotspots: boolean
}

export function MapLegend({ layer, showHotspots }: MapLegendProps) {
  const label = layer === 'risk' ? 'Risco' : layer === 'danger' ? 'Perigo' : 'Alerta'

  return (
    <div className="map-legend-stack">
      <div className="map-legend" aria-label={`Legenda do índice de ${label.toLowerCase()}`}>
        <strong>{label}</strong>
        <div className="legend-gradient" />
        <div className="legend-scale">
          <span>0 · baixo</span>
          <span>1 · alto</span>
        </div>
      </div>

      {showHotspots ? (
        <div className="hotspot-legend" aria-label="Legenda dos focos de calor do INPE">
          <strong>Focos de calor — INPE</strong>
          <span>
            <i className="hotspot-legend-point" aria-hidden="true" /> Foco individual
          </span>
          <span>
            <i className="hotspot-legend-cluster" aria-hidden="true" /> Agrupamento de focos
          </span>
        </div>
      ) : null}
    </div>
  )
}
