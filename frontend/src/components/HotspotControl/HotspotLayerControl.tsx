interface HotspotLayerControlProps {
  checked: boolean
  count: number | null
  referenceDate: string | null
  loading: boolean
  error: string | null
  onChange: (checked: boolean) => void
}

function hotspotSummary(count: number, referenceDate: string | null) {
  const countLabel = `${count} ${count === 1 ? 'foco' : 'focos'} no Acre`
  return referenceDate ? `${referenceDate} · ${countLabel}` : countLabel
}

export function HotspotLayerControl({
  checked,
  count,
  referenceDate,
  loading,
  error,
  onChange,
}: HotspotLayerControlProps) {
  const unavailable = loading || Boolean(error) || count === null

  return (
    <section className="control-group hotspot-layer-control" aria-labelledby="additional-layers-label">
      <span id="additional-layers-label" className="control-label">
        Camadas adicionais
      </span>

      <label className={`hotspot-toggle${unavailable ? ' unavailable' : ''}`}>
        <input
          type="checkbox"
          checked={!unavailable && checked}
          disabled={unavailable}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="hotspot-toggle-symbol" aria-hidden="true" />
        <span className="hotspot-toggle-copy">
          <strong>Focos de calor — INPE</strong>
          <small>
            {loading
              ? 'Carregando dados…'
              : error
                ? 'Camada indisponível'
                : hotspotSummary(count ?? 0, referenceDate)}
          </small>
        </span>
      </label>

      {error ? (
        <p className="hotspot-control-error" role="alert">
          {error}
        </p>
      ) : (
        <p className="hotspot-control-note">
          Detecções orbitais independentes da data de Perigo; não são incêndios confirmados.
        </p>
      )}
    </section>
  )
}
