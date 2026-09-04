import type { LayerType } from '../../types/fire'

interface LayerSelectorProps {
  value: LayerType
  onChange: (layer: LayerType) => void
}

export function LayerSelector({ value, onChange }: LayerSelectorProps) {
  return (
    <section className="control-group" aria-labelledby="index-layer-label">
      <span id="index-layer-label" className="control-label">
        Índice
      </span>
      <div className="layer-selector" role="tablist" aria-label="Índice exibido no mapa">
        <button
          type="button"
          role="tab"
          aria-selected={value === 'risk'}
          className={value === 'risk' ? 'active' : ''}
          onClick={() => onChange('risk')}
        >
          Risco
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={value === 'danger'}
          className={value === 'danger' ? 'active' : ''}
          onClick={() => onChange('danger')}
        >
          Perigo
        </button>
        <button
          type="button"
          role="tab"
          aria-selected="false"
          disabled
          title="Funcionalidade prevista para uma etapa futura"
        >
          Alerta · em breve
        </button>
      </div>
    </section>
  )
}
