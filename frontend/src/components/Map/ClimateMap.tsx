import { useEffect, useMemo, useRef } from 'react'
import { Map as MapLibreMap, NavigationControl, Popup, type GeoJSONSource, type MapLayerMouseEvent } from 'maplibre-gl'
import { cellStats } from '../../data/climate'
import type { ClimateProduct, ClimateVariable } from '../../types/climate'

interface ClimateMapProps {
  product: ClimateProduct
  variable: ClimateVariable
  date: string
  showScars: boolean
  selectedCellId: string | null
  onCellSelect: (id: string) => void
}

const GRID_SOURCE = 'climate-grid'
const GRID_FILL = 'climate-grid-fill'
const GRID_LINE = 'climate-grid-line'
const SELECTED_LINE = 'climate-selected-cell'
const SCARS_SOURCE = 'observed-scars'
const SCAR_POINTS_SOURCE = 'observed-scar-points'
const SCARS_FILL = 'observed-scars-fill'
const SCARS_LINE = 'observed-scars-line'
const SCAR_POINTS = 'observed-scar-markers'

const COLORS = {
  humidity: ['interpolate', ['linear'], ['coalesce', ['get', 'value'], -1],
    -1, '#9ca3af', 0, '#ca8340', 50, '#e7c86f', 70, '#72b997', 85, '#237c91', 100, '#155276'],
  precipitation: ['interpolate', ['linear'], ['coalesce', ['get', 'value'], -1],
    -1, '#9ca3af', 0, '#f7f4e7', 1, '#c4e4ef', 10, '#69aed7', 30, '#3164a6', 60, '#422b7a', 170, '#261b59'],
} as const

function fmt(value: number | null, unit: string) {
  return value === null ? 'Sem dado' : `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value)} ${unit}`
}

export function ClimateMap({ product, variable, date, showScars, selectedCellId, onCellSelect }: ClimateMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const popupRef = useRef<Popup | null>(null)
  const currentRef = useRef({ date, variable, onCellSelect, product, showScars, selectedCellId })
  currentRef.current = { date, variable, onCellSelect, product, showScars, selectedCellId }

  const collection = useMemo(() => {
    const day = product.manifest.dates.indexOf(date)
    return {
      ...product.grid,
      features: product.grid.features.map((feature, index) => ({
        ...feature,
        properties: { ...feature.properties, value: product[variable].values[day][index][1] },
      })),
    }
  }, [product, variable, date])
  const collectionRef = useRef(collection)
  collectionRef.current = collection
  const scarPoints = useMemo(() => ({
    type: 'FeatureCollection' as const,
    features: product.scars.features.map((feature) => ({
      type: 'Feature' as const,
      properties: feature.properties,
      geometry: { type: 'Point' as const, coordinates: feature.properties.center },
    })),
  }), [product])

  useEffect(() => {
    if (!containerRef.current) return
    const map = new MapLibreMap({
      container: containerRef.current,
      style: 'https://demotiles.maplibre.org/style.json',
      center: [-70.3, -9.3], zoom: 5.2, attributionControl: {},
    })
    map.addControl(new NavigationControl(), 'top-right')
    map.on('load', () => {
      map.addSource('climate-boundary', { type: 'geojson', data: product.boundary })
      const current = currentRef.current
      map.addSource(GRID_SOURCE, { type: 'geojson', data: collectionRef.current })
      map.addSource(SCARS_SOURCE, { type: 'geojson', data: product.scars })
      map.addSource(SCAR_POINTS_SOURCE, { type: 'geojson', data: scarPoints })
      map.addLayer({ id: GRID_FILL, type: 'fill', source: GRID_SOURCE,
        paint: { 'fill-color': COLORS[current.variable] as never, 'fill-opacity': 0.82 } })
      map.addLayer({ id: GRID_LINE, type: 'line', source: GRID_SOURCE,
        paint: { 'line-color': 'rgba(255,255,255,.8)', 'line-width': 0.7 } })
      map.addLayer({ id: SELECTED_LINE, type: 'line', source: GRID_SOURCE,
        filter: ['==', ['get', 'id'], current.selectedCellId ?? '__none__'],
        paint: { 'line-color': '#142f2c', 'line-width': 3.4 } })
      map.addLayer({ id: SCARS_FILL, type: 'fill', source: SCARS_SOURCE,
        filter: ['==', ['get', 'date'], current.date],
        layout: { visibility: current.showScars ? 'visible' : 'none' },
        paint: { 'fill-color': '#e94431', 'fill-opacity': 0.88 } })
      map.addLayer({ id: SCARS_LINE, type: 'line', source: SCARS_SOURCE,
        filter: ['==', ['get', 'date'], current.date],
        layout: { visibility: current.showScars ? 'visible' : 'none' },
        paint: { 'line-color': '#752817', 'line-width': 0.7 } })
      map.addLayer({ id: SCAR_POINTS, type: 'circle', source: SCAR_POINTS_SOURCE,
        filter: ['==', ['get', 'date'], current.date],
        layout: { visibility: current.showScars ? 'visible' : 'none' },
        paint: { 'circle-color': '#e94431',
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 3.5, 9, 1.5],
          'circle-stroke-color': '#fff', 'circle-stroke-width': 0.7 } })
      map.addLayer({ id: 'climate-boundary-line', type: 'line', source: 'climate-boundary',
        paint: { 'line-color': '#173f32', 'line-width': 2.4 } })

      const [west, south, east, north] = product.manifest.bounds
      map.fitBounds([[west, south], [east, north]], { padding: 44, duration: 0 })
      for (const layer of [GRID_FILL, SCARS_FILL, SCAR_POINTS]) {
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }
      const onScarClick = (event: MapLayerMouseEvent) => {
        const scar = event.features?.[0]
        if (!scar) return
        const underlying = map.queryRenderedFeatures(event.point, { layers: [GRID_FILL] })[0]
        const id = underlying?.properties?.id
        if (typeof id === 'string') currentRef.current.onCellSelect(id)
        popupRef.current?.remove()
        popupRef.current = new Popup({ closeButton: true, maxWidth: '260px' })
          .setLngLat(event.lngLat)
          .setText(`Cicatriz observada em ${String(scar.properties?.date)}. A data é a detecção registrada no raster.`)
          .addTo(map)
      }
      map.on('click', SCARS_FILL, (event: MapLayerMouseEvent) => {
        if (!map.queryRenderedFeatures(event.point, { layers: [SCAR_POINTS] }).length) onScarClick(event)
      })
      map.on('click', SCAR_POINTS, onScarClick)
      map.on('click', GRID_FILL, (event: MapLayerMouseEvent) => {
        if (map.queryRenderedFeatures(event.point, { layers: [SCARS_FILL, SCAR_POINTS] }).length) return
        const id = event.features?.[0]?.properties?.id
        if (typeof id !== 'string') return
        const active = currentRef.current
        active.onCellSelect(id)
        const stats = cellStats(active.product, active.variable, active.date, id)
        const unit = active.product.manifest.variables[active.variable].unit
        popupRef.current?.remove()
        popupRef.current = new Popup({ closeButton: true })
          .setLngLat(event.lngLat)
          .setText(`${id} · média espacial: ${fmt(stats[1], unit)}`)
          .addTo(map)
      })
    })
    mapRef.current = map
    return () => { popupRef.current?.remove(); map.remove(); mapRef.current = null }
  }, [product, scarPoints])

  useEffect(() => {
    const map = mapRef.current
    const source = map?.getSource(GRID_SOURCE) as GeoJSONSource | undefined
    source?.setData(collection)
    if (map?.getLayer(GRID_FILL)) map.setPaintProperty(GRID_FILL, 'fill-color', COLORS[variable] as never)
    popupRef.current?.remove()
  }, [collection, variable])

  useEffect(() => {
    const map = mapRef.current
    for (const layer of [SCARS_FILL, SCARS_LINE, SCAR_POINTS]) {
      if (!map?.getLayer(layer)) continue
      map.setFilter(layer, ['==', ['get', 'date'], date])
      map.setLayoutProperty(layer, 'visibility', showScars ? 'visible' : 'none')
    }
    popupRef.current?.remove()
  }, [date, showScars])

  useEffect(() => {
    const map = mapRef.current
    if (map?.getLayer(SELECTED_LINE)) {
      map.setFilter(SELECTED_LINE, ['==', ['get', 'id'], selectedCellId ?? '__none__'])
    }
  }, [selectedCellId])

  return (
    <div className="map-shell">
      <div ref={containerRef} className="map-container" />
      <div className="map-legend-stack">
        <div className="map-legend" aria-label={`Legenda de ${variable === 'humidity' ? 'umidade' : 'precipitação'}`}>
          <strong>{variable === 'humidity' ? 'Umidade relativa · %' : 'Precipitação · mm'}</strong>
          <div className={`legend-gradient climate-gradient-${variable}`} />
          <div className="legend-scale"><span>{variable === 'humidity' ? '0%' : '0 mm'}</span><span>{variable === 'humidity' ? '100%' : '60+ mm'}</span></div>
          <small>Cinza: sem dado climático</small>
        </div>
        {showScars && <div className="hotspot-legend"><strong><i className="scar-swatch" /> Cicatriz observada</strong><span>Detecção no dia selecionado</span></div>}
      </div>
      <div className="map-prototype-note">Clima diário histórico · 2015 · estatísticas espaciais por célula de 0,28°</div>
    </div>
  )
}
