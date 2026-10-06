import { useEffect, useMemo, useRef, useState } from 'react'
import type { Feature, MultiPolygon, Polygon } from 'geojson'
import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type GeoJSONSource,
  type MapLayerMouseEvent,
} from 'maplibre-gl'
import { scoreForModel } from '../../data/susceptibility'
import {
  loadNativeSector,
  nativeFeatureIntersectsViewport,
  NativeSectorCache,
  selectNativeSectors,
} from '../../data/nativeSusceptibility'
import type {
  RiskScenario,
  AggregatedCellCollection,
  AggregatedCellProperties,
  NativeCellCollection,
  NativeCellProperties,
  NativeGridProduct,
  SelectedSusceptibilityCell,
  SusceptibilityModelId,
} from '../../types/susceptibility'
import { MapLegend } from '../Legend/MapLegend'
import { formatRelativeScorePercent } from '../../utils/formatRelativeScore'

interface FireMapProps {
  scenario: RiskScenario
  model: SusceptibilityModelId
  modelLabel: string
  cells: AggregatedCellCollection
  boundary: Feature<Polygon | MultiPolygon>
  bounds: [[number, number], [number, number]]
  selectedCellId: string | null
  onCellSelect: (cell: SelectedSusceptibilityCell | null) => void
  nativeProduct: NativeGridProduct | null
  nativeIndexError: string | null
}

const CELLS_SOURCE_ID = 'susceptibility-cells'
const CELLS_FILL_LAYER_ID = 'susceptibility-cells-fill'
const CELLS_LINE_LAYER_ID = 'susceptibility-cells-line'
const SELECTED_CELL_LAYER_ID = 'susceptibility-selected-cell'
const NATIVE_SOURCE_ID = 'native-susceptibility-cells'
const NATIVE_FILL_LAYER_ID = 'native-susceptibility-fill'
const NATIVE_LINE_LAYER_ID = 'native-susceptibility-line'
const NATIVE_SELECTED_LAYER_ID = 'native-susceptibility-selected'
const ACRE_SOURCE_ID = 'acre-boundary'
const ACRE_OUTLINE_LAYER_ID = 'acre-outline'
const NATIVE_ZOOM = 8.5

const EMPTY_NATIVE: NativeCellCollection = { type: 'FeatureCollection', features: [] }

const HTML_ENTITIES: Record<string, string> = {
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => HTML_ENTITIES[character])
}

function buildCellPopup(
  properties: AggregatedCellProperties,
  model: SusceptibilityModelId,
  modelLabel: string,
  scenario: RiskScenario,
) {
  return `<div class="susceptibility-popup">
    <strong>${escapeHtml(properties.id)}</strong>
    <span>${escapeHtml(modelLabel)}: ${escapeHtml(formatRelativeScorePercent(scoreForModel(properties, model, scenario)))} (escore relativo)</span>
    <span>${properties.n_source_cells.toLocaleString('pt-BR')} células científicas · média</span>
  </div>`
}

function buildNativePopup(
  properties: NativeCellProperties,
  model: SusceptibilityModelId,
  modelLabel: string,
  scenario: RiskScenario,
) {
  return `<div class="susceptibility-popup">
    <strong>${escapeHtml(properties.id)}</strong>
    <span>Grade X ${properties.grid_x} · Y ${properties.grid_y}</span>
    <span>${escapeHtml(modelLabel)}: ${escapeHtml(formatRelativeScorePercent(scoreForModel(properties, model, scenario)))} (escore relativo)</span>
    <span>Célula científica original · sem agregação</span>
  </div>`
}

function nativeWithValue(collection: NativeCellCollection, model: SusceptibilityModelId, scenario: RiskScenario) {
  return {
    ...collection,
    features: collection.features.map((feature) => ({
      ...feature,
      properties: { ...feature.properties, value: scoreForModel(feature.properties, model, scenario) },
    })),
  } as NativeCellCollection
}

export function FireMap({
  scenario,
  model,
  modelLabel,
  cells,
  boundary,
  bounds,
  selectedCellId,
  onCellSelect,
  nativeProduct,
  nativeIndexError,
}: FireMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const scenarioRef = useRef(scenario)
  const modelRef = useRef(model)
  const modelLabelRef = useRef(modelLabel)
  const cellsRef = useRef(cells)
  const onCellSelectRef = useRef(onCellSelect)
  const nativeProductRef = useRef(nativeProduct)
  const nativeVisibleRef = useRef<NativeCellCollection>(EMPTY_NATIVE)
  const nativeCacheRef = useRef(new NativeSectorCache(32))
  const nativeAbortRef = useRef<AbortController | null>(null)
  const refreshNativeRef = useRef<(() => void) | null>(null)
  const popupRef = useRef<Popup | null>(null)
  const [nativeMode, setNativeMode] = useState(false)
  const [nativeLoading, setNativeLoading] = useState(false)
  const [nativeError, setNativeError] = useState<string | null>(null)
  const [nativeCellCount, setNativeCellCount] = useState(0)

  scenarioRef.current = scenario
  modelRef.current = model
  modelLabelRef.current = modelLabel
  cellsRef.current = cells
  onCellSelectRef.current = onCellSelect
  nativeProductRef.current = nativeProduct

  const geojson = useMemo<AggregatedCellCollection>(
    () => ({
      ...cells,
      features: cells.features.map((feature) => ({
        ...feature,
        properties: {
          ...feature.properties,
          value: scoreForModel(feature.properties, model, scenario),
        },
      })) as AggregatedCellCollection['features'],
    }),
    [cells, model, scenario],
  )

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new MapLibreMap({
      container: containerRef.current,
      style: 'https://demotiles.maplibre.org/style.json',
      center: [-70.3, -9.3],
      zoom: 5.2,
      attributionControl: {},
    })
    map.addControl(new NavigationControl(), 'top-right')

    map.on('load', () => {
      map.addSource(ACRE_SOURCE_ID, { type: 'geojson', data: boundary })
      map.addSource(CELLS_SOURCE_ID, { type: 'geojson', data: {
        ...cellsRef.current,
        features: cellsRef.current.features.map((feature) => ({
          ...feature,
          properties: { ...feature.properties, value: scoreForModel(feature.properties, modelRef.current, scenarioRef.current) },
        })),
      } })
      map.addSource(NATIVE_SOURCE_ID, { type: 'geojson', data: EMPTY_NATIVE })
      map.addLayer({
        id: CELLS_FILL_LAYER_ID,
        type: 'fill',
        source: CELLS_SOURCE_ID,
        paint: {
          'fill-color': [
            'interpolate', ['linear'], ['coalesce', ['get', 'value'], -1],
            -1, '#9ca3af', 0, '#1a9850', 0.5, '#fee08b', 1, '#d73027',
          ],
          'fill-opacity': 0.74,
        },
      })
      map.addLayer({
        id: CELLS_LINE_LAYER_ID,
        type: 'line',
        source: CELLS_SOURCE_ID,
        paint: {
          'line-color': 'rgba(255, 255, 255, 0.82)',
          'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.45, 8, 1],
        },
      })
      map.addLayer({
        id: SELECTED_CELL_LAYER_ID,
        type: 'line',
        source: CELLS_SOURCE_ID,
        filter: ['==', ['get', 'id'], '__none__'],
        paint: { 'line-color': '#102a43', 'line-width': 3.4, 'line-opacity': 1 },
      })
      map.addLayer({
        id: NATIVE_FILL_LAYER_ID,
        type: 'fill',
        source: NATIVE_SOURCE_ID,
        layout: { visibility: 'none' },
        paint: {
          'fill-color': [
            'interpolate', ['linear'], ['coalesce', ['get', 'value'], -1],
            -1, '#9ca3af', 0, '#1a9850', 0.5, '#fee08b', 1, '#d73027',
          ],
          'fill-opacity': 0.76,
        },
      })
      map.addLayer({
        id: NATIVE_LINE_LAYER_ID,
        type: 'line',
        source: NATIVE_SOURCE_ID,
        layout: { visibility: 'none' },
        paint: {
          'line-color': 'rgba(255, 255, 255, 0.72)',
          'line-width': ['interpolate', ['linear'], ['zoom'], NATIVE_ZOOM, 0.2, 12, 0.8],
        },
      })
      map.addLayer({
        id: NATIVE_SELECTED_LAYER_ID,
        type: 'line',
        source: NATIVE_SOURCE_ID,
        filter: ['==', ['get', 'id'], '__none__'],
        layout: { visibility: 'none' },
        paint: { 'line-color': '#102a43', 'line-width': 3, 'line-opacity': 1 },
      })
      map.addLayer({
        id: ACRE_OUTLINE_LAYER_ID,
        type: 'line',
        source: ACRE_SOURCE_ID,
        paint: { 'line-color': '#173f32', 'line-width': 2.4, 'line-opacity': 0.95 },
      })
      map.fitBounds(bounds, { padding: 44, duration: 0 })

      for (const layerId of [CELLS_FILL_LAYER_ID, NATIVE_FILL_LAYER_ID]) {
        map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = '' })
      }

      map.on('click', CELLS_FILL_LAYER_ID, (event: MapLayerMouseEvent) => {
        const id = event.features?.[0]?.properties?.id as string | undefined
        const cell = cellsRef.current.features.find((feature) => feature.properties.id === id)
        if (!cell) return
        onCellSelectRef.current({ kind: 'aggregated', feature: cell })
        popupRef.current?.remove()
        popupRef.current = new Popup({ closeButton: true })
          .setLngLat(event.lngLat)
          .setHTML(buildCellPopup(cell.properties, modelRef.current, modelLabelRef.current, scenarioRef.current))
          .addTo(map)
      })

      map.on('click', NATIVE_FILL_LAYER_ID, (event: MapLayerMouseEvent) => {
        const id = event.features?.[0]?.properties?.id as string | undefined
        const cell = nativeVisibleRef.current.features.find((feature) => feature.properties.id === id)
        if (!cell) return
        onCellSelectRef.current({ kind: 'native', feature: cell })
        popupRef.current?.remove()
        popupRef.current = new Popup({ closeButton: true })
          .setLngLat(event.lngLat)
          .setHTML(buildNativePopup(cell.properties, modelRef.current, modelLabelRef.current, scenarioRef.current))
          .addTo(map)
      })

      const setNativeVisibility = (visible: boolean) => {
        const aggregatedVisibility = visible ? 'none' : 'visible'
        const nativeVisibility = visible ? 'visible' : 'none'
        for (const layerId of [CELLS_FILL_LAYER_ID, CELLS_LINE_LAYER_ID, SELECTED_CELL_LAYER_ID]) {
          map.setLayoutProperty(layerId, 'visibility', aggregatedVisibility)
        }
        for (const layerId of [NATIVE_FILL_LAYER_ID, NATIVE_LINE_LAYER_ID, NATIVE_SELECTED_LAYER_ID]) {
          map.setLayoutProperty(layerId, 'visibility', nativeVisibility)
        }
      }

      const refreshNative = () => {
        nativeAbortRef.current?.abort()
        if (map.getZoom() < NATIVE_ZOOM) {
          setNativeVisibility(false)
          nativeVisibleRef.current = EMPTY_NATIVE
          const nativeSource = map.getSource(NATIVE_SOURCE_ID) as GeoJSONSource
          nativeSource.setData(EMPTY_NATIVE)
          setNativeMode(false)
          setNativeLoading(false)
          setNativeError(null)
          setNativeCellCount(0)
          return
        }

        const product = nativeProductRef.current
        if (!product) {
          setNativeVisibility(false)
          setNativeMode(false)
          setNativeLoading(false)
          setNativeError('A grade científica original ainda não está disponível.')
          return
        }

        setNativeVisibility(true)
        setNativeMode(true)
        setNativeLoading(true)
        setNativeError(null)
        const controller = new AbortController()
        nativeAbortRef.current = controller
        const view = map.getBounds()
        const viewport: [number, number, number, number] = [
          view.getWest(), view.getSouth(), view.getEast(), view.getNorth(),
        ]
        const visibleEntries = selectNativeSectors(product.index, viewport)
        const visibleIds = new Set(visibleEntries.map((entry) => entry.id))
        const requestedEntries = selectNativeSectors(
          product.index,
          viewport,
          product.index.sector_step_degrees,
        )

        void Promise.allSettled(
          requestedEntries.map(async (entry) => {
            const cached = nativeCacheRef.current.get(entry.id)
            if (cached) return { entry, collection: cached }
            const collection = await loadNativeSector(entry, controller.signal)
            nativeCacheRef.current.set(entry.id, collection)
            return { entry, collection }
          }),
        ).then((results) => {
          if (controller.signal.aborted) return
          const features = results.flatMap((result) => {
            if (result.status !== 'fulfilled' || !visibleIds.has(result.value.entry.id)) return []
            return result.value.collection.features.filter((feature) => nativeFeatureIntersectsViewport(feature, viewport))
          })
          const failedVisible = results.some(
            (result, index) =>
              result.status === 'rejected' && visibleIds.has(requestedEntries[index].id),
          )
          const collection: NativeCellCollection = { type: 'FeatureCollection', features }
          nativeVisibleRef.current = collection
          const nativeSource = map.getSource(NATIVE_SOURCE_ID) as GeoJSONSource
          nativeSource.setData(nativeWithValue(collection, modelRef.current, scenarioRef.current))
          setNativeCellCount(features.length)
          setNativeLoading(false)
          setNativeError(
            failedVisible ? 'Alguns setores visíveis não puderam ser carregados.' : null,
          )
        })
      }

      refreshNativeRef.current = refreshNative
      map.on('movestart', () => nativeAbortRef.current?.abort())
      map.on('moveend', refreshNative)
      refreshNative()
    })

    mapRef.current = map
    return () => {
      nativeAbortRef.current?.abort()
      refreshNativeRef.current = null
      popupRef.current?.remove()
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const source = mapRef.current?.getSource(CELLS_SOURCE_ID) as GeoJSONSource | undefined
    source?.setData(geojson)
  }, [geojson])

  useEffect(() => {
    popupRef.current?.remove()
    const source = mapRef.current?.getSource(NATIVE_SOURCE_ID) as GeoJSONSource | undefined
    if (source) source.setData(nativeWithValue(nativeVisibleRef.current, model, scenario))
  }, [model, scenario])

  useEffect(() => {
    refreshNativeRef.current?.()
  }, [nativeProduct])

  useEffect(() => {
    const map = mapRef.current
    if (map?.getLayer(SELECTED_CELL_LAYER_ID)) {
      map.setFilter(SELECTED_CELL_LAYER_ID, ['==', ['get', 'id'], selectedCellId ?? '__none__'])
    }
    if (map?.getLayer(NATIVE_SELECTED_LAYER_ID)) {
      map.setFilter(NATIVE_SELECTED_LAYER_ID, ['==', ['get', 'id'], selectedCellId ?? '__none__'])
    }
  }, [selectedCellId])

  return (
    <div className="map-shell">
      <div ref={containerRef} className="map-container" />
      <MapLegend modelLabel={modelLabel} />
      <div className="map-prototype-note">
        {nativeMode
          ? nativeLoading
            ? 'Carregando setores da grade científica original…'
            : nativeError || `${nativeCellCount.toLocaleString('pt-BR')} células científicas visíveis · sem agregação`
          : nativeIndexError
            ? `Grade científica indisponível: ${nativeIndexError}`
            : 'Visualização agregada em 0,28° · aproxime até o zoom 8,5 para visualizar a grade científica original'}
      </div>
    </div>
  )
}
