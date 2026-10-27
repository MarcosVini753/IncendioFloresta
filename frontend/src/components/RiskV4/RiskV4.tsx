import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  Map as MapLibreMap,
  NavigationControl,
  addProtocol,
  removeProtocol,
  type GeoJSONSource,
  type RasterTileSource,
} from 'maplibre-gl'
import type { FeatureCollection } from 'geojson'
import { loadRiskV4 } from '../../data/riskV4'
import { RISK_DISPLAY_CLASSES } from '../../data/riskDisplayPalette'
import { comparisonColorExpression, formatRankingDifference, rankingDifference } from '../../data/riskComparison'
import { RiskRasterClient } from '../../data/riskRaster'
import { loadScarProduct } from '../../data/climate'
import {
  type RiskV4Model,
  type RiskV4Product,
  type RiskV4Selection,
  type RiskV4Values,
} from '../../types/riskV4'
import type { ScarCollection } from '../../types/climate'
import { MapLegend } from '../Legend/MapLegend'
import { RiskYearComparison } from './RiskYearComparison'

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
  highlightClass,
  onHighlightClassChange,
  focusPoint,
  comparisonMode,
}: {
  product: RiskV4Product
  model: RiskV4Model
  selected: RiskV4Selection | null
  onSelect: (selection: RiskV4Selection | null) => void
  scars: ScarCollection | null
  showScars: boolean
  highlightClass: string | null
  onHighlightClassChange: (id: string | null) => void
  focusPoint: [number, number] | null
  comparisonMode: boolean
}) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const updateRef = useRef<(() => void) | null>(null)
  const selectedRef = useRef(selected),
    modelRef = useRef(model),
    scarsRef = useRef(scars),
    showScarsRef = useRef(showScars),
    highlightRef = useRef(highlightClass),
    comparisonRef = useRef(comparisonMode)
  selectedRef.current = selected
  modelRef.current = model
  scarsRef.current = scars
  showScarsRef.current = showScars
  highlightRef.current = highlightClass
  comparisonRef.current = comparisonMode
  const [mapReady, setMapReady] = useState(false)
  const [copyState, setCopyState] = useState('')
  const [zoom, setZoom] = useState(5)
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const clientRef = useRef<RiskRasterClient | null>(null)

  useEffect(() => {
    const client =
      product.rasterBase === null
        ? null
        : new RiskRasterClient(product.index, product.rasterBase)
    clientRef.current = client
    const protocol = `risk-v4-${++mapSerial}`
    if (client)
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
      style: 'https://tiles.openfreemap.org/styles/positron',
      center: [-70.3, -9.3],
      zoom: 5.2,
    })
    mapRef.current = map
    map.addControl(new NavigationControl(), 'top-right')
    let query: AbortController | null = null
    const tiles = (id: RiskV4Model) => [`${protocol}://${id}/{z}/{x}/{y}`]
    const update = () => {
      if (!map.getSource('risk-v4-grid')) return
      const native = client !== null && map.getZoom() >= 8.5 && !comparisonRef.current
      for (const layer of ['risk-v4-fill', 'risk-v4-lines'])
        map.setLayoutProperty(layer, 'visibility', native ? 'none' : 'visible')
      if (client)
        for (const id of ['random_forest', 'xgboost'] as const)
          map.setLayoutProperty(
            `risk-v4-${id}`,
            'visibility',
            native && id === modelRef.current ? 'visible' : 'none',
          )
      map.setPaintProperty(
        'risk-v4-fill',
        'fill-color',
        comparisonRef.current ? comparisonColorExpression as never : [
          'step',
          ['get', `percentile_${modelRef.current}`],
          RISK_DISPLAY_CLASSES[0].color,
          50, RISK_DISPLAY_CLASSES[1].color,
          70, RISK_DISPLAY_CLASSES[2].color,
          90, RISK_DISPLAY_CLASSES[3].color,
          95, RISK_DISPLAY_CLASSES[4].color,
        ],
      )
      const spotlight = comparisonRef.current
        ? undefined
        : RISK_DISPLAY_CLASSES.find((item) => item.id === highlightRef.current)
      map.setPaintProperty('risk-v4-fill', 'fill-opacity', spotlight ? [
        'case',
        ['all',
          ['>=', ['get', `percentile_${modelRef.current}`], spotlight.lower],
          [spotlight.upper === 100 ? '<=' : '<',
            ['get', `percentile_${modelRef.current}`], spotlight.upper],
        ],
        0.91, 0.16,
      ] as never : comparisonRef.current ? 0.94 : 0.85)
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
      // Os rótulos do mapa-base devem permanecer legíveis sobre o risco.
      const labelLayerId = map.getStyle().layers.find((layer) => layer.type === 'symbol')?.id
      map.addLayer({
        id: 'risk-v4-fill',
        type: 'fill',
        source: 'risk-v4-grid',
        paint: { 'fill-color': '#f1de84', 'fill-opacity': 0.85 },
      }, labelLayerId)
      map.addLayer({
        id: 'risk-v4-lines',
        type: 'line',
        source: 'risk-v4-grid',
        minzoom: 7.5,
        paint: { 'line-color': 'rgba(255,255,255,.28)', 'line-width': 0.4 },
      }, labelLayerId)
      if (client)
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
              'raster-opacity': 0.9,
              'raster-resampling': 'nearest',
              'raster-fade-duration': 0,
            },
          }, labelLayerId)
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
      const urlParams = new URLSearchParams(window.location.search)
      const savedLon = urlParams.get('lon')
      const savedLat = urlParams.get('lat')
      const savedZoom = urlParams.get('zoom')
      const lon = Number(savedLon)
      const lat = Number(savedLat)
      const zoomValue = Number(savedZoom)
      if (urlParams.get('view') === 'risk' &&
          urlParams.get('year') === String(product.manifest.year) &&
          savedLon !== null && savedLat !== null && savedZoom !== null &&
          Number.isFinite(lon) && Number.isFinite(lat) && Number.isFinite(zoomValue) &&
          lon >= w && lon <= e && lat >= s && lat <= n && zoomValue >= 4 && zoomValue <= 14) {
        map.jumpTo({ center: [lon, lat], zoom: zoomValue })
      } else {
        map.fitBounds([[w, s], [e, n]], { padding: 44, duration: 0 })
      }
      update()
      setZoom(map.getZoom())
      setMapReady(true)
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
      const show = (selection: RiskV4Selection) => onSelect(selection)
      if (!client || map.getZoom() < 8.5 || comparisonRef.current) {
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
      map.remove()
      if (client) removeProtocol(protocol)
      client?.destroy()
      updateRef.current = null
      mapRef.current = null
      clientRef.current = null
    }
  }, [product, onSelect])

  useEffect(() => {
    updateRef.current?.()
  }, [model, selected, scars, showScars, highlightClass, comparisonMode])
  useEffect(() => {
    const map = mapRef.current
    if (!map || !focusPoint || !mapReady) return
    map.flyTo({ center: focusPoint, zoom: product.rasterBase === null ? 8.2 : 10, essential: true })
  }, [focusPoint, mapReady, product.rasterBase])
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
  async function shareMap() {
    const map = mapRef.current
    if (!map) return
    const { lng, lat } = map.getCenter()
    const link = new URL(window.location.href)
    link.searchParams.set('year', String(product.manifest.year))
    link.searchParams.set('model', model)
    link.searchParams.set('lon', lng.toFixed(5))
    link.searchParams.set('lat', lat.toFixed(5))
    link.searchParams.set('zoom', map.getZoom().toFixed(2))
    link.searchParams.set('view', 'risk')
    link.searchParams.set('mode', comparisonMode ? 'compare' : 'risk')
    try {
      await navigator.clipboard.writeText(link.toString())
      setCopyState('Link copiado')
    } catch {
      setCopyState('O navegador não permitiu copiar o link.')
    }
  }
  return (
    <div className="map-shell">
      <div ref={container} className="map-container" />
      <MapLegend
        modelLabel={
          product.manifest.models.find((item) => item.id === model)!.label
        }
        aggregated={product.rasterBase === null || zoom < 8.5 || comparisonMode}
        rasterReduced={product.rasterBase !== null && zoom >= 8.5 && zoom < 12}
        showScars={showScars && scars !== null}
        highlightClass={highlightClass}
        onHighlightClassChange={onHighlightClassChange}
        comparisonMode={comparisonMode}
      />
      <div className="risk-map-share">
        <button type="button" onClick={() => void shareMap()} disabled={!mapReady}>Compartilhar mapa</button>
        {copyState && <span role="status">{copyState}</span>}
      </div>
      {!mapReady && <div className="risk-map-loading" role="status">Preparando o mapa…</div>}
      <div className="map-prototype-note" role="status" aria-live="polite">
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
        ) : comparisonMode ? (
          'Comparação de modelos · grupos de 5 km'
        ) : product.rasterBase === null ? (
          'Visualização agregada · grupos de 5 km'
        ) : (
          status ||
          (zoom < 8.5
            ? 'Visualização agregada · grupos de 5 km'
            : zoom < 12
              ? 'Raster reduzido · consulta a 30 m'
              : 'Resolução original · aproximadamente 30 m')
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
  onClose,
  comparisonMode,
}: {
  selection: RiskV4Selection | null
  product: RiskV4Product
  model: RiskV4Model
  onClear: () => void
  onClose: () => void
  comparisonMode: boolean
}) {
  if (!selection)
    return (
      <aside className="cell-details cell-details-empty">
        <div>
          <span className="eyebrow">Local selecionado</span>
          <h2>Explore o Risco de {product.manifest.year}</h2>
          <p>
            {product.rasterBase === null
              ? 'Clique em um grupo de 5 km para comparar as médias dos dois modelos. Os pixels originais de 30 m não estão disponíveis nesta publicação.'
              : 'Clique em um grupo de 5 km ou aproxime para consultar um pixel científico de 30 m e comparar os dois modelos.'}
          </p>
        </div>
      </aside>
    )
  const p = selection.properties,
    aggregate = selection.kind === 'aggregated'
  const active = product.manifest.models.find((item) => item.id === model)!
  const currentPercentile = percentile(p, model)
  const rankDelta = rankingDifference(p)
  // Mesmos limites científicos do mapa: classificação apenas visual.
  const currentClass = RISK_DISPLAY_CLASSES.find(
    (item) => currentPercentile >= item.lower && (
      currentPercentile < item.upper || item.upper === 100
    ),
  ) ?? RISK_DISPLAY_CLASSES[RISK_DISPLAY_CLASSES.length - 1]
  return (
    <aside id="risk-cell-details" className="cell-details">
      <div className="cell-details-header">
        <div>
          <span className="eyebrow">Área selecionada</span>
          <h2>{aggregate ? 'Grupo de 5 km' : 'Pixel de 30 m'}</h2>
          <span className="risk-cell-id">{p.id}</span>
        </div>
        <div className="cell-details-actions">
          <button type="button" className="clear-selection" onClick={onClear} aria-label="Limpar seleção" title="Limpar seleção">Limpar</button>
          <button type="button" className="clear-selection risk-panel-close" onClick={onClose} aria-label="Fechar painel de detalhes" title="Fechar painel">×</button>
        </div>
      </div>
      {comparisonMode && (
        <div className="risk-model-delta">
          <span className="eyebrow">Diferença entre os modelos</span>
          <strong>{formatRankingDifference(rankDelta)}</strong>
          <p>
            O valor mostra a distância entre as posições atribuídas pelos dois
            modelos para esta área. Não mede a mudança do risco nem a chance de incêndio.
          </p>
          <div className="risk-delta-pair" role="group" aria-label="Posição dos dois modelos">
            <div><span>Random Forest</span><strong>{decimal(p.percentile_random_forest)}</strong></div>
            <div><span>XGBoost</span><strong>{decimal(p.percentile_xgboost)}</strong></div>
          </div>
        </div>
      )}
      {!comparisonMode && <div className="active-score">
        <span className="risk-score-caption">{active.label} · mapa de {product.manifest.year}</span>
        <span className="risk-score-topline">
          <strong>{decimal(currentPercentile)}</strong>
          <span className="risk-score-unit">posição<br/>no ranking</span>
        </span>
        <span className="risk-score-class">Classificação nesta área: <b>{currentClass.label}</b></span>
        <small>Esse número indica a posição relativa da área no mapa, de 0 a 100. Não é a chance de ocorrer um incêndio.</small>
        <details className="risk-score-technical">
          <summary>Valor calculado pelo modelo</summary>
          <p>{active.value_label}: {pct(modelValue(p, model))}. {aggregate ? 'Média dos pixels do grupo.' : 'Valor do pixel consultado.'} Valores de modelos diferentes não devem ser comparados como probabilidades equivalentes.</p>
        </details>
      </div>}
      {!comparisonMode && <dl className="model-score-list">
        {product.manifest.models.map((item) => (
          <div
            key={item.id}
            className={item.id === model ? 'active' : undefined}
          >
            <dt>{item.label}</dt>
            <dd>
              <strong>{decimal(percentile(p, item.id))}</strong>
              <small>
                {aggregate ? 'Posição média no ranking' : 'Posição no ranking'}
              </small>
              <small>
                {item.calibrated
                  ? 'Valor ajustado pelo estudo'
                  : 'Valor sem calibração equivalente'}
              </small>
            </dd>
          </div>
        ))}
      </dl>}
      {!comparisonMode && (
        <RiskYearComparison
          year={product.manifest.year}
          selection={selection}
          model={model}
        />
      )}
      <details className="risk-panel-extra">
        <summary>Informações técnicas desta área</summary>
      {selection.kind === 'aggregated' && (
        <section className="risk-class-shares">
          <h3>Como se distribuem os pixels nesta área</h3>
          {RISK_DISPLAY_CLASSES.map((category) => {
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
          <dd>{product.manifest.training.years.join('–')}</dd>
        </div>
        <div>
          <dt>Clima do modelo</dt>
          <dd>{product.manifest.training.climate_year} · suavizado</dd>
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
      </details>
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
    <details className="risk-evaluation" id="risk-evaluation">
      <summary className="risk-evaluation-summary">
        <span>
          <span className="eyebrow">Resultados da pesquisa</span>
          <strong>Como o modelo se saiu nos anos anteriores?</strong>
        </span>
        <span className="risk-disclosure-hint">Ver análise</span>
      </summary>
      <div className="risk-evaluation-content">
        <p>
          Estes números mostram o desempenho do {active.label} em mapas de
          2023 a 2025, comparando suas estimativas com áreas identificadas
          depois como queimadas no MapBiomas Fogo. Isso ajuda a avaliar o
          método, mas não garante acertos no futuro.
          {!product.manifest.evaluation.target_year_available &&
            ` Ainda não há avaliação observada do mapa de ${product.manifest.year} nesta entrega.`}
        </p>
        <div className="evaluation-table-wrapper">
          <table className="evaluation-priority-table">
            <caption>Resultados históricos para todo o Acre</caption>
            <thead>
              <tr>
                <th>Ano</th>
                <th title="Período usado para treinar o modelo">Anos usados no treino</th>
                <th title="Pixels identificados como queimados">Pixels queimados</th>
                <th title="Capacidade de ordenar áreas queimadas acima de não queimadas">AUC-ROC</th>
                <th title="Resumo da precisão ao priorizar áreas queimadas">Precisão média (AP)</th>
                <th title="Percentual dos pixels queimados situado nos 5% do território com maior prioridade">Encontrados no topo de 5%</th>
              </tr>
            </thead>
            <tbody>
              {product.manifest.evaluation.historical[model].map((row) => (
                <tr key={row.year}>
                  <th scope="row">{row.year}</th>
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
        <details className="risk-metrics-explanation">
          <summary>O que significa cada medida?</summary>
          <p><strong>Pixels queimados:</strong> pequenas partes do território identificadas como queimadas no histórico. Não correspondem à quantidade de incêndios.</p>
          <p><strong>AUC-ROC:</strong> mede a capacidade de posicionar áreas queimadas acima de áreas não queimadas em uma classificação. Valores mais próximos de 1 são melhores.</p>
          <p><strong>Precisão média (AP):</strong> resume o desempenho na identificação das áreas queimadas quando elas são priorizadas. Também depende da frequência das áreas queimadas.</p>
          <p><strong>Encontrados no topo de 5%:</strong> indica quantos dos pixels queimados estavam entre os 5% do território que o modelo colocou mais alto na classificação.</p>
        </details>
        <p className="risk-evaluation-limit">
          Resultados recebidos da equipe de pesquisa, sem recálculo neste site.
          Áreas queimadas mapeadas não são incêndios individuais confirmados.
        </p>
      </div>
    </details>
  )
}

export function RiskV4({
  year,
  onYearChange,
}: {
  year: 2025 | 2026
  onYearChange: (year: 2025 | 2026) => void
}) {
  const cache = useRef(new Map<number, RiskV4Product>())
  const [product, setProduct] = useState<RiskV4Product | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [model, setModel] = useState<RiskV4Model>(() => {
    const saved = new URLSearchParams(window.location.search).get('model')
    return saved === 'xgboost' ? 'xgboost' : 'random_forest'
  })
  const [comparisonMode, setComparisonMode] = useState(
    () => new URLSearchParams(window.location.search).get('mode') === 'compare',
  )
  const [selection, setSelection] = useState<RiskV4Selection | null>(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  // Callback estável: não reinicializa o mapa a cada seleção.
  const handleMapSelection = useCallback((next: RiskV4Selection | null) => {
    setSelection(next)
    if (next) setDetailsOpen(true)
  }, [])
  const [highlightClass, setHighlightClass] = useState<string | null>(null)
  const [coordinateText, setCoordinateText] = useState('')
  const [coordinateError, setCoordinateError] = useState('')
  const [focusPoint, setFocusPoint] = useState<[number, number] | null>(null)
  const [showScars, setShowScars] = useState(false)
  const [scars, setScars] = useState<ScarCollection | null>(null)
  const [scarError, setScarError] = useState<string | null>(null)
  const [scarAttempt, setScarAttempt] = useState(0)
  useEffect(() => {
    if (!detailsOpen) return
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDetailsOpen(false)
    }
    window.addEventListener('keydown', onEscape)
    return () => window.removeEventListener('keydown', onEscape)
  }, [detailsOpen])
  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    setSelection(null)
    setDetailsOpen(false)
    setProduct(cache.current.get(year) ?? null)
    if (cache.current.has(year)) return () => controller.abort()
    void loadRiskV4(year, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        cache.current.set(year, result)
        setProduct(result)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : 'Falha ao carregar o Risco v4.',
          )
      })
    return () => controller.abort()
  }, [attempt, year])
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
  function goToCoordinates(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const pieces = coordinateText.trim().split(/[,;]/).map((value) => value.trim())
    if (pieces.length !== 2 || pieces.some(
      (value) => value === '' || !Number.isFinite(Number(value)),
    )) {
      setCoordinateError('Digite latitude e longitude. Exemplo: -9.97, -67.81')
      return
    }
    const [latitude, longitude] = pieces.map(Number)
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
        Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
      setCoordinateError('Coordenadas inválidas.')
      return
    }
    const [west, south, east, north] = product?.manifest.bounds ?? [-75, -13, -66, -6]
    if (latitude < south || latitude > north || longitude < west || longitude > east) {
      setCoordinateError('O ponto informado está fora da área coberta pelo mapa do Acre.')
      return
    }
    setCoordinateError('')
    setFocusPoint([longitude, latitude])
  }
  const yearControl = (
    <section className="control-group risk-year-control">
      <label className="control-label" htmlFor="risk-year">
        Ano do risco
      </label>
      <select
        className="model-selector"
        id="risk-year"
        value={year}
        onChange={(event) =>
          onYearChange(Number(event.target.value) as 2025 | 2026)
        }
      >
        <option value={2026}>2026</option>
        <option value={2025}>2025</option>
      </select>
    </section>
  )
  if (!product || product.manifest.year !== year)
    return (
      <section className="map-section">
        {yearControl}
        <div className="map-shell map-status" role="status">
          <strong>
            {error
              ? 'Não foi possível carregar o mapa de risco.'
              : `Preparando o mapa de risco para ${year}…`}
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
      <div className="risk-v4-toolbar" aria-label="Configuração do mapa de risco">
        {yearControl}
        <section className="control-group risk-model-control">
          <span className="control-label">Modelo de risco</span>
          <div className="layer-selector" role="group" aria-label="Modelo de risco">
            {product.manifest.models.map((item) => (
              <button
                type="button"
                key={item.id}
                className={model === item.id ? 'active' : undefined}
                aria-pressed={model === item.id}
                disabled={comparisonMode}
                onClick={() => setModel(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </section>
        <section className="control-group risk-compare-control">
          <span className="control-label">Visualização</span>
          <div className="risk-view-toggle" role="group" aria-label="Como mostrar os modelos">
            <button
              type="button"
              aria-pressed={!comparisonMode}
              className={!comparisonMode ? 'active' : undefined}
              onClick={() => setComparisonMode(false)}
            >Mapa de risco</button>
            <button
              type="button"
              aria-pressed={comparisonMode}
              className={comparisonMode ? 'active' : undefined}
              onClick={() => {
                setHighlightClass(null)
                setComparisonMode(true)
              }}
            >Comparar modelos</button>
          </div>
        </section>
        <section className="control-group risk-scar-control">
          <span className="control-label">Camadas observadas</span>
          <label>
            <input
              type="checkbox"
              checked={showScars}
              onChange={(event) => setShowScars(event.target.checked)}
            />
            <i className="scar-swatch risk-scar-swatch" aria-hidden="true" />
            Áreas queimadas · 2025
          </label>
          {scarError && (
            <div className="overlay-error" role="alert">
              {scarError}{' '}
              <button type="button" onClick={() => setScarAttempt((v) => v + 1)}>
                Tentar novamente
              </button>
            </div>
          )}
        </section>
        <details className="risk-coordinate-panel">
          <summary>Buscar por coordenadas</summary>
          <form className="risk-coordinate-form" onSubmit={goToCoordinates}>
            <label htmlFor="risk-coordinate-search">Latitude, longitude</label>
            <input
              id="risk-coordinate-search"
              type="text"
              value={coordinateText}
              onChange={(event) => setCoordinateText(event.target.value)}
              placeholder="-9.97, -67.81"
              aria-describedby={coordinateError ? 'risk-coordinate-error' : undefined}
            />
            <button type="submit">Localizar</button>
            {coordinateError && <small id="risk-coordinate-error" role="alert">{coordinateError}</small>}
          </form>
        </details>
        <details className="risk-toolbar-context">
          <summary>Sobre os dados</summary>
          <p>O mapa usa o histórico de áreas queimadas do MapBiomas Fogo e dados ambientais para estimar o risco anual. São resultados de pesquisa, não registros de incêndios em andamento.</p>
        </details>
      </div>
      {showScars && year !== 2025 && (
        <p className="risk-year-note" role="status">
          <strong>Atenção às datas:</strong> o mapa mostra o risco estimado para 2026;
          os pontos roxos mostram áreas queimadas mapeadas em 2025.
          Essas observações não comprovam se a estimativa para 2026 acertou.
          {!scars && !scarError ? ' Carregando as observações…' : ''}
        </p>
      )}
      <section
        className={`map-workspace risk-v4-workspace${selection && detailsOpen ? ' has-details' : ''}`}
        aria-label="Mapa de risco e consulta do local"
      >
        <div className="map-section risk-map-section">
          <RiskMap
            key={year}
            product={product}
            model={model}
            selected={selection}
            onSelect={handleMapSelection}
            scars={scars}
            showScars={showScars}
            highlightClass={highlightClass}
            onHighlightClassChange={setHighlightClass}
            focusPoint={focusPoint}
            comparisonMode={comparisonMode}
          />
          {selection && !detailsOpen && (
            <button
              type="button"
              className="risk-details-reopen"
              aria-label="Abrir painel de detalhes do local selecionado"
              onClick={() => setDetailsOpen(true)}
            >
              Ver detalhes do local selecionado
            </button>
          )}
        </div>
        {selection && detailsOpen && (
          <CellPanel
            product={product}
            model={model}
            selection={selection}
            comparisonMode={comparisonMode}
            onClear={() => {
              setSelection(null)
              setDetailsOpen(false)
            }}
            onClose={() => setDetailsOpen(false)}
          />
        )}
      </section>
      {comparisonMode && (
        <div className="risk-comparison-explainer">
          <strong>Como interpretar a comparação</strong>
          <p>Azul: XGBoost colocou a área mais acima em seu ranking. Terracota:
          Random Forest colocou a área mais acima. Tons claros: classificações próximas.
          A comparação usa apenas os grupos de 5 km do mesmo ano e não indica qual modelo acertou.</p>
        </div>
      )}
      <Evaluation product={product} model={model} />
      <section className="risk-science-summary" aria-label="Sobre este mapa">
        <div className="risk-science-intro">
          <span className="eyebrow">Sobre este mapa</span>
          <strong>O que as cores mostram?</strong>
          <p>
            {comparisonMode
              ? 'Nesta visualização, as cores mostram diferenças entre o ranking do Random Forest e o do XGBoost para o mesmo ano. Elas não representam probabilidades nem evolução do risco.'
              : 'As cores comparam as áreas do Acre entre si. Os tons quentes mostram áreas mais altas na classificação do modelo; os verdes, mais baixas. Isso não quer dizer que um incêndio vai acontecer nesses lugares.'}
          </p>
        </div>
        <details className="risk-methodology">
          <summary>Como esse mapa foi produzido?</summary>
          <p>
            Pesquisadores analisaram dados ambientais e o histórico de áreas
            queimadas para estimar o risco anual. O modelo {active.label} usou
            informações de {product.manifest.training.years.join(' a ')} e dados
            climáticos de {product.manifest.training.climate_year}.
          </p>
          <p>
            O estudo reúne {decimal(product.manifest.counts.source_pixels, 0)}
            pequenos pixels, de aproximadamente 30 metros. Nesta visão afastada,
            {decimal(product.manifest.counts.features, 0)} grupos de 5 km resumem
            os dados para facilitar a leitura.
            {product.rasterBase === null
              ? ' A consulta dos pixels individuais ainda não está disponível nesta publicação.'
              : ' Ao aproximar, é possível consultar um pixel específico.'}
          </p>
          <details className="risk-technical-method">
            <summary>Informações técnicas para aprofundar</summary>
            <p>
              Os arquivos GeoTIFF finais foram publicados sem recalcular as
              estimativas nem os percentis. O Random Forest recebeu calibração
              temporal da equipe científica; o XGBoost recebeu correção de
              amostragem e não tem calibração equivalente. O cenário é AB30C,
              com suavização climática. Este produto é experimental e não
              oferece alertas operacionais de incêndio.
            </p>
          </details>
        </details>
      </section>
    </>
  )
}
