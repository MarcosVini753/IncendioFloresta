import type { LayerType } from '../../types/fire'

interface LayerSelectorProps {
  value: LayerType
  onChange: (layer: LayerType) => void
}

export function LayerSelector({ value, onChange }: LayerSelectorProps) {
  return (
    <div className="layer-selector" role="tablist" aria-label="Índice exibido no mapa">
      <button
        type="button"
        className={value === 'risk' ? 'active' : ''}
        onClick={() => onChange('risk')}
      >
        Risco
      </button>
      <button
        type="button"
        className={value === 'danger' ? 'active' : ''}
        onClick={() => onChange('danger')}
      >
        Perigo
      </button>
      <button type="button" disabled title="Funcionalidade prevista para uma etapa futura">
        Alerta · em breve
      </button>
    </div>
  )
}
