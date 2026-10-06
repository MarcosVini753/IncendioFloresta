import { useEffect, useState } from 'react'
import { CellDetails } from './components/CellDetails/CellDetails'
import { ClimateSeries } from './components/Chart/ClimateSeries'
import { ClimateDetails } from './components/ClimateDetails/ClimateDetails'
import { ClimateMap } from './components/Map/ClimateMap'
import { FireMap } from './components/Map/FireMap'
import { ModelSelector } from './components/ModelSelector/ModelSelector'
import { RiskEvaluation } from './components/RiskEvaluation/RiskEvaluation'
import { TimeSlider } from './components/Timeline/TimeSlider'
import { loadClimateProduct, loadScarProduct } from './data/climate'
import { loadNativeGridProduct } from './data/nativeSusceptibility'
import { loadSusceptibilityProduct } from './data/susceptibility'
import type { ClimateProduct, ClimateVariable, ScarProduct } from './types/climate'
import type {
  NativeGridProduct,
  RiskScenario,
  SelectedSusceptibilityCell,
  SusceptibilityModelId,
  SusceptibilityProduct,
} from './types/susceptibility'

function formatPtDate(value: string | undefined) {
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : null
}

export default function App() {
  const [section, setSection] = useState<'susceptibility' | 'climate'>('susceptibility')
  const [climate, setClimate] = useState<ClimateProduct | null>(null)
  const [climateError, setClimateError] = useState<string | null>(null)
  const [climateVariable, setClimateVariable] = useState<ClimateVariable>('humidity')
  const [climateDate, setClimateDate] = useState('2025-08-25')
  const [showScars, setShowScars] = useState(true)
  const [showRiskScars, setShowRiskScars] = useState(true)
  const [riskScars, setRiskScars] = useState<ScarProduct | null>(null)
  const [riskScarsLoading, setRiskScarsLoading] = useState(false)
  const [riskScarsError, setRiskScarsError] = useState<string | null>(null)
  const [riskScarsRetry, setRiskScarsRetry] = useState(0)
  const [selectedClimateCell, setSelectedClimateCell] = useState<string | null>(null)
  const [product, setProduct] = useState<SusceptibilityProduct | null>(null)
  const [selectedModel, setSelectedModel] = useState<SusceptibilityModelId>('random_forest')
  const [scenario, setScenario] = useState<RiskScenario>('regional')
  const [selectedCell, setSelectedCell] = useState<SelectedSusceptibilityCell | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [nativeProduct, setNativeProduct] = useState<NativeGridProduct | null>(null)
  const [nativeIndexError, setNativeIndexError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    loadSusceptibilityProduct(controller.signal)
      .then((result) => {
        setProduct(result)
        setSelectedModel(result.manifest.default_model)
        setScenario(result.manifest.default_scenario)
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setLoadError(
            error instanceof Error ? error.message : 'Erro ao carregar o risco experimental.',
          )
        }
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (section !== 'climate' || climate) return
    const controller = new AbortController()
    setClimateError(null)
    loadClimateProduct(controller.signal)
      .then((result) => {
        setClimate(result)
        setRiskScars({ manifest: result.manifest, scars: result.scars })
        setRiskScarsError(null)
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setClimateError(error instanceof Error ? error.message : 'Erro ao carregar clima histórico.')
        }
      })
    return () => controller.abort()
  }, [section, climate])

  useEffect(() => {
    if (section !== 'susceptibility' || !showRiskScars || riskScars) {
      setRiskScarsLoading(false)
      return
    }
    const controller = new AbortController()
    setRiskScarsLoading(true)
    setRiskScarsError(null)
    loadScarProduct(controller.signal)
      .then(setRiskScars)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setRiskScarsError(error instanceof Error ? error.message : 'Erro ao carregar as cicatrizes de 2025.')
        }
      })
      .finally(() => { if (!controller.signal.aborted) setRiskScarsLoading(false) })
    return () => controller.abort()
  }, [section, showRiskScars, riskScars, riskScarsRetry])

  useEffect(() => {
    const controller = new AbortController()
    loadNativeGridProduct(controller.signal)
      .then(setNativeProduct)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setNativeIndexError(
            error instanceof Error ? error.message : 'Erro ao carregar a grade científica original.',
          )
        }
      })
    return () => controller.abort()
  }, [])

  const selectedCellId = selectedCell?.feature.properties.id ?? null
  const activeModel = product?.manifest.models.find((model) => model.id === selectedModel)
  const dailyScars = climate?.scars.features.filter((feature) => feature.properties.date === climateDate).length ?? 0

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <span className="eyebrow">Produto científico experimental</span>
          <h1>Monitoramento de Incêndios Florestais — Acre</h1>
          <p>Risco calculado e dados observados do Acre em 2025.</p>
        </div>
        <span className="prototype-badge">{section === 'climate' ? 'Clima histórico · cicatrizes mapeadas · 2025' : 'Risco anual experimental — 2025'}</span>
      </header>

      <nav className="product-tabs" aria-label="Seção do mapa">
        <button
          type="button"
          className={section === 'susceptibility' ? 'active' : undefined}
          aria-pressed={section === 'susceptibility'}
          aria-labelledby="risk-tab-label"
          aria-describedby="risk-tab-description"
          onClick={() => setSection('susceptibility')}
        >
          <span id="risk-tab-label" className="product-tab-title">Risco</span>
          <span id="risk-tab-description" className="product-tab-description">Resultado do modelo · 2025 · clima de 2024</span>
        </button>
        <button
          type="button"
          className={section === 'climate' ? 'active' : undefined}
          aria-pressed={section === 'climate'}
          aria-labelledby="climate-tab-label"
          aria-describedby="climate-tab-description"
          onClick={() => setSection('climate')}
        >
          <span id="climate-tab-label" className="product-tab-title">Clima e cicatrizes · 2025</span>
          <span id="climate-tab-description" className="product-tab-description">Dados observados · calendário diário</span>
        </button>
      </nav>

      {section === 'climate' ? (
        <>
          <div className="map-controls climate-controls">
            <section className="control-group">
              <span className="control-label">Variável climática</span>
              <div className="layer-selector">
                <button type="button" className={climateVariable === 'humidity' ? 'active' : undefined} onClick={() => setClimateVariable('humidity')}>Umidade relativa</button>
                <button type="button" className={climateVariable === 'precipitation' ? 'active' : undefined} onClick={() => setClimateVariable('precipitation')}>Precipitação</button>
              </div>
            </section>
            <section className="control-group climate-scar-control">
              <span className="control-label">Observações</span>
              <label><input type="checkbox" checked={showScars} onChange={(event) => setShowScars(event.target.checked)} /> Cicatrizes observadas no dia</label>
              <small>{dailyScars} pixels classificados em {formatPtDate(climateDate)}</small>
            </section>
          </div>
          {climate ? (
            <>
              <TimeSlider dates={climate.manifest.dates} selectedDate={climateDate} onChange={setClimateDate} />
              <section className="map-workspace climate-workspace">
                <ClimateMap product={climate} variable={climateVariable} date={climateDate} showScars={showScars} selectedCellId={selectedClimateCell} onCellSelect={setSelectedClimateCell} />
                <ClimateDetails product={climate} variable={climateVariable} date={climateDate} cellId={selectedClimateCell} onClear={() => setSelectedClimateCell(null)} />
              </section>
              <ClimateSeries product={climate} variable={climateVariable} date={climateDate} cellId={selectedClimateCell} />
              <section className="scientific-product-note">
                <div><span className="eyebrow">Dados observados · 2025</span><strong>Clima e cicatrizes dão contexto ao resultado do modelo</strong></div>
                <div>
                  <p>Umidade, precipitação e cicatrizes observadas em 2025 ajudam a avaliar o Risco. As cicatrizes são pixels classificados, não uma contagem de incêndios confirmados. O inventário é limitado.</p>
                  <details className="scientific-note-details">
                    <summary>Como ler as observações</summary>
                    <p>As cores mostram a média espacial diária. Mínimo, média e máximo descrevem os pixels climáticos de aproximadamente 0,1° que intersectam cada célula visual de 0,28°, não extremos ao longo do dia. A duração de acumulação da precipitação em 24 horas não está comprovada. Marcadores vermelhos localizam cicatrizes; ao aproximar, seu contorno aparece. Um dia sem registro não comprova ausência de fogo. O clima exibido é de 2025; o Risco anual utiliza clima de 2024.</p>
                  </details>
                </div>
              </section>
            </>
          ) : (
            <section className="map-section">
              <div className="map-shell map-status" role="status">
                <strong>{climateError ? 'Não foi possível carregar o clima histórico.' : 'Carregando clima e cicatrizes de 2025…'}</strong>
                {climateError && <span>{climateError}</span>}
              </div>
            </section>
          )}
        </>
      ) : (
      <>
      <div className="map-controls risk-map-controls">
        {product && <section className="control-group"><span className="control-label">Cenário científico</span><div className="layer-selector">{product.manifest.scenarios.map((item) => <button key={item.id} type="button" className={scenario === item.id ? 'active' : undefined} onClick={() => setScenario(item.id)}>{item.label}</button>)}</div></section>}
        {product ? (
          <ModelSelector
            value={selectedModel}
            models={product.manifest.models}
            onChange={setSelectedModel}
          />
        ) : (
          <section className="control-group">
            <span className="control-label">Modelo de risco</span>
            <span className="control-loading">Carregando produto…</span>
          </section>
        )}
        <section className="control-group risk-scar-control">
          <span className="control-label">Observações sobre o Risco</span>
          <label><input type="checkbox" checked={showRiskScars} onChange={(event) => setShowRiskScars(event.target.checked)} /><i className="scar-swatch risk-scar-swatch" /> Cicatrizes observadas · 2025</label>
          <small role="status">{riskScarsLoading ? 'Carregando o inventário anual…' : riskScars ? `${riskScars.scars.features.length} pixels classificados · todo o ano` : 'Inventário anual de pixels classificados; cobertura limitada.'}</small>
          {showRiskScars && riskScarsError && <div className="overlay-error" role="alert"><span>{riskScarsError}</span><button type="button" className="clear-selection" onClick={() => setRiskScarsRetry((value) => value + 1)}>Tentar novamente</button></div>}
        </section>
      </div>

      {product && activeModel ? (
        <>
          <section className="map-workspace">
            <div className="map-section">
              <FireMap
                scenario={scenario}
                model={selectedModel}
                modelLabel={activeModel.label}
                cells={product.cells}
                boundary={product.boundary}
                bounds={product.bounds}
                selectedCellId={selectedCellId}
                onCellSelect={setSelectedCell}
                nativeProduct={nativeProduct}
                nativeIndexError={nativeIndexError}
                scars={riskScars?.scars ?? null}
                showScars={showRiskScars}
              />
            </div>
            <CellDetails
              scenario={scenario}
              cell={selectedCell}
              model={selectedModel}
              manifest={product.manifest}
              onClear={() => setSelectedCell(null)}
            />
          </section>
          <RiskEvaluation manifest={product.manifest} model={selectedModel} scenario={scenario} />
          <section className="scientific-product-note">
            <div>
              <span className="eyebrow">Resultado calculado pelo modelo</span>
              <strong>Risco anual experimental — 2025</strong>
            </div>
            <div>
              <p>
                Risco de 2025 calculado por <strong>{activeModel.label}</strong>, com treino de 2007–2024 e clima de 2024. Os percentuais mostram um escore relativo, não a chance de ocorrer um incêndio. Resultado experimental, sem uso operacional.
              </p>
              {selectedModel === 'xgboost' && <p className="model-validation-note">XGBoost: as métricas recalculadas diferem do relatório recebido; ambas estão registradas no manifesto.</p>}
              <details className="scientific-note-details">
                <summary>Dados e limites do modelo</summary>
                <p>A paisagem usa insumos de 2003–2013. A divisão Oeste–Leste segue um corte científico, não limites administrativos, e pode gerar descontinuidades. A avaliação de 2025 tem poucas células positivas. Os escores não são probabilidades calibradas nem medições diretas de fogo. Na malha agregada, cada valor é a média de células científicas de aproximadamente 893 × 598 m; na grade original, é o escore da célula individual.</p>
              </details>
            </div>
          </section>
        </>
      ) : (
        <section className="map-section">
          <div className="map-shell map-status" role="status">
            {loadError ? (
              <>
                <strong>Não foi possível carregar o risco experimental.</strong>
                <span>{loadError}</span>
              </>
            ) : (
              <>
                <strong>Carregando o produto científico…</strong>
                <span>Validando manifesto, limite do Acre e escores dos cinco modelos.</span>
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
