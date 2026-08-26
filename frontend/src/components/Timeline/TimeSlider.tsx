interface TimeSliderProps {
  dates: string[]
  selectedDate: string
  onChange: (date: string) => void
}

function formatDate(date: string) {
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${date}T00:00:00Z`))
}

export function TimeSlider({ dates, selectedDate, onChange }: TimeSliderProps) {
  const index = Math.max(0, dates.indexOf(selectedDate))

  function move(delta: number) {
    const nextIndex = Math.min(dates.length - 1, Math.max(0, index + delta))
    onChange(dates[nextIndex])
  }

  return (
    <section className="timeline-card" aria-label="Navegação temporal">
      <div className="timeline-header">
        <div>
          <span className="eyebrow">Data selecionada</span>
          <strong>{formatDate(selectedDate)}</strong>
        </div>
        <div className="timeline-actions">
          <button type="button" onClick={() => move(-1)} disabled={index === 0} aria-label="Dia anterior">
            ←
          </button>
          <button
            type="button"
            onClick={() => move(1)}
            disabled={index === dates.length - 1}
            aria-label="Próximo dia"
          >
            →
          </button>
        </div>
      </div>

      <input
        type="range"
        min={0}
        max={dates.length - 1}
        step={1}
        value={index}
        onChange={(event) => onChange(dates[Number(event.target.value)])}
        aria-label="Selecionar data"
      />

      <div className="timeline-extremes">
        <span>{formatDate(dates[0])}</span>
        <span>{formatDate(dates[dates.length - 1])}</span>
      </div>
    </section>
  )
}
