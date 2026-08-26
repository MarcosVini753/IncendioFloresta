import type { LayerType } from '../../types/fire'

interface MapLegendProps {
  layer: LayerType
}

export function MapLegend({ layer }: MapLegendProps) {
  const label = layer === 'risk' ? 'Risco' : layer === 'danger' ? 'Perigo' : 'Alerta'

  return (
    <div className="map-legend" aria-label={`Legenda do índice de ${label.toLowerCase()}`}>
      <strong>{label}</strong>
      <div className="legend-gradient" />
      <div className="legend-scale">
        <span>0 · baixo</span>
        <span>1 · alto</span>
      </div>
    </div>
  )
}
