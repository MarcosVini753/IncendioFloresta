import { useEffect, useState } from 'react'
import { CellDetails } from './components/CellDetails/CellDetails'
import { ClimateDetails } from './components/ClimateDetails/ClimateDetails'
import { HotspotLayerControl } from './components/HotspotControl/HotspotLayerControl'
import { ClimateMap } from './components/Map/ClimateMap'
import { FireMap } from './components/Map/FireMap'
import { ModelSelector } from './components/ModelSelector/ModelSelector'
import { TimeSlider } from './components/Timeline/TimeSlider'
import { loadClimateProduct } from './data/climate'
import { loadInpeHotspots } from './data/inpeHotspots'
import { loadNativeGridProduct } from './data/nativeSusceptibility'
import { loadSusceptibilityProduct } from './data/susceptibility'
import type { InpeHotspotCollection } from './types/inpe'
import type { ClimateProduct, ClimateVariable } from './types/climate'
import type {
  NativeGridProduct,
  SelectedSusceptibilityCell,
  SusceptibilityModelId,
  SusceptibilityProduct,
} from './types/susceptibility'

function formatReferenceDate(value: string | undefined) {
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : null
}

export default function App() {
  const [section, setSection] = useState<'susceptibility' | 'climate'>('susceptibility')
  const [climate, setClimate] = useState<ClimateProduct | null>(null)
  const [climateError, setClimateError] = useState<string | null>(null)
  const [climateVariable, setClimateVariable] = useState<ClimateVariable>('humidity')
  const [climateDate, setClimateDate] = useState('2015-08-25')
  const [showScars, setShowScars] = useState(true)
  const [selectedClimateCell, setSelectedClimateCell] = useState<string | null>(null)
  const [product, setProduct] = useState<SusceptibilityProduct | null>(null)
  const [selectedModel, setSelectedModel] = useState<SusceptibilityModelId>('gradboost')
  const [selectedCell, setSelectedCell] = useState<SelectedSusceptibilityCell | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [hotspots, setHotspots] = useState<InpeHotspotCollection | null>(null)
  const [showHotspots, setShowHotspots] = useState(true)
  const [hotspotsError, setHotspotsError] = useState<string | null>(null)
  const [nativeProduct, setNativeProduct] = useState<NativeGridProduct | null>(null)
  const [nativeIndexError, setNativeIndexError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    loadSusceptibilityProduct(controller.signal)
      .then((result) => {
        setProduct(result)
        setSelectedModel(result.manifest.default_model)
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

  useEffect(() => {
    const controller = new AbortController()
    loadInpeHotspots(controller.signal)
      .then(setHotspots)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setHotspotsError(
            error instanceof Error ? error.message : 'Erro ao carregar os focos do INPE.',
          )
        }
      })
    return () => controller.abort()
  }, [])

  const selectedCellId = selectedCell?.feature.properties.id ?? null
  const activeModel = product?.manifest.models.find((model) => model.id === selectedModel)
  const hotspotReferenceDate = formatReferenceDate(
    hotspots?.metadata.data_referencia ?? hotspots?.features[0]?.properties.data_hora_gmt ?? undefined,
  )
  const dailyScars = climate?.scars.features.filter((feature) => feature.properties.date === climateDate).length ?? 0

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <span className="eyebrow">Produto científico experimental</span>
          <h1>Monitoramento de Incêndios Florestais — Acre</h1>
          <p>Risco experimental referente a 2016, clima diário de 2015 e observações de fogo.</p>
        </div>
        <span className="prototype-badge">{section === 'climate' ? 'Clima histórico · cicatrizes mapeadas · 2015' : 'Risco experimental · referência 2016 · focos INPE reais'}</span>
      </header>

      <nav className="product-tabs" aria-label="Seção do mapa">
        <button type="button" className={section === 'susceptibility' ? 'active' : undefined} onClick={() => setSection('susceptibility')}>Risco</button>
        <button type="button" className={section === 'climate' ? 'active' : undefined} onClick={() => setSection('climate')}>Clima e cicatrizes · 2015</button>
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
              <small>{dailyScars} pixels classificados em {formatReferenceDate(climateDate)}</small>
            </section>
          </div>
          {climate ? (
            <>
              <TimeSlider dates={climate.manifest.dates} selectedDate={climateDate} onChange={setClimateDate} />
              <section className="map-workspace climate-workspace">
                <ClimateMap product={climate} variable={climateVariable} date={climateDate} showScars={showScars} selectedCellId={selectedClimateCell} onCellSelect={setSelectedClimateCell} />
                <ClimateDetails product={climate} variable={climateVariable} date={climateDate} cellId={selectedClimateCell} onClear={() => setSelectedClimateCell(null)} />
              </section>
              <section className="scientific-product-note">
                <div><span className="eyebrow">Como ler</span><strong>Clima histórico e cicatrizes mapeadas de 2015</strong></div>
                <p>As cores mostram a média espacial diária. O painel informa mínimo, média e máximo entre pixels climáticos de aproximadamente 0,1° que intersectam cada célula visual de 0,28°. Marcadores vermelhos localizam pixels classificados como cicatriz; ao aproximar, seu contorno aparece. Um dia sem registro não comprova ausência de fogo.</p>
              </section>
            </>
          ) : (
            <section className="map-section">
              <div className="map-shell map-status" role="status">
                <strong>{climateError ? 'Não foi possível carregar o clima histórico.' : 'Carregando clima e cicatrizes de 2015…'}</strong>
                {climateError && <span>{climateError}</span>}
              </div>
            </section>
          )}
        </>
      ) : (
      <>
      <div className="map-controls">
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
        <HotspotLayerControl
          checked={showHotspots}
          count={hotspots?.features.length ?? null}
          referenceDate={hotspotReferenceDate}
          loading={!hotspots && !hotspotsError}
          error={hotspotsError}
          onChange={setShowHotspots}
        />
      </div>

      {product && activeModel ? (
        <>
          <section className="map-workspace">
            <div className="map-section">
              <FireMap
                model={selectedModel}
                modelLabel={activeModel.label}
                cells={product.cells}
                boundary={product.boundary}
                bounds={product.bounds}
                selectedCellId={selectedCellId}
                onCellSelect={setSelectedCell}
                hotspots={hotspots}
                showHotspots={showHotspots}
                nativeProduct={nativeProduct}
                nativeIndexError={nativeIndexError}
              />
            </div>
            <CellDetails
              cell={selectedCell}
              model={selectedModel}
              manifest={product.manifest}
              onClear={() => setSelectedCell(null)}
            />
          </section>
          <section className="scientific-product-note">
            <div>
              <span className="eyebrow">Leitura correta</span>
              <strong>Risco experimental referente às cicatrizes de 2016</strong>
            </div>
            <p>
              Ano de referência {product.manifest.source_period}. Os escores são relativos e não
              representam probabilidades calibradas nem previsão operacional independente. Cada
              célula visível reúne, por média aritmética, células científicas de aproximadamente
              893 × 598 m. O modelo ativo é{' '}
              <strong>{activeModel.label}</strong>.
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
                <span>Validando manifesto, limite do Acre e escores dos quatro modelos.</span>
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
