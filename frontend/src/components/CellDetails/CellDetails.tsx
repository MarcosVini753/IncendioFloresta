import { scoreForModel } from '../../data/susceptibility'
import type {
  SelectedSusceptibilityCell,
  SusceptibilityManifest,
  SusceptibilityModelId,
} from '../../types/susceptibility'
import type { DangerManifest } from '../../types/danger'

interface CellDetailsProps {
  cell: SelectedSusceptibilityCell | null
  model: SusceptibilityModelId
  manifest: SusceptibilityManifest | DangerManifest
  date?: string
  productLabel?: string
  onClear: () => void
}

function formatScore(value: number) {
  return new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(value)
}

function formatDate(value: string) {
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}

export function CellDetails({
  cell, model, manifest, date, productLabel = 'Suscetibilidade', onClear,
}: CellDetailsProps) {
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

  const properties = cell.feature.properties
  const activeModel = manifest.models.find((candidate) => candidate.id === model)
  const activeScore = scoreForModel(properties, model)

  return (
    <aside className="cell-details">
      <div className="cell-details-header">
        <div>
          <span className="eyebrow">
            {cell.kind === 'native' ? 'Célula científica original' : `${productLabel} · célula agregada`}
          </span>
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
        {date ? <div><dt>Data</dt><dd>{formatDate(date)}</dd></div> : null}
        {cell.kind === 'native' ? (
          <>
            <div><dt>Índice X</dt><dd>{cell.feature.properties.grid_x}</dd></div>
            <div><dt>Índice Y</dt><dd>{cell.feature.properties.grid_y}</dd></div>
          </>
        ) : (
          <div>
            <dt>Células científicas</dt>
            <dd>{cell.feature.properties.n_source_cells.toLocaleString('pt-BR')}</dd>
          </div>
        )}
        <div>
          <dt>Agregação</dt>
          <dd>{cell.kind === 'native' ? 'Nenhuma' : 'Média'}</dd>
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
        {cell.kind === 'native'
          ? 'Centroide da célula original.'
          : 'Coordenada representativa: média dos centroides-fonte.'}{' '}
        Dimensões aproximadas: {Math.round(manifest.original_grid.cell_width_m)} ×{' '}
        {Math.round(manifest.original_grid.cell_height_m)} m.
      </p>
    </aside>
  )
}
