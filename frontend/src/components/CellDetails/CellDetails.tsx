import { scoreForModel } from '../../data/susceptibility'
import type {
  AggregatedCellFeature,
  SusceptibilityManifest,
  SusceptibilityModelId,
} from '../../types/susceptibility'

interface CellDetailsProps {
  cell: AggregatedCellFeature | null
  model: SusceptibilityModelId
  manifest: SusceptibilityManifest
  onClear: () => void
}

function formatScore(value: number) {
  return new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(value)
}

export function CellDetails({ cell, model, manifest, onClear }: CellDetailsProps) {
  if (!cell) {
    return (
      <aside className="cell-details cell-details-empty">
        <div>
          <span className="eyebrow">Local selecionado</span>
          <h2>Nenhuma célula selecionada</h2>
          <p>Clique em uma célula para comparar os quatro escores científicos agregados.</p>
        </div>
        <span className="cell-details-hint">
          A seleção permanece ativa ao trocar o modelo exibido no mapa.
        </span>
      </aside>
    )
  }

  const properties = cell.properties
  const activeModel = manifest.models.find((candidate) => candidate.id === model)
  const activeScore = scoreForModel(properties, model)

  return (
    <aside className="cell-details">
      <div className="cell-details-header">
        <div>
          <span className="eyebrow">Célula agregada</span>
          <h2>{properties.id}</h2>
        </div>
        <button type="button" className="clear-selection" onClick={onClear}>
          Limpar
        </button>
      </div>

      <div className="active-score">
        <span>{activeModel?.label ?? model}</span>
        <strong>{formatScore(activeScore)}</strong>
        <small>escore relativo</small>
      </div>

      <dl className="model-score-list">
        {manifest.models.map((candidate) => (
          <div key={candidate.id} className={candidate.id === model ? 'active' : undefined}>
            <dt>{candidate.label}</dt>
            <dd>{formatScore(scoreForModel(properties, candidate.id))}</dd>
          </div>
        ))}
      </dl>

      <dl className="cell-metrics">
        <div>
          <dt>Células científicas</dt>
          <dd>{properties.n_source_cells.toLocaleString('pt-BR')}</dd>
        </div>
        <div>
          <dt>Agregação</dt>
          <dd>Média</dd>
        </div>
        <div>
          <dt>Latitude</dt>
          <dd>{properties.centroid[1].toFixed(4)}</dd>
        </div>
        <div>
          <dt>Longitude</dt>
          <dd>{properties.centroid[0].toFixed(4)}</dd>
        </div>
      </dl>

      <p className="cell-details-note">
        Coordenada representativa: média dos centroides-fonte. Resolução original aproximada:{' '}
        {Math.round(manifest.original_grid.cell_width_m)} ×{' '}
        {Math.round(manifest.original_grid.cell_height_m)} m.
      </p>
    </aside>
  )
}
