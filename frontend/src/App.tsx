import { useEffect, useState } from 'react'
import { ClimateSeries } from './components/Chart/ClimateSeries'
import { ClimateDetails } from './components/ClimateDetails/ClimateDetails'
import { ClimateMap } from './components/Map/ClimateMap'
import { TimeSlider } from './components/Timeline/TimeSlider'
import { RiskV4 } from './components/RiskV4/RiskV4'
import { loadClimateProduct } from './data/climate'
import type { ClimateProduct, ClimateVariable } from './types/climate'

function formatPtDate(value: string) {
  return value.split('-').reverse().join('/')
}

export default function App() {
  const [section, setSection] = useState<'risk' | 'climate'>('risk')
  const [climate, setClimate] = useState<ClimateProduct | null>(null)
  const [climateError, setClimateError] = useState<string | null>(null)
  const [climateAttempt, setClimateAttempt] = useState(0)
  const [climateVariable, setClimateVariable] =
    useState<ClimateVariable>('humidity')
  const [climateDate, setClimateDate] = useState('2025-08-25')
  const [showScars, setShowScars] = useState(true)
  const [selectedClimateCell, setSelectedClimateCell] = useState<string | null>(
    null,
  )

  useEffect(() => {
    if (section !== 'climate' || climate) return
    const controller = new AbortController()
    setClimateError(null)
    void loadClimateProduct(controller.signal)
      .then(setClimate)
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setClimateError(
            error instanceof Error
              ? error.message
              : 'Erro ao carregar clima histórico.',
          )
      })
    return () => controller.abort()
  }, [section, climate, climateAttempt])

  const dailyScars =
    climate?.scars.features.filter(
      (feature) => feature.properties.date === climateDate,
    ).length ?? 0
  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <span className="eyebrow">Produto científico experimental</span>
          <h1>Monitoramento de Incêndios Florestais — Acre</h1>
          <p>
            Risco anual da entrega v4 para 2026 e observações históricas de
            2025.
          </p>
        </div>
        <span className="prototype-badge">
          {section === 'climate'
            ? 'Clima histórico · cicatrizes mapeadas · 2025'
            : 'Risco anual experimental — 2026'}
        </span>
      </header>
      <nav className="product-tabs" aria-label="Seção do mapa">
        <button
          type="button"
          className={section === 'risk' ? 'active' : undefined}
          aria-pressed={section === 'risk'}
          onClick={() => setSection('risk')}
        >
          <span className="product-tab-title">Risco · 2026</span>
          <span className="product-tab-description">
            Índice percentil · modelos da v4 · clima de 2025
          </span>
        </button>
        <button
          type="button"
          className={section === 'climate' ? 'active' : undefined}
          aria-pressed={section === 'climate'}
          onClick={() => setSection('climate')}
        >
          <span className="product-tab-title">Clima e cicatrizes · 2025</span>
          <span className="product-tab-description">
            Dados observados · calendário diário
          </span>
        </button>
      </nav>
      <div hidden={section !== 'risk'}>
        <RiskV4 />
      </div>
      {section === 'climate' && (
        <>
          <div className="map-controls climate-controls">
            <section className="control-group">
              <span className="control-label">Variável climática</span>
              <div className="layer-selector">
                <button
                  type="button"
                  className={
                    climateVariable === 'humidity' ? 'active' : undefined
                  }
                  onClick={() => setClimateVariable('humidity')}
                >
                  Umidade relativa
                </button>
                <button
                  type="button"
                  className={
                    climateVariable === 'precipitation' ? 'active' : undefined
                  }
                  onClick={() => setClimateVariable('precipitation')}
                >
                  Precipitação
                </button>
              </div>
            </section>
            <section className="control-group climate-scar-control">
              <span className="control-label">Observações</span>
              <label>
                <input
                  type="checkbox"
                  checked={showScars}
                  onChange={(event) => setShowScars(event.target.checked)}
                />{' '}
                Cicatrizes observadas no dia
              </label>
              <small>
                {dailyScars} pixels classificados em {formatPtDate(climateDate)}
              </small>
            </section>
          </div>
          {climate ? (
            <>
              <TimeSlider
                dates={climate.manifest.dates}
                selectedDate={climateDate}
                onChange={setClimateDate}
              />
              <section className="map-workspace climate-workspace">
                <ClimateMap
                  product={climate}
                  variable={climateVariable}
                  date={climateDate}
                  showScars={showScars}
                  selectedCellId={selectedClimateCell}
                  onCellSelect={setSelectedClimateCell}
                />
                <ClimateDetails
                  product={climate}
                  variable={climateVariable}
                  date={climateDate}
                  cellId={selectedClimateCell}
                  onClear={() => setSelectedClimateCell(null)}
                />
              </section>
              <ClimateSeries
                product={climate}
                variable={climateVariable}
                date={climateDate}
                cellId={selectedClimateCell}
              />
              <section className="scientific-product-note">
                <div>
                  <span className="eyebrow">Dados observados · 2025</span>
                  <strong>Clima e cicatrizes históricos</strong>
                </div>
                <div>
                  <p>
                    Umidade, precipitação e cicatrizes observadas em 2025. As
                    cicatrizes são pixels classificados, não uma contagem de
                    incêndios confirmados. O inventário é limitado. Estes dados
                    não representam as condições observadas de 2026.
                  </p>
                  <details className="scientific-note-details">
                    <summary>Como ler as observações</summary>
                    <p>
                      As cores mostram a média espacial diária. Mínimo, média e
                      máximo descrevem os pixels climáticos de aproximadamente
                      0,1° que intersectam cada célula visual de 0,28°, não
                      extremos ao longo do dia. A duração de acumulação da
                      precipitação em 24 horas não está comprovada. Marcadores
                      vermelhos localizam cicatrizes; ao aproximar, seu contorno
                      aparece. Um dia sem registro não comprova ausência de
                      fogo. O risco anual de 2026 utiliza clima de 2025.
                    </p>
                  </details>
                </div>
              </section>
            </>
          ) : (
            <section className="map-section">
              <div className="map-shell map-status" role="status">
                <strong>
                  {climateError
                    ? 'Não foi possível carregar o clima histórico.'
                    : 'Carregando clima e cicatrizes de 2025…'}
                </strong>
                {climateError && (
                  <>
                    <span>{climateError}</span>
                    <button
                      type="button"
                      onClick={() => setClimateAttempt((v) => v + 1)}
                    >
                      Tentar novamente
                    </button>
                  </>
                )}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  )
}
