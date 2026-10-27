import { useEffect, useState } from 'react'
import { loadRiskV4 } from '../../data/riskV4'
import type { RiskV4Model, RiskV4Selection, RiskV4Product } from '../../types/riskV4'

interface Props {
  year: 2025 | 2026
  selection: RiskV4Selection
  model: RiskV4Model
}

export function RiskYearComparison({ year, selection, model }: Props) {
  const [open, setOpen] = useState(false)
  const [other, setOther] = useState<RiskV4Product | null>(null)
  const [error, setError] = useState('')
  const comparisonYear = year === 2025 ? 2026 : 2025
  const id = selection.properties.id
  useEffect(() => {
    setOpen(false)
  }, [id, year])
  useEffect(() => {
    if (!open || selection.kind !== 'aggregated' || other?.manifest.year === comparisonYear) return
    const controller = new AbortController()
    setError('')
    void loadRiskV4(comparisonYear, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setOther(value) })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(
          reason instanceof Error ? reason.message : 'Não foi possível carregar o outro ano.',
        )
      })
    return () => controller.abort()
  }, [open, selection.kind, comparisonYear, other])

  if (selection.kind !== 'aggregated') return null

  const row = other?.manifest.year === comparisonYear
    ? other.cells.features.find((feature) => feature.properties.id === id)?.properties
    : null
  const current = selection.properties[`percentile_${model}`]
  const previous = row?.[`percentile_${model}`]
  const gap = typeof previous === 'number' ? current - previous : null

  return (
    <details
      className="risk-year-compare"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Comparar esta área com {comparisonYear}</summary>
      <div className="risk-year-compare-body">
        {!other && !error && <p role="status">Carregando o mapa de {comparisonYear}…</p>}
        {error && <p role="alert">Não foi possível consultar {comparisonYear}: {error}</p>}
        {other && row && gap !== null && (
          <>
            <div className="risk-year-comparison-grid">
              <div>
                <small>{year} · mapa atual</small>
                <strong>{current.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}</strong>
              </div>
              <div>
                <small>{comparisonYear} · mesmo grupo</small>
                <strong>{previous?.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}</strong>
              </div>
            </div>
            <p>
              {Math.abs(gap) < 0.05
                ? 'A posição relativa permaneceu praticamente igual.'
                : `No ranking do mapa de ${year}, este grupo aparece ${Math.abs(gap).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} pontos ${gap > 0 ? 'acima' : 'abaixo'} de sua posição no mapa de ${comparisonYear}.`}
            </p>
            <p className="risk-year-compare-note">
              São mapas de anos diferentes, com treinamentos e referências climáticas
              diferentes. A diferença é entre índices relativos, não uma medição de
              aumento ou redução do risco real.
            </p>
          </>
        )}
        {other && !row && <p>Não encontramos o mesmo grupo de 5 km no mapa de {comparisonYear}.</p>}
      </div>
    </details>
  )
}
