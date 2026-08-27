import type { MultiPolygon, Polygon } from 'geojson'

export type LayerType = 'risk' | 'danger' | 'alert'

export type CellGeometry = Polygon | MultiPolygon

export interface PrototypeCell {
  id: string
  centroid: [number, number]
  geometry: CellGeometry
  risk: number
  danger: Record<string, number | null>
}

export interface TimeSeriesPoint {
  date: string
  value: number
}
