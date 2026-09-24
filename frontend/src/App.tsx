import { useEffect, useMemo, useState } from 'react'
import './styles.css'
import { CellDetails } from './components/CellDetails/CellDetails'
import { TimeSeriesChart } from './components/Chart/TimeSeriesChart'
import { HotspotLayerControl } from './components/HotspotControl/HotspotLayerControl'
import { FireMap } from './components/Map/FireMap'
import { ModelSelector } from './components/ModelSelector/ModelSelector'
import { TimeSlider } from './components/Timeline/TimeSlider'
import { dangerCellsForDate, dangerSeries, loadDangerProduct } from './data/danger'
import { loadInpeHotspots } from './data/inpeHotspots'
import { loadNativeGridProduct } from './data/nativeSusceptibility'
import { loadSusceptibilityProduct } from './data/susceptibility'
import type { DangerProduct } from './types/danger'
import type { InpeHotspotCollection } from './types/inpe'
import type { NativeGridProduct, SelectedSusceptibilityCell, SusceptibilityModelId, SusceptibilityProduct } from './types/susceptibility'

type ProductMode = 'susceptibility' | 'danger'

function formatReferenceDate(value: string | undefined) {
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : null
}

export default function App() {
  const [mode, setMode] = useState<ProductMode>('susceptibility')
  const [susceptibility, setSusceptibility] = useState<SusceptibilityProduct | null>(null)
  const [danger, setDanger] = useState<DangerProduct | null>(null)
  const [susceptibilityModel, setSusceptibilityModel] = useState<SusceptibilityModelId>('gradboost')
  const [dangerModel, setDangerModel] = useState<SusceptibilityModelId>('gradboost')
  const [dangerDate, setDangerDate] = useState('2015-08-25')
  const [selectedCell, setSelectedCell] = useState<SelectedSusceptibilityCell | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [dangerError, setDangerError] = useState<string | null>(null)
  const [hotspots, setHotspots] = useState<InpeHotspotCollection | null>(null)
  const [showSusceptibilityHotspots, setShowSusceptibilityHotspots] = useState(true)
  const [showDangerHotspots, setShowDangerHotspots] = useState(false)
  const [hotspotsError, setHotspotsError] = useState<string | null>(null)
  const [nativeProduct, setNativeProduct] = useState<NativeGridProduct | null>(null)
  const [nativeIndexError, setNativeIndexError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    loadSusceptibilityProduct(controller.signal).then((result) => {
      setSusceptibility(result)
      setSusceptibilityModel(result.manifest.default_model)
    }).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        setLoadError(error instanceof Error ? error.message : 'Erro ao carregar a suscetibilidade.')
      }
    })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (mode !== 'danger' || danger || dangerError) return
    const controller = new AbortController()
    loadDangerProduct(controller.signal).then((result) => {
      setDanger(result)
      setDangerModel(result.manifest.default_model)
      setDangerDate(result.manifest.default_date)
    }).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        setDangerError(error instanceof Error ? error.message : 'Erro ao carregar o perigo histórico.')
      }
    })
    return () => controller.abort()
  }, [mode, danger, dangerError])

  useEffect(() => {
    const controller = new AbortController()
    loadNativeGridProduct(controller.signal).then(setNativeProduct).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        setNativeIndexError(error instanceof Error ? error.message : 'Erro ao carregar a grade científica original.')
      }
    })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadInpeHotspots(controller.signal).then(setHotspots).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        setHotspotsError(error instanceof Error ? error.message : 'Erro ao carregar os focos do INPE.')
      }
    })
    return () => controller.abort()
  }, [])

  const dangerCells = useMemo(() => danger ? dangerCellsForDate(danger, dangerDate) : null, [danger, dangerDate])
  const activeModel = mode === 'danger' ? dangerModel : susceptibilityModel
  const activeProduct = mode === 'danger' ? danger : susceptibility
  const activeCells = mode === 'danger' ? dangerCells : susceptibility?.cells ?? null
  const activeModels = activeProduct?.manifest.models ?? []
  const activeModelManifest = activeModels.find((candidate) => candidate.id === activeModel)
  const showHotspots = mode === 'danger' ? showDangerHotspots : showSusceptibilityHotspots
  const setShowHotspots = mode === 'danger' ? setShowDangerHotspots : setShowSusceptibilityHotspots
  const selectedCellId = selectedCell?.feature.properties.id ?? null
  const hotspotReferenceDate = formatReferenceDate(hotspots?.metadata.data_referencia ?? hotspots?.features[0]?.properties.data_hora_gmt ?? undefined)
  const series = useMemo(() => danger ? dangerSeries(
    danger,
    dangerModel,
    selectedCell?.kind === 'aggregated' ? selectedCell.feature.properties.id : undefined,
  ) : [], [danger, dangerModel, selectedCell])

  useEffect(() => { setSelectedCell(null) }, [mode])

  useEffect(() => {
    if (mode !== 'danger' || !dangerCells || selectedCell?.kind !== 'aggregated') return
    const updated = dangerCells.features.find((feature) => feature.properties.id === selectedCellId)
    if (updated) setSelectedCell({ kind: 'aggregated', feature: updated })
  }, [dangerCells, mode, selectedCellId])

  const ready = Boolean(susceptibility && activeProduct && activeCells && activeModelManifest)
  const currentError = mode === 'danger' ? dangerError : loadError

  return (
    <main className="app-shell">
      <header className="app-header">
        <div><span className="eyebrow">Produtos científicos experimentais</span>
          <h1>Monitoramento de Incêndios Florestais — Acre</h1>
          <p>Suscetibilidade experimental e reconstituição histórica diária com focos observados pelo INPE.</p></div>
        <span className="prototype-badge">
          {mode === 'danger'
            ? 'Perigo histórico diário — 2015 · focos INPE reais'
            : 'Suscetibilidade experimental · focos INPE reais'}
        </span>
      </header>

      <div className="map-controls product-controls">
        <section className="control-group" aria-labelledby="product-mode-label">
          <span id="product-mode-label" className="control-label">Produto</span>
          <div className="layer-selector">
            <button type="button" className={mode === 'susceptibility' ? 'active' : undefined} onClick={() => setMode('susceptibility')}>Suscetibilidade</button>
            <button type="button" className={mode === 'danger' ? 'active' : undefined} onClick={() => setMode('danger')}>Perigo histórico</button>
          </div>
        </section>
        {activeProduct ? <ModelSelector value={activeModel} models={activeModels}
          label={mode === 'danger' ? 'Modelo diário' : 'Modelo de suscetibilidade'}
          onChange={mode === 'danger' ? setDangerModel : setSusceptibilityModel} />
          : <section className="control-group"><span className="control-label">Modelo</span><span className="control-loading">Carregando produto…</span></section>}
        <HotspotLayerControl checked={showHotspots} count={hotspots?.features.length ?? null}
          referenceDate={hotspotReferenceDate} loading={!hotspots && !hotspotsError}
          error={hotspotsError} onChange={setShowHotspots} />
      </div>

      {mode === 'danger' && showDangerHotspots ? <aside className="temporal-warning" role="note">
        <strong>Perigo histórico: {formatReferenceDate(dangerDate)}</strong>
        <span>Focos INPE: {hotspotReferenceDate ?? 'data não informada'}</span>
        <span>Períodos diferentes; as camadas não representam validação temporal entre si.</span>
      </aside> : null}

      {ready && susceptibility && activeCells && activeModelManifest ? <>
        <section className="map-workspace">
          <div className="map-section"><FireMap model={activeModel} modelLabel={activeModelManifest.label}
            productLabel={mode === 'danger' ? 'Perigo histórico diário — 2015' : 'Suscetibilidade'} nativeEnabled={mode === 'susceptibility'}
            cells={activeCells} boundary={susceptibility.boundary} bounds={susceptibility.bounds}
            selectedCellId={selectedCellId} onCellSelect={setSelectedCell} hotspots={hotspots}
            showHotspots={showHotspots} nativeProduct={nativeProduct} nativeIndexError={nativeIndexError} /></div>
          <CellDetails cell={selectedCell} model={activeModel} manifest={activeProduct!.manifest}
            date={mode === 'danger' ? dangerDate : undefined}
            productLabel={mode === 'danger' ? 'Perigo histórico' : 'Suscetibilidade'} onClear={() => setSelectedCell(null)} />
        </section>

        {mode === 'danger' && danger ? <section className="temporal-grid">
          <TimeSlider dates={danger.manifest.dates} selectedDate={dangerDate} onChange={setDangerDate} />
          <TimeSeriesChart data={series} selectedDate={dangerDate}
            title={selectedCell?.kind === 'aggregated' ? `Série diária — ${selectedCell.feature.properties.id}` : 'Média estadual diária das 212 células'} />
        </section> : null}

        <section className="scientific-product-note">
          <div><span className="eyebrow">Leitura correta</span><strong>Escores relativos, não probabilidades calibradas</strong></div>
          {mode === 'danger' && danger ? <p>Reconstituição histórica de 01/01 a 31/12/2015. Treino 2006–2012,
            validação 2013 e teste histórico 2014–2015. O contexto de fogo usa somente dias anteriores.
            Cada polígono é a média de células de aproximadamente 893 × 598 m.</p>
            : <p>Período-fonte {susceptibility.manifest.source_period}. Cada célula visível reúne,
              por média aritmética, células científicas de aproximadamente 893 × 598 m.</p>}
        </section>
      </> : <section className="map-section"><div className="map-shell map-status" role="status">
        {currentError ? <><strong>Não foi possível carregar o produto.</strong><span>{currentError}</span></>
          : <><strong>Carregando o produto científico…</strong><span>Validando manifesto, grade e escores dos quatro modelos.</span></>}
      </div></section>}
    </main>
  )
}
