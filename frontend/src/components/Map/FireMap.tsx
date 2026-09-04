import { useEffect, useMemo, useRef } from 'react'
import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type GeoJSONSource,
  type MapLayerMouseEvent,
} from 'maplibre-gl'
import type { Feature, FeatureCollection, MultiPolygon, Point, Polygon } from 'geojson'
import type { LayerType, PrototypeCell } from '../../types/fire'
import type { InpeHotspotCollection, InpeHotspotProperties } from '../../types/inpe'
import { MapLegend } from '../Legend/MapLegend'

interface FireMapProps {
  layer: LayerType
  selectedDate: string
  cells: PrototypeCell[]
  boundary: Feature<Polygon | MultiPolygon>
  bounds: [[number, number], [number, number]]
  selectedCellId: string | null
  onCellSelect: (cellId: string) => void
  hotspots: InpeHotspotCollection | null
  showHotspots: boolean
}

const CELLS_SOURCE_ID = 'prototype-cells'
const CELLS_FILL_LAYER_ID = 'prototype-cells-fill'
const CELLS_LINE_LAYER_ID = 'prototype-cells-line'
const SELECTED_CELL_LAYER_ID = 'prototype-selected-cell'
const ACRE_SOURCE_ID = 'acre-boundary'
const ACRE_OUTLINE_LAYER_ID = 'acre-outline'
const INPE_SOURCE_ID = 'inpe-hotspots'
const INPE_CLUSTER_LAYER_ID = 'inpe-clusters'
const INPE_CLUSTER_COUNT_LAYER_ID = 'inpe-cluster-count'
const INPE_UNCLUSTERED_LAYER_ID = 'inpe-unclustered-points'

const EMPTY_HOTSPOTS: FeatureCollection<Point, InpeHotspotProperties> = {
  type: 'FeatureCollection',
  features: [],
}

const HTML_ENTITIES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#039;',
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => HTML_ENTITIES[character])
}

function formatPopupText(value: string | null | undefined) {
  const text = value?.trim()
  return text ? escapeHtml(text) : 'Sem dado'
}

function formatPopupNumber(value: number | null | undefined) {
  return value == null
    ? 'Sem dado'
    : new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value)
}

function formatHotspotDateTime(value: string | null | undefined) {
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/)

  if (!match) return formatPopupText(value)

  const seconds = match[6] ? `:${match[6]}` : ''
  return `${match[3]}/${match[2]}/${match[1]} ${match[4]}:${match[5]}${seconds}`
}

function buildHotspotPopup(properties: Partial<InpeHotspotProperties>) {
  return `
    <div class="inpe-popup">
      <strong class="inpe-popup-title">Foco de calor — INPE</strong>
      <dl>
        <div><dt>Data/hora (GMT)</dt><dd>${formatHotspotDateTime(properties.data_hora_gmt)}</dd></div>
        <div><dt>Satélite</dt><dd>${formatPopupText(properties.satelite)}</dd></div>
        <div><dt>Município</dt><dd>${formatPopupText(properties.municipio)}</dd></div>
        <div><dt>Bioma</dt><dd>${formatPopupText(properties.bioma)}</dd></div>
        <div><dt>FRP</dt><dd>${formatPopupNumber(properties.frp)}</dd></div>
        <div><dt>Risco de fogo</dt><dd>${formatPopupNumber(properties.risco_fogo)}</dd></div>
        <div><dt>Precipitação</dt><dd>${formatPopupNumber(properties.precipitacao)}</dd></div>
      </dl>
      <p class="inpe-popup-source">Fonte: ${formatPopupText(properties.fonte)}</p>
      <p class="inpe-popup-note">Detecção orbital; não representa incêndio confirmado.</p>
    </div>
  `
}

export function FireMap({
  layer,
  selectedDate,
  cells,
  boundary,
  bounds,
  selectedCellId,
  onCellSelect,
  hotspots,
  showHotspots,
}: FireMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const layerRef = useRef<LayerType>(layer)
  const dateRef = useRef(selectedDate)
  const cellsRef = useRef(cells)
  const onCellSelectRef = useRef(onCellSelect)
  const hotspotsRef = useRef(hotspots)
  const showHotspotsRef = useRef(showHotspots)
  const hotspotPopupRef = useRef<Popup | null>(null)

  layerRef.current = layer
  dateRef.current = selectedDate
  cellsRef.current = cells
  onCellSelectRef.current = onCellSelect
  hotspotsRef.current = hotspots
  showHotspotsRef.current = showHotspots

  const geojson = useMemo<FeatureCollection<Polygon | MultiPolygon>>(
    () => ({
      type: 'FeatureCollection',
      features: cells.map((cell) => ({
        type: 'Feature',
        geometry: cell.geometry,
        properties: {
          id: cell.id,
          risk: cell.risk,
          danger: cell.danger[selectedDate],
          value: layer === 'risk' ? cell.risk : cell.danger[selectedDate],
        },
      })),
    }),
    [cells, layer, selectedDate],
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
      const hotspotVisibility =
        showHotspotsRef.current && Boolean(hotspotsRef.current?.features.length)
          ? 'visible'
          : 'none'

      map.addSource(ACRE_SOURCE_ID, {
        type: 'geojson',
        data: boundary,
      })

      map.addSource(CELLS_SOURCE_ID, {
        type: 'geojson',
        data: geojson,
      })

      map.addSource(INPE_SOURCE_ID, {
        type: 'geojson',
        data: hotspotsRef.current ?? EMPTY_HOTSPOTS,
        attribution: 'Programa Queimadas/INPE',
        cluster: true,
        clusterRadius: 35,
        clusterMaxZoom: 10,
      })

      map.addLayer({
        id: CELLS_FILL_LAYER_ID,
        type: 'fill',
        source: CELLS_SOURCE_ID,
        paint: {
          'fill-color': [
            'interpolate',
            ['linear'],
            ['coalesce', ['get', 'value'], -1],
            -1,
            '#9ca3af',
            0,
            '#1a9850',
            0.5,
            '#fee08b',
            1,
            '#d73027',
          ],
          'fill-opacity': 0.72,
        },
      })

      map.addLayer({
        id: CELLS_LINE_LAYER_ID,
        type: 'line',
        source: CELLS_SOURCE_ID,
        paint: {
          'line-color': 'rgba(255, 255, 255, 0.78)',
          'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.45, 8, 1],
        },
      })

      map.addLayer({
        id: SELECTED_CELL_LAYER_ID,
        type: 'line',
        source: CELLS_SOURCE_ID,
        filter: ['==', ['get', 'id'], '__none__'],
        paint: {
          'line-color': '#102a43',
          'line-width': 3.4,
          'line-opacity': 1,
        },
      })

      map.addLayer({
        id: INPE_CLUSTER_LAYER_ID,
        type: 'circle',
        source: INPE_SOURCE_ID,
        filter: ['has', 'point_count'],
        layout: {
          visibility: hotspotVisibility,
        },
        paint: {
          'circle-color': [
            'step',
            ['get', 'point_count'],
            '#f97316',
            10,
            '#ea580c',
            25,
            '#c2410c',
          ],
          'circle-radius': [
            'step',
            ['get', 'point_count'],
            16,
            10,
            20,
            25,
            24,
          ],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
          'circle-opacity': 0.9,
        },
      })

      map.addLayer({
        id: INPE_CLUSTER_COUNT_LAYER_ID,
        type: 'symbol',
        source: INPE_SOURCE_ID,
        filter: ['has', 'point_count'],
        layout: {
          visibility: hotspotVisibility,
          'text-field': ['get', 'point_count_abbreviated'],
          'text-size': 12,
          'text-allow-overlap': true,
        },
        paint: {
          'text-color': '#ffffff',
          'text-halo-color': 'rgba(99, 45, 11, 0.42)',
          'text-halo-width': 0.7,
        },
      })

      map.addLayer({
        id: INPE_UNCLUSTERED_LAYER_ID,
        type: 'circle',
        source: INPE_SOURCE_ID,
        filter: ['!', ['has', 'point_count']],
        layout: {
          visibility: hotspotVisibility,
        },
        paint: {
          'circle-color': '#ef3b2c',
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 4.5, 11, 7],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.6,
          'circle-opacity': 0.92,
        },
      })

      map.addLayer({
        id: ACRE_OUTLINE_LAYER_ID,
        type: 'line',
        source: ACRE_SOURCE_ID,
        paint: {
          'line-color': '#173f32',
          'line-width': 2.4,
          'line-opacity': 0.95,
        },
      })

      map.fitBounds(bounds, {
        padding: 44,
        duration: 0,
      })

      map.on('mouseenter', CELLS_FILL_LAYER_ID, () => {
        map.getCanvas().style.cursor = 'pointer'
      })

      map.on('mouseleave', CELLS_FILL_LAYER_ID, () => {
        map.getCanvas().style.cursor = ''
      })

      map.on('mouseenter', INPE_CLUSTER_LAYER_ID, () => {
        map.getCanvas().style.cursor = 'pointer'
      })

      map.on('mouseleave', INPE_CLUSTER_LAYER_ID, () => {
        map.getCanvas().style.cursor = ''
      })

      map.on('mouseenter', INPE_UNCLUSTERED_LAYER_ID, () => {
        map.getCanvas().style.cursor = 'pointer'
      })

      map.on('mouseleave', INPE_UNCLUSTERED_LAYER_ID, () => {
        map.getCanvas().style.cursor = ''
      })

      map.on('click', INPE_CLUSTER_LAYER_ID, (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0]
        const clusterId = Number(feature?.properties?.cluster_id)
        const coordinates = feature?.geometry.type === 'Point' ? feature.geometry.coordinates : null
        const source = map.getSource(INPE_SOURCE_ID) as GeoJSONSource | undefined

        if (!source || !Number.isInteger(clusterId) || !coordinates) return

        void source
          .getClusterExpansionZoom(clusterId)
          .then((zoom) => {
            map.easeTo({
              center: [coordinates[0], coordinates[1]],
              zoom,
            })
          })
          .catch((error: unknown) => {
            console.error('Não foi possível expandir o agrupamento de focos.', error)
          })
      })

      map.on('click', INPE_UNCLUSTERED_LAYER_ID, (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0]
        const coordinates = feature?.geometry.type === 'Point' ? feature.geometry.coordinates : null

        if (!feature || !coordinates) return

        hotspotPopupRef.current?.remove()

        const popup = new Popup({ closeButton: true, maxWidth: '320px' })
          .setLngLat([coordinates[0], coordinates[1]])
          .setHTML(buildHotspotPopup(feature.properties ?? {}))
          .addTo(map)

        hotspotPopupRef.current = popup
        popup.on('close', () => {
          if (hotspotPopupRef.current === popup) hotspotPopupRef.current = null
        })
      })

      map.on('click', CELLS_FILL_LAYER_ID, (event: MapLayerMouseEvent) => {
        const hotspotFeatures = map.queryRenderedFeatures(event.point, {
          layers: [INPE_CLUSTER_LAYER_ID, INPE_UNCLUSTERED_LAYER_ID],
        })

        if (hotspotFeatures.length > 0) return

        const feature = event.features?.[0]
        const cellId = feature?.properties?.id as string | undefined
        if (!cellId) return

        const cell = cellsRef.current.find((item) => item.id === cellId)
        if (!cell) return

        onCellSelectRef.current(cellId)

        const currentLayer = layerRef.current
        const value = currentLayer === 'risk' ? cell.risk : cell.danger[dateRef.current]
        const indexLabel = currentLayer === 'risk' ? 'Risco' : 'Perigo'
        const formattedValue = value == null ? 'Sem dado' : value.toFixed(2)

        hotspotPopupRef.current?.remove()

        new Popup({ closeButton: true })
          .setLngLat(event.lngLat)
          .setHTML(
            `<strong>${cell.id}</strong><br/>` +
              `Longitude: ${cell.centroid[0].toFixed(4)}<br/>` +
              `Latitude: ${cell.centroid[1].toFixed(4)}<br/>` +
              `${indexLabel}: ${formattedValue}`,
          )
          .addTo(map)
      })
    })

    mapRef.current = map

    return () => {
      hotspotPopupRef.current?.remove()
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const source = mapRef.current?.getSource(CELLS_SOURCE_ID) as GeoJSONSource | undefined
    source?.setData(geojson)
  }, [geojson])

  useEffect(() => {
    const source = mapRef.current?.getSource(INPE_SOURCE_ID) as GeoJSONSource | undefined
    source?.setData(hotspots ?? EMPTY_HOTSPOTS)

    if (!hotspots) hotspotPopupRef.current?.remove()
  }, [hotspots])

  useEffect(() => {
    const map = mapRef.current
    const visibility = showHotspots && Boolean(hotspots?.features.length) ? 'visible' : 'none'

    for (const layerId of [
      INPE_CLUSTER_LAYER_ID,
      INPE_CLUSTER_COUNT_LAYER_ID,
      INPE_UNCLUSTERED_LAYER_ID,
    ]) {
      if (map?.getLayer(layerId)) map.setLayoutProperty(layerId, 'visibility', visibility)
    }

    if (visibility === 'none') hotspotPopupRef.current?.remove()
  }, [hotspots, showHotspots])

  useEffect(() => {
    const map = mapRef.current
    if (!map?.getLayer(SELECTED_CELL_LAYER_ID)) return

    map.setFilter(SELECTED_CELL_LAYER_ID, [
      '==',
      ['get', 'id'],
      selectedCellId ?? '__none__',
    ])
  }, [selectedCellId])

  return (
    <div className="map-shell">
      <div ref={containerRef} className="map-container" />
      <MapLegend layer={layer} showHotspots={showHotspots && Boolean(hotspots?.features.length)} />
      <div className="map-prototype-note">
        Malha demonstrativa · resolução não corresponde à base científica final
      </div>
    </div>
  )
}
