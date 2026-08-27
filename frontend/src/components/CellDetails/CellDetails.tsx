import type { LayerType, PrototypeCell } from '../../types/fire'

interface CellDetailsProps {
  cell: PrototypeCell | null
  layer: LayerType
  selectedDate: string
  onClear: () => void
}

function formatDate(date: string) {
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${date}T00:00:00Z`))
}

export function CellDetails({ cell, layer, selectedDate, onClear }: CellDetailsProps) {
  if (!cell) {
    return (
      <aside className="cell-details cell-details-empty">
        <div>
          <span className="eyebrow">Local selecionado</span>
          <h2>Nenhuma célula selecionada</h2>
          <p>Clique em uma célula da malha para inspecionar seus valores e sua série temporal.</p>
        </div>
        <span className="cell-details-hint">A seleção permanecerá ativa ao trocar a data ou a camada.</span>
      </aside>
    )
  }

  const value = layer === 'risk' ? cell.risk : cell.danger[selectedDate]
  const indexLabel = layer === 'risk' ? 'Risco' : layer === 'danger' ? 'Perigo' : 'Alerta'

  return (
    <aside className="cell-details">
      <div className="cell-details-header">
        <div>
          <span className="eyebrow">Célula selecionada</span>
          <h2>{cell.id}</h2>
        </div>
        <button type="button" className="clear-selection" onClick={onClear}>
          Limpar
        </button>
      </div>

      <dl className="cell-metrics">
        <div>
          <dt>{indexLabel}</dt>
          <dd>{value == null ? 'Sem dado' : value.toFixed(2)}</dd>
        </div>
        {layer === 'danger' ? (
          <div>
            <dt>Data</dt>
            <dd>{formatDate(selectedDate)}</dd>
          </div>
        ) : (
          <div>
            <dt>Temporalidade</dt>
            <dd>Camada estática</dd>
          </div>
        )}
        <div>
          <dt>Latitude</dt>
          <dd>{cell.centroid[1].toFixed(4)}</dd>
        </div>
        <div>
          <dt>Longitude</dt>
          <dd>{cell.centroid[0].toFixed(4)}</dd>
        </div>
      </dl>

      <p className="cell-details-note">
        Valores simulados para validação da interação. A malha não representa a resolução científica final.
      </p>
    </aside>
  )
}
