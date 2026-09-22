import { useEffect, useState } from 'react'
import { CellDetails } from './components/CellDetails/CellDetails'
import { HotspotLayerControl } from './components/HotspotControl/HotspotLayerControl'
import { FireMap } from './components/Map/FireMap'
import { ModelSelector } from './components/ModelSelector/ModelSelector'
import { loadInpeHotspots } from './data/inpeHotspots'
import { loadNativeGridProduct } from './data/nativeSusceptibility'
import { loadSusceptibilityProduct } from './data/susceptibility'
import type { InpeHotspotCollection } from './types/inpe'
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
            error instanceof Error ? error.message : 'Erro ao carregar a suscetibilidade.',
          )
        }
      })
    return () => controller.abort()
  }, [])

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

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <span className="eyebrow">Produto científico experimental</span>
          <h1>Monitoramento de Incêndios Florestais — Acre</h1>
          <p>Suscetibilidade histórica agregada com focos de calor observados pelo INPE.</p>
        </div>
        <span className="prototype-badge">Suscetibilidade experimental · focos INPE reais</span>
      </header>

      <div className="map-controls">
        {product ? (
          <ModelSelector
            value={selectedModel}
            models={product.manifest.models}
            onChange={setSelectedModel}
          />
        ) : (
          <section className="control-group">
            <span className="control-label">Modelo de suscetibilidade</span>
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
              <strong>Escores relativos de suscetibilidade, não probabilidades calibradas</strong>
            </div>
            <p>
              Período-fonte {product.manifest.source_period}. Cada célula visível reúne, por média
              aritmética, células científicas de aproximadamente 893 × 598 m. O modelo ativo é{' '}
              <strong>{activeModel.label}</strong>.
            </p>
          </section>
        </>
      ) : (
        <section className="map-section">
          <div className="map-shell map-status" role="status">
            {loadError ? (
              <>
                <strong>Não foi possível carregar a suscetibilidade.</strong>
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
    </main>
  )
}
