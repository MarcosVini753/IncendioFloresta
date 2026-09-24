import type { SusceptibilityModelId } from '../../types/susceptibility'

interface ModelSelectorProps {
  value: SusceptibilityModelId
  models: { id: SusceptibilityModelId; label: string }[]
  onChange: (model: SusceptibilityModelId) => void
  label?: string
}

export function ModelSelector({ value, models, onChange, label = 'Modelo de suscetibilidade' }: ModelSelectorProps) {
  return (
    <section className="control-group" aria-labelledby="model-selector-label">
      <label id="model-selector-label" className="control-label" htmlFor="susceptibility-model">
        {label}
      </label>
      <select
        id="susceptibility-model"
        className="model-selector"
        value={value}
        onChange={(event) => onChange(event.target.value as SusceptibilityModelId)}
      >
        {models.map((model) => (
          <option key={model.id} value={model.id}>
            {model.label}
          </option>
        ))}
      </select>
    </section>
  )
}
