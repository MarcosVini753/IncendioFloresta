import type {
  SusceptibilityModelId,
  SusceptibilityModelManifest,
} from '../../types/susceptibility'

interface ModelSelectorProps {
  value: SusceptibilityModelId
  models: SusceptibilityModelManifest[]
  onChange: (model: SusceptibilityModelId) => void
}

export function ModelSelector({ value, models, onChange }: ModelSelectorProps) {
  return (
    <section className="control-group" aria-labelledby="model-selector-label">
      <label id="model-selector-label" className="control-label" htmlFor="susceptibility-model">
        Modelo de suscetibilidade
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
