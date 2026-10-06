import { useEffect, useState } from 'react'
import { CellDetails } from './components/CellDetails/CellDetails'
import { ClimateSeries } from './components/Chart/ClimateSeries'
import { ClimateDetails } from './components/ClimateDetails/ClimateDetails'
import { ClimateMap } from './components/Map/ClimateMap'
import { FireMap } from './components/Map/FireMap'
import { ModelSelector } from './components/ModelSelector/ModelSelector'
import { TimeSlider } from './components/Timeline/TimeSlider'
import { loadClimateProduct } from './data/climate'
import { loadNativeGridProduct } from './data/nativeSusceptibility'
import { loadSusceptibilityProduct } from './data/susceptibility'
import type { ClimateProduct, ClimateVariable } from './types/climate'
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
      .then(setClimate)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setClimateError(error instanceof Error ? error.message : 'Erro ao carregar clima histórico.')
        }
      })
    return () => controller.abort()
  }, [section, climate])

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
          <p>Risco 2025 é um escore calculado pelo modelo; clima e cicatrizes são observações de 2025 para contexto.</p>
        </div>
        <span className="prototype-badge">{section === 'climate' ? 'Clima histórico · cicatrizes mapeadas · 2025' : 'Risco anual experimental — 2025'}</span>
      </header>

      <nav className="product-tabs" aria-label="Seção do mapa">
        <button type="button" className={section === 'susceptibility' ? 'active' : undefined} onClick={() => setSection('susceptibility')}>Risco</button>
        <button type="button" className={section === 'climate' ? 'active' : undefined} onClick={() => setSection('climate')}>Clima e cicatrizes · 2025</button>
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
                <p>Esta seção mostra dados observados de 2025, não escores produzidos pelo modelo: o clima descreve as condições daquele ano e as cicatrizes ajudam a contextualizar e avaliar o mapa de Risco. As cicatrizes são pixels classificados em um raster — não são uma contagem de incêndios confirmados — e o inventário disponível é limitado; a ausência de registro num dia não comprova ausência de fogo. A precipitação é o valor do produto, sem duração de acumulação em 24 horas comprovada. As cores mostram a média espacial diária; o painel informa mínimo, média e máximo entre pixels climáticos de aproximadamente 0,1° que intersectam cada célula visual de 0,28°. Marcadores vermelhos localizam pixels classificados como cicatriz; ao aproximar, seu contorno aparece.</p>
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
      <div className="map-controls">
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
          <section className="scientific-product-note">
            <div>
              <span className="eyebrow">Resultado calculado pelo modelo</span>
              <strong>Risco anual experimental — 2025</strong>
            </div>
            <p>
              Este mapa é um escore calculado pelo modelo para 2025, reconstruído com dados de treino de 2007–2024 e clima de 2024 — não uma medição direta das condições de fogo em 2025. É experimental, não uma previsão operacional. Paisagem baseada em insumos de 2003–2013. A divisão Oeste–Leste é científica, não administrativa, e pode produzir descontinuidades. A avaliação de 2025 possui poucas células positivas; não equivale a uma contagem de incêndios. Os escores são relativos e não
              representam probabilidades calibradas. Cada
              célula visível reúne, por média aritmética, células científicas de aproximadamente
              893 × 598 m. O modelo ativo é{' '}
              <strong>{activeModel.label}</strong>.
              {selectedModel === 'xgboost' && ' O XGBoost foi retreinado no ambiente atual; suas métricas recalculadas diferem do relatório recebido e estão registradas separadamente no manifesto.'}
            </p>
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
