import { useEffect, useMemo, useRef } from 'react'
import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type GeoJSONSource,
  type MapLayerMouseEvent,
} from 'maplibre-gl'
import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'
import type { LayerType, PrototypeCell } from '../../types/fire'
import { MapLegend } from '../Legend/MapLegend'

interface FireMapProps {
  layer: LayerType
  selectedDate: string
  cells: PrototypeCell[]
  boundary: Feature<Polygon | MultiPolygon>
  bounds: [[number, number], [number, number]]
}

const CELLS_SOURCE_ID = 'prototype-cells'
const CELLS_FILL_LAYER_ID = 'prototype-cells-fill'
const CELLS_LINE_LAYER_ID = 'prototype-cells-line'
const ACRE_SOURCE_ID = 'acre-boundary'
const ACRE_OUTLINE_LAYER_ID = 'acre-outline'

export function FireMap({ layer, selectedDate, cells, boundary, bounds }: FireMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const layerRef = useRef<LayerType>(layer)
  const dateRef = useRef(selectedDate)
  const cellsRef = useRef(cells)

  layerRef.current = layer
  dateRef.current = selectedDate
  cellsRef.current = cells

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
      map.addSource(ACRE_SOURCE_ID, {
        type: 'geojson',
        data: boundary,
      })

      map.addSource(CELLS_SOURCE_ID, {
        type: 'geojson',
        data: geojson,
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

      map.on('click', CELLS_FILL_LAYER_ID, (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0]
        const cellId = feature?.properties?.id as string | undefined
        if (!cellId) return

        const cell = cellsRef.current.find((item) => item.id === cellId)
        if (!cell) return

        const currentLayer = layerRef.current
        const value =
          currentLayer === 'risk' ? cell.risk : cell.danger[dateRef.current]
        const indexLabel = currentLayer === 'risk' ? 'Risco' : 'Perigo'
        const formattedValue = value == null ? 'Sem dado' : value.toFixed(2)

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
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const source = mapRef.current?.getSource(CELLS_SOURCE_ID) as GeoJSONSource | undefined
    source?.setData(geojson)
  }, [geojson])

  return (
    <div className="map-shell">
      <div ref={containerRef} className="map-container" />
      <MapLegend layer={layer} />
      <div className="map-prototype-note">
        Malha demonstrativa · resolução não corresponde à base científica final
      </div>
    </div>
  )
}
