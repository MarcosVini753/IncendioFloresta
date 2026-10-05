import { scoreForModel } from '../../data/susceptibility'
import type {
  SelectedSusceptibilityCell,
  RiskScenario,
  SusceptibilityManifest,
  SusceptibilityModelId,
} from '../../types/susceptibility'

interface CellDetailsProps {
  cell: SelectedSusceptibilityCell | null
  scenario: RiskScenario
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

export function CellDetails({ cell, model, scenario, manifest, onClear }: CellDetailsProps) {
  if (!cell) {
    return (
      <aside className="cell-details cell-details-empty">
        <div>
          <span className="eyebrow">Local selecionado</span>
          <h2>Nenhuma célula selecionada</h2>
          <p>Clique em uma célula para comparar os cinco escores científicos agregados.</p>
        </div>
        <span className="cell-details-hint">
          A seleção permanece ativa ao trocar o modelo exibido no mapa.
        </span>
      </aside>
    )
  }

  const properties = cell.feature.properties
  const activeModel = manifest.models.find((candidate) => candidate.id === model)
  const activeScore = scoreForModel(properties, model, scenario)

  return (
    <aside className="cell-details">
      <div className="cell-details-header">
        <div>
          <span className="eyebrow">
            {cell.kind === 'native' ? 'Célula científica original' : 'Célula agregada'}
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
        <small>escore relativo · {scenario === 'regional' ? 'Oeste–Leste' : 'Acre inteiro'} · 2025</small>
      </div>

      <dl className="model-score-list">
        {manifest.models.map((candidate) => (
          <div key={candidate.id} className={candidate.id === model ? 'active' : undefined}>
            <dt>{candidate.label}</dt>
            <dd>{formatScore(scoreForModel(properties, candidate.id, scenario))}</dd>
          </div>
        ))}
      </dl>

      <dl className="cell-metrics">
        <div><dt>Treino</dt><dd>2007–2024</dd></div>
        <div><dt>Clima do modelo</dt><dd>2024</dd></div>
        {cell.kind === 'native' && cell.feature.properties.region && <div><dt>Região científica</dt><dd>{cell.feature.properties.region === 'oeste' ? 'Oeste' : 'Leste'}</dd></div>}
        {model === 'fuzzy_knn' && (scenario === 'unico' ? ['acre'] : ['oeste', 'leste']).map((scope) => (
          <div key={scope}><dt>Vizinhos k · {scope}</dt><dd>{manifest.provenance.models[`fuzzy_knn/${scope}`].parameters.k}</dd></div>
        ))}
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
