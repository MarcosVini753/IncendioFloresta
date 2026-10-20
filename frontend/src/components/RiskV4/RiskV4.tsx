import { useEffect, useRef, useState } from 'react'
import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  addProtocol,
  removeProtocol,
  type GeoJSONSource,
  type RasterTileSource,
} from 'maplibre-gl'
import type { FeatureCollection } from 'geojson'
import { loadRiskV4 } from '../../data/riskV4'
import { RiskRasterClient } from '../../data/riskRaster'
import { loadScarProduct } from '../../data/climate'
import {
  RISK_V4_CLASSES,
  type RiskV4Model,
  type RiskV4Product,
  type RiskV4Selection,
  type RiskV4Values,
} from '../../types/riskV4'
import type { ScarCollection } from '../../types/climate'
import { MapLegend } from '../Legend/MapLegend'

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }
const decimal = (value: number, digits = 1) =>
  value.toLocaleString('pt-BR', { maximumFractionDigits: digits })
const pct = (value: number) =>
  value > 0 && value < 0.000001 ? '<0,000001%' : `${decimal(value, 6)}%`
const percentile = (values: RiskV4Values, model: RiskV4Model) =>
  values[`percentile_${model}`]
const modelValue = (values: RiskV4Values, model: RiskV4Model) =>
  values[`value_${model}`]
let mapSerial = 0

function RiskMap({
  product,
  model,
  selected,
  onSelect,
  scars,
  showScars,
}: {
  product: RiskV4Product
  model: RiskV4Model
  selected: RiskV4Selection | null
  onSelect: (selection: RiskV4Selection | null) => void
  scars: ScarCollection | null
  showScars: boolean
}) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const updateRef = useRef<(() => void) | null>(null)
  const selectedRef = useRef(selected),
    modelRef = useRef(model),
    scarsRef = useRef(scars),
    showScarsRef = useRef(showScars)
  selectedRef.current = selected
  modelRef.current = model
  scarsRef.current = scars
  showScarsRef.current = showScars
  const [zoom, setZoom] = useState(5)
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const clientRef = useRef<RiskRasterClient | null>(null)
  const popupRef = useRef<Popup | null>(null)

  useEffect(() => {
    const client = new RiskRasterClient(product.index)
    clientRef.current = client
    const protocol = `risk-v4-${++mapSerial}`
    addProtocol(protocol, async (request, controller) => {
      const match = request.url.match(
        /:\/\/(random_forest|xgboost)\/(\d+)\/(\d+)\/(\d+)/,
      )
      if (!match) throw new Error('Endereço raster inválido.')
      return {
        data: await client.tile(
          match[1] as RiskV4Model,
          Number(match[2]),
          Number(match[3]),
          Number(match[4]),
          controller.signal,
        ),
      }
    })
    const map = new MapLibreMap({
      container: container.current!,
      style: 'https://demotiles.maplibre.org/style.json',
      center: [-70.3, -9.3],
      zoom: 5.2,
    })
    mapRef.current = map
    map.addControl(new NavigationControl(), 'top-right')
    const popup = new Popup({ closeButton: true })
    popupRef.current = popup
    let query: AbortController | null = null
    const tiles = (id: RiskV4Model) => [`${protocol}://${id}/{z}/{x}/{y}`]
    const update = () => {
      if (!map.getSource('risk-v4-grid')) return
      const native = map.getZoom() >= 8.5
      for (const layer of ['risk-v4-fill', 'risk-v4-lines'])
        map.setLayoutProperty(layer, 'visibility', native ? 'none' : 'visible')
      for (const id of ['random_forest', 'xgboost'] as const)
        map.setLayoutProperty(
          `risk-v4-${id}`,
          'visibility',
          native && id === modelRef.current ? 'visible' : 'none',
        )
      map.setPaintProperty('risk-v4-fill', 'fill-color', [
        'step',
        ['get', `percentile_${modelRef.current}`],
        RISK_V4_CLASSES[0].color,
        50,
        RISK_V4_CLASSES[1].color,
        70,
        RISK_V4_CLASSES[2].color,
        90,
        RISK_V4_CLASSES[3].color,
        95,
        RISK_V4_CLASSES[4].color,
      ])
      const choice = selectedRef.current
      const selection =
        choice?.kind === 'pixel'
          ? (() => {
              const [w, s, e, n] = choice.properties.bbox
              return {
                type: 'FeatureCollection' as const,
                features: [
                  {
                    type: 'Feature' as const,
                    properties: {},
                    geometry: {
                      type: 'Polygon' as const,
                      coordinates: [
                        [
                          [w, s],
                          [e, s],
                          [e, n],
                          [w, n],
                          [w, s],
                        ],
                      ],
                    },
                  },
                ],
              }
            })()
          : choice
            ? {
                type: 'FeatureCollection' as const,
                features: product.cells.features.filter(
                  (feature) => feature.properties.id === choice.properties.id,
                ),
              }
            : EMPTY
      ;(map.getSource('risk-v4-selected') as GeoJSONSource).setData(selection)
      const observed = scarsRef.current ?? EMPTY
      ;(map.getSource('risk-v4-scars') as GeoJSONSource).setData(observed)
      ;(map.getSource('risk-v4-scar-points') as GeoJSONSource).setData({
        type: 'FeatureCollection',
        features:
          scarsRef.current?.features.map((feature) => ({
            type: 'Feature',
            properties: feature.properties,
            geometry: { type: 'Point', coordinates: feature.properties.center },
          })) ?? [],
      })
      for (const layer of [
        'risk-v4-scar-fill',
        'risk-v4-scar-line',
        'risk-v4-scar-markers',
      ])
        map.setLayoutProperty(
          layer,
          'visibility',
          showScarsRef.current ? 'visible' : 'none',
        )
    }
    updateRef.current = update
    map.on('style.load', () => {
      map.addSource('risk-v4-grid', { type: 'geojson', data: product.cells })
      map.addSource('risk-v4-boundary', {
        type: 'geojson',
        data: product.boundary,
      })
      map.addSource('risk-v4-selected', { type: 'geojson', data: EMPTY })
      map.addSource('risk-v4-scars', { type: 'geojson', data: EMPTY })
      map.addSource('risk-v4-scar-points', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'risk-v4-fill',
        type: 'fill',
        source: 'risk-v4-grid',
        paint: { 'fill-color': '#fee08b', 'fill-opacity': 0.76 },
      })
      map.addLayer({
        id: 'risk-v4-lines',
        type: 'line',
        source: 'risk-v4-grid',
        paint: { 'line-color': 'rgba(255,255,255,.82)', 'line-width': 0.55 },
      })
      for (const id of ['random_forest', 'xgboost'] as const) {
        map.addSource(`risk-v4-${id}`, {
          type: 'raster',
          tiles: tiles(id),
          tileSize: 256,
          minzoom: 8,
          maxzoom: 14,
          bounds: product.manifest.bounds,
        })
        map.addLayer({
          id: `risk-v4-${id}`,
          type: 'raster',
          source: `risk-v4-${id}`,
          minzoom: 8.5,
          layout: { visibility: 'none' },
          paint: {
            'raster-opacity': 0.82,
            'raster-resampling': 'nearest',
            'raster-fade-duration': 0,
          },
        })
      }
      map.addLayer({
        id: 'risk-v4-outline',
        type: 'line',
        source: 'risk-v4-boundary',
        paint: { 'line-color': '#173f32', 'line-width': 2.2 },
      })
      map.addLayer({
        id: 'risk-v4-selected-line',
        type: 'line',
        source: 'risk-v4-selected',
        paint: { 'line-color': '#102a43', 'line-width': 3 },
      })
      map.addLayer({
        id: 'risk-v4-scar-fill',
        type: 'fill',
        source: 'risk-v4-scars',
        minzoom: 8.5,
        paint: { 'fill-color': '#8e2b92', 'fill-opacity': 0.72 },
      })
      map.addLayer({
        id: 'risk-v4-scar-line',
        type: 'line',
        source: 'risk-v4-scars',
        minzoom: 8.5,
        paint: { 'line-color': '#48194e', 'line-width': 1.2 },
      })
      map.addLayer({
        id: 'risk-v4-scar-markers',
        type: 'circle',
        source: 'risk-v4-scar-points',
        maxzoom: 8.5,
        paint: {
          'circle-color': '#8e2b92',
          'circle-radius': 4.5,
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1.2,
        },
      })
      const [w, s, e, n] = product.manifest.bounds
      map.fitBounds(
        [
          [w, s],
          [e, n],
        ],
        { padding: 44, duration: 0 },
      )
      update()
      setZoom(map.getZoom())
    })
    map.on('zoom', () => {
      setZoom(map.getZoom())
      update()
    })
    map.on('movestart', () => {
      query?.abort()
      setStatus('')
      setError(null)
    })
    map.on('click', (event) => {
      query?.abort()
      setError(null)
      popup.remove()
      const show = (selection: RiskV4Selection) => {
        onSelect(selection)
        const label =
          selection.kind === 'pixel'
            ? 'Pixel científico · 2026'
            : 'Grupo de 5 km · 2026'
        const active = product.manifest.models.find(
          (item) => item.id === modelRef.current,
        )!
        popup
          .setLngLat(event.lngLat)
          .setHTML(
            `<div class="susceptibility-popup"><strong>${label}</strong><span>${active.label} · índice ${decimal(percentile(selection.properties, modelRef.current))}</span><span>${active.value_label}: ${pct(modelValue(selection.properties, modelRef.current))}</span><span>${selection.kind === 'pixel' ? 'Consulta na resolução original' : 'Média dos pixels válidos'}</span></div>`,
          )
          .addTo(map)
      }
      if (map.getZoom() < 8.5) {
        const id = map.queryRenderedFeatures(event.point, {
          layers: ['risk-v4-fill'],
        })[0]?.properties?.id
        const feature = product.cells.features.find(
          (item) => item.properties.id === id,
        )
        if (feature)
          show({ kind: 'aggregated', properties: feature.properties })
        return
      }
      const controller = new AbortController()
      query = controller
      setStatus('Consultando o pixel original de 30 m…')
      void client
        .query(event.lngLat.lng, event.lngLat.lat, controller.signal)
        .then((pixel) => {
          if (controller.signal.aborted) return
          setStatus(pixel ? '' : 'Sem dados válidos neste local.')
          if (pixel) show({ kind: 'pixel', properties: pixel })
          else onSelect(null)
        })
        .catch((reason: unknown) => {
          if (!controller.signal.aborted) {
            setStatus('')
            setError(
              reason instanceof Error
                ? reason.message
                : 'Falha ao consultar o pixel.',
            )
          }
        })
    })
    map.on('error', (event) => {
      const sourceId = (event as unknown as { sourceId?: string }).sourceId
      if (
        sourceId?.startsWith('risk-v4-') ||
        event.error.message.includes('setor')
      )
        setError(event.error.message)
    })
    map.on('mouseenter', 'risk-v4-fill', () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', 'risk-v4-fill', () => {
      map.getCanvas().style.cursor = ''
    })
    const observer = new ResizeObserver(() => {
      if (container.current?.clientWidth) map.resize()
    })
    observer.observe(container.current!)
    return () => {
      observer.disconnect()
      query?.abort()
      popup.remove()
      map.remove()
      removeProtocol(protocol)
      client.destroy()
      updateRef.current = null
      mapRef.current = null
      clientRef.current = null
      popupRef.current = null
    }
  }, [product, onSelect])

  useEffect(() => {
    updateRef.current?.()
  }, [model, selected, scars, showScars])
  useEffect(() => {
    popupRef.current?.remove()
  }, [model])
  useEffect(() => {
    if (!selected) popupRef.current?.remove()
  }, [selected])
  useEffect(() => {
    if (!retry) return
    setError(null)
    for (const id of ['random_forest', 'xgboost'] as const) {
      const source = mapRef.current?.getSource(`risk-v4-${id}`) as
        | RasterTileSource
        | undefined
      if (source) source.setTiles(source.tiles!)
    }
  }, [retry])
  return (
    <div className="map-shell">
      <div ref={container} className="map-container" />
      <MapLegend
        modelLabel={
          product.manifest.models.find((item) => item.id === model)!.label
        }
        aggregated={zoom < 8.5}
        rasterReduced={zoom >= 8.5 && zoom < 12}
        showScars={showScars && scars !== null}
      />
      <div className="map-prototype-note" role="status">
        {error ? (
          <>
            <span>Falha no raster: {error}</span>{' '}
            <button
              type="button"
              className="clear-selection"
              onClick={() => setRetry((v) => v + 1)}
            >
              Tentar novamente
            </button>
          </>
        ) : (
          status ||
          (zoom < 8.5
            ? 'Grupos de 5 km: média dos percentis · aproxime para explorar os pixels de 30 m'
            : zoom < 12
              ? 'Raster reduzido por médias · clique consulta o pixel original de 30 m'
              : 'Pixels originais de aproximadamente 30 m · clique para consultar')
        )}
      </div>
    </div>
  )
}

function CellPanel({
  selection,
  product,
  model,
  onClear,
}: {
  selection: RiskV4Selection | null
  product: RiskV4Product
  model: RiskV4Model
  onClear: () => void
}) {
  if (!selection)
    return (
      <aside className="cell-details cell-details-empty">
        <div>
          <span className="eyebrow">Local selecionado</span>
          <h2>Explore o Risco de 2026</h2>
          <p>
            Clique em um grupo de 5 km ou aproxime para consultar um pixel
            científico de 30 m e comparar os dois modelos.
          </p>
        </div>
      </aside>
    )
  const p = selection.properties,
    aggregate = selection.kind === 'aggregated'
  const active = product.manifest.models.find((item) => item.id === model)!
  return (
    <aside className="cell-details">
      <div className="cell-details-header">
        <div>
          <span className="eyebrow">
            {aggregate ? 'Grupo visual de 5 km' : 'Pixel científico original'}
          </span>
          <h2>{p.id}</h2>
        </div>
        <button type="button" className="clear-selection" onClick={onClear}>
          Limpar
        </button>
      </div>
      <div className="active-score">
        <span>{active.label}</span>
        <strong>{decimal(percentile(p, model))}</strong>
        <small>
          {aggregate ? 'Média dos percentis' : 'Índice percentil'} · 2026
        </small>
        <span>
          {active.value_label}: {pct(modelValue(p, model))}
        </span>
        <small>
          O percentil é posição no ranking; não é porcentagem de chance de
          incêndio.
        </small>
      </div>
      <dl className="model-score-list">
        {product.manifest.models.map((item) => (
          <div
            key={item.id}
            className={item.id === model ? 'active' : undefined}
          >
            <dt>{item.label}</dt>
            <dd>
              <strong>{decimal(percentile(p, item.id))}</strong>
              <small>
                {aggregate ? 'Percentil médio' : 'Percentil'} ·{' '}
                {pct(modelValue(p, item.id))}
              </small>
              <small>
                {item.calibrated
                  ? 'Estimativa calibrada experimental'
                  : 'Escore não calibrado'}
              </small>
            </dd>
          </div>
        ))}
      </dl>
      {selection.kind === 'aggregated' && (
        <section className="risk-class-shares">
          <h3>Proporção dos pixels por classe</h3>
          {RISK_V4_CLASSES.map((category) => {
            const share = Number(
              selection.properties[`share_${model}_${category.id}`],
            )
            return (
              <div className="risk-class-share" key={category.id}>
                <span
                  className="risk-class-swatch"
                  style={{ backgroundColor: category.color }}
                />
                <span className="risk-class-name">
                  {category.label}
                  <small>
                    índice {category.lower}–
                    {category.upper === 100 ? '100' : `<${category.upper}`}
                  </small>
                </span>
                <strong>{decimal(share * 100)}%</strong>
                <small>
                  {decimal(
                    Math.round(share * selection.properties.n_source_pixels),
                    0,
                  )}{' '}
                  pixels
                </small>
              </div>
            )
          })}
          <p>
            A contagem de pixels aproxima a proporção da área; são pixels
            válidos, não incêndios.
          </p>
        </section>
      )}
      <dl className="cell-metrics">
        <div>
          <dt>Treino</dt>
          <dd>2016–2025</dd>
        </div>
        <div>
          <dt>Clima do modelo</dt>
          <dd>2025 · suavizado</dd>
        </div>
        <div>
          <dt>Histórico e rótulo</dt>
          <dd>MapBiomas Fogo · AB30C</dd>
        </div>
        {selection.kind === 'pixel' ? (
          <>
            <div>
              <dt>Linha original</dt>
              <dd>{selection.properties.row}</dd>
            </div>
            <div>
              <dt>Coluna original</dt>
              <dd>{selection.properties.column}</dd>
            </div>
          </>
        ) : (
          <div>
            <dt>Pixels científicos</dt>
            <dd>{decimal(selection.properties.n_source_pixels, 0)}</dd>
          </div>
        )}
        <div>
          <dt>Latitude</dt>
          <dd>{p.centroid[1].toFixed(6)}</dd>
        </div>
        <div>
          <dt>Longitude</dt>
          <dd>{p.centroid[0].toFixed(6)}</dd>
        </div>
        <div>
          <dt>Resolução original</dt>
          <dd>aproximadamente 30 m</dd>
        </div>
      </dl>
      <p className="cell-details-note">
        {aggregate
          ? 'A cor classifica a média dos percentis recebidos. Escores e proporções também vêm dos pixels originais.'
          : 'Consulta feita na resolução original, mesmo quando o raster desenhado usa uma versão reduzida.'}{' '}
        Os percentis estaduais do professor são preservados.
      </p>
    </aside>
  )
}

function Evaluation({
  product,
  model,
}: {
  product: RiskV4Product
  model: RiskV4Model
}) {
  const active = product.manifest.models.find((item) => item.id === model)!
  return (
    <section className="risk-evaluation">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Avaliações fornecidas pelo professor</span>
          <h2>Desempenho histórico · {active.label}</h2>
        </div>
      </div>
      <p>
        Não há avaliação observada de 2026 nesta entrega. A tabela apresenta
        mapas de 2023–2025, na variante AB30C com clima suavizado, comparados às
        cicatrizes de 30 m do MapBiomas Fogo.
      </p>
      <div className="evaluation-table-wrapper">
        <table className="evaluation-priority-table">
          <caption>
            Relatórios recebidos · território completo · nível 30m_fogo
          </caption>
          <thead>
            <tr>
              <th>Ano</th>
              <th>Treino</th>
              <th>Pixels positivos</th>
              <th>AUC-ROC</th>
              <th>AP</th>
              <th>Captura no topo de 5%</th>
            </tr>
          </thead>
          <tbody>
            {product.manifest.evaluation.historical[model].map((row) => (
              <tr key={row.year}>
                <th>{row.year}</th>
                <td>{row.training}</td>
                <td>{decimal(row.metrics.positivos, 0)}</td>
                <td>{decimal(row.metrics.roc_auc, 3)}</td>
                <td>{decimal(row.metrics.pr_auc, 4)}</td>
                <td>{pct(row.metrics['captura_5%'] * 100)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="risk-evaluation-limit">
        Métricas recebidas, não recalculadas nesta integração. A captura mede a
        fração dos pixels positivos nas áreas priorizadas; pixels queimados não
        equivalem a incêndios confirmados. Os relatórios usam histogramas para
        resumir as previsões e o ranking.
      </p>
    </section>
  )
}

export function RiskV4() {
  const [product, setProduct] = useState<RiskV4Product | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [model, setModel] = useState<RiskV4Model>('random_forest')
  const [selection, setSelection] = useState<RiskV4Selection | null>(null)
  const [showScars, setShowScars] = useState(false)
  const [scars, setScars] = useState<ScarCollection | null>(null)
  const [scarError, setScarError] = useState<string | null>(null)
  const [scarAttempt, setScarAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    void loadRiskV4(controller.signal)
      .then(setProduct)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : 'Falha ao carregar o Risco v4.',
          )
      })
    return () => controller.abort()
  }, [attempt])
  useEffect(() => {
    if (!showScars || scars) return
    const controller = new AbortController()
    setScarError(null)
    void loadScarProduct(controller.signal)
      .then((result) => setScars(result.scars))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setScarError(
            reason instanceof Error
              ? reason.message
              : 'Falha ao carregar as cicatrizes de 2025.',
          )
      })
    return () => controller.abort()
  }, [showScars, scars, scarAttempt])
  if (!product)
    return (
      <section className="map-section">
        <div className="map-shell map-status" role="status">
          <strong>
            {error
              ? 'Não foi possível carregar o Risco v4.'
              : 'Carregando Risco v4 de 2026…'}
          </strong>
          {error && (
            <>
              <span>{error}</span>
              <button type="button" onClick={() => setAttempt((v) => v + 1)}>
                Tentar novamente
              </button>
            </>
          )}
        </div>
      </section>
    )
  const active = product.manifest.models.find((item) => item.id === model)!
  return (
    <>
      <div className="map-controls risk-v4-controls">
        <section className="control-group">
          <span className="control-label">Modelo de risco · 2026</span>
          <div className="layer-selector">
            {product.manifest.models.map((item) => (
              <button
                type="button"
                key={item.id}
                className={model === item.id ? 'active' : undefined}
                aria-pressed={model === item.id}
                onClick={() => setModel(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <small>MapBiomas Fogo · cenário AB30C · clima suavizado</small>
        </section>
        <section className="control-group risk-scar-control">
          <span className="control-label">Observações históricas</span>
          <label>
            <input
              type="checkbox"
              checked={showScars}
              onChange={(event) => setShowScars(event.target.checked)}
            />
            <i className="scar-swatch risk-scar-swatch" />
            Cicatrizes observadas · 2025
          </label>
          <small>
            Inventário anterior à previsão de 2026; não há cicatrizes observadas
            de 2026 nesta entrega.
          </small>
          {scarError && (
            <div role="alert">
              {scarError}{' '}
              <button
                type="button"
                onClick={() => setScarAttempt((v) => v + 1)}
              >
                Tentar novamente
              </button>
            </div>
          )}
        </section>
      </div>
      {showScars && (
        <p className="temporal-warning" role="status">
          <strong>Risco anual: 2026 · Cicatrizes observadas: 2025.</strong>{' '}
          Períodos diferentes; a sobreposição não é uma validação da previsão de
          2026.{!scars && !scarError ? ' Carregando inventário…' : ''}
        </p>
      )}
      <section className="map-workspace risk-v4-workspace">
        <div className="map-section">
          <RiskMap
            product={product}
            model={model}
            selected={selection}
            onSelect={setSelection}
            scars={scars}
            showScars={showScars}
          />
        </div>
        <CellPanel
          product={product}
          model={model}
          selection={selection}
          onClear={() => setSelection(null)}
        />
      </section>
      <Evaluation product={product} model={model} />
      <section className="scientific-product-note">
        <div>
          <span className="eyebrow">Mapas finais do professor · v4</span>
          <strong>Risco anual experimental — 2026</strong>
        </div>
        <div>
          <p>
            {active.label} · treino de 2016–2025 · clima e histórico anteriores
            a 2026. O mapa mostra o índice percentil recebido, em classes fixas.{' '}
            {active.value_label} aparece separadamente no clique. Não é uma
            medição de fogo nem previsão operacional.
          </p>
          <details className="scientific-note-details">
            <summary>Dados e preparação do mapa</summary>
            <p>
              As previsões foram importadas dos GeoTIFFs finais sem novo treino,
              previsão, ranking ou calibração. Random Forest tem calibração
              temporal fornecida pelo professor; XGBoost tem correção de
              amostragem e não é calibrado. São{' '}
              {decimal(product.manifest.counts.source_pixels, 0)} pixels válidos
              de aproximadamente 30 m. No mapa afastado,{' '}
              {decimal(product.manifest.counts.features, 0)} grupos de 5 km
              mostram médias e proporções. Ao aproximar, setores raster são
              carregados progressivamente; o clique sempre consulta o pixel
              original. A aba Clima permanece em 2025.
            </p>
          </details>
        </div>
      </section>
    </>
  )
}
