import { useEffect, useMemo, useRef } from 'react'
import { Map as MapLibreMap, NavigationControl, Popup, type GeoJSONSource, type MapLayerMouseEvent } from 'maplibre-gl'
import type { FeatureCollection, Point } from 'geojson'
import { mockCells } from '../../data/risk.mock'
import type { LayerType } from '../../types/fire'
import { MapLegend } from '../Legend/MapLegend'

interface FireMapProps {
  layer: LayerType
  selectedDate: string
}

const SOURCE_ID = 'prototype-cells'
const LAYER_ID = 'prototype-cells-layer'

export function FireMap({ layer, selectedDate }: FireMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const layerRef = useRef<LayerType>(layer)
  const dateRef = useRef(selectedDate)

  layerRef.current = layer
  dateRef.current = selectedDate

  const geojson = useMemo<FeatureCollection<Point>>(
    () => ({
      type: 'FeatureCollection',
      features: mockCells.map((cell) => ({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: cell.coordinates,
        },
        properties: {
          id: cell.id,
          name: cell.name,
          risk: cell.risk,
          danger: cell.danger[selectedDate] ?? 0,
          value: layer === 'risk' ? cell.risk : cell.danger[selectedDate] ?? 0,
        },
      })),
    }),
    [layer, selectedDate],
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
      map.addSource(SOURCE_ID, {
        type: 'geojson',
        data: geojson,
      })

      map.addLayer({
        id: LAYER_ID,
        type: 'circle',
        source: SOURCE_ID,
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 11, 8, 24],
          'circle-opacity': 0.78,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff',
          'circle-color': [
            'interpolate',
            ['linear'],
            ['get', 'value'],
            0,
            '#1a9850',
            0.5,
            '#fee08b',
            1,
            '#d73027',
          ],
        },
      })

      map.on('mouseenter', LAYER_ID, () => {
        map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', LAYER_ID, () => {
        map.getCanvas().style.cursor = ''
      })

      map.on('click', LAYER_ID, (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0]
        if (!feature || feature.geometry.type !== 'Point') return

        const coordinates = feature.geometry.coordinates as [number, number]
        const currentLayer = layerRef.current
        const cell = mockCells.find((item) => item.id === feature.properties?.id)
        if (!cell) return

        const value =
          currentLayer === 'risk'
            ? cell.risk
            : cell.danger[dateRef.current] ?? 0

        const indexLabel = currentLayer === 'risk' ? 'Risco' : 'Perigo'

        new Popup()
          .setLngLat(coordinates)
          .setHTML(
            `<strong>${cell.name}</strong><br/>` +
              `Longitude: ${coordinates[0].toFixed(4)}<br/>` +
              `Latitude: ${coordinates[1].toFixed(4)}<br/>` +
              `${indexLabel}: ${value.toFixed(2)}`,
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
    const source = mapRef.current?.getSource(SOURCE_ID) as GeoJSONSource | undefined
    source?.setData(geojson)
  }, [geojson])

  return (
    <div className="map-shell">
      <div ref={containerRef} className="map-container" />
      <MapLegend layer={layer} />
      <div className="map-prototype-note">Visualização demonstrativa · não usar para decisão operacional</div>
    </div>
  )
}
