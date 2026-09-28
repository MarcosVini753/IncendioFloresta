import { cellStats } from '../../data/climate'
import type { ClimateProduct, ClimateVariable } from '../../types/climate'

interface ClimateDetailsProps {
  product: ClimateProduct
  variable: ClimateVariable
  date: string
  cellId: string | null
  onClear: () => void
}

function format(value: number | null, unit: string) {
  return value === null ? 'Sem dado' : `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value)} ${unit}`
}

export function ClimateDetails({ product, variable, date, cellId, onClear }: ClimateDetailsProps) {
  if (!cellId) {
    return <aside className="cell-details cell-details-empty"><div><span className="eyebrow">Clima local</span><h2>Selecione uma célula</h2><p>Clique no mapa para consultar mínimo, média e máximo espaciais no dia escolhido.</p></div><span className="cell-details-hint">O cinza indica ausência de dados climáticos naquele setor.</span></aside>
  }
  const index = product.manifest.cell_order.indexOf(cellId)
  const stats = cellStats(product, variable, date, cellId)
  const unit = product.manifest.variables[variable].unit
  const center = product.grid.features[index].properties.centroid
  return (
    <aside className="cell-details">
      <div className="cell-details-header"><div><span className="eyebrow">Célula visual · {date.split('-').reverse().join('/')}</span><h2>{cellId}</h2></div><button type="button" className="clear-selection" onClick={onClear}>Limpar</button></div>
      <div className="active-score"><span>{variable === 'humidity' ? 'Umidade relativa média' : 'Precipitação média'}</span><strong>{format(stats[1], unit)}</strong><small>Média espacial ponderada pela área dos pixels</small></div>
      <dl className="cell-metrics">
        <div><dt>Mínimo</dt><dd>{format(stats[0], unit)}</dd></div>
        <div><dt>Máximo</dt><dd>{format(stats[2], unit)}</dd></div>
        <div><dt>Pixels válidos</dt><dd>{product.manifest.n_valid_pixels[index]}</dd></div>
        <div><dt>Centroide</dt><dd>{center[1].toFixed(3)}, {center[0].toFixed(3)}</dd></div>
      </dl>
      <p className="cell-details-note">Mínimo e máximo entre pixels climáticos que intersectam a célula neste dia. Não representam extremos horários. Resolução climática aproximada: 0,1°.</p>
    </aside>
  )
}
