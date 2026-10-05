import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'

export type ClimateVariable = 'humidity' | 'precipitation'
export type ClimateStats = [number, number, number] | [null, null, null]

export interface ClimateManifest {
  schema_version: '1.0'
  product: 'historical_climate_and_scars'
  year: 2025
  generated_at: string
  crs: 'EPSG:4326'
  dates: string[]
  cell_order: string[]
  bounds: [number, number, number, number]
  n_valid_pixels: number[]
  grid: { step_degrees: number; source_step_degrees: number }
  statistics: { scope: 'spatial_per_day'; mean: string; extrema: string }
  variables: Record<ClimateVariable, { unit: string; source: string }>
  scars: { source: string; meaning: 'day_of_year_of_detection'; feature_count: number }
  files: { grid: string; boundary: string; humidity: string; precipitation: string; scars: string }
}

export interface ClimateCellProperties {
  id: string
  centroid: [number, number]
}

export type ClimateGrid = FeatureCollection<Polygon | MultiPolygon, ClimateCellProperties>

export interface ClimateMatrix {
  variable: ClimateVariable
  values: ClimateStats[][]
}

export interface ScarProperties {
  date: string
  day_of_year: number
  center: [number, number]
}

export type ScarCollection = FeatureCollection<Polygon | MultiPolygon, ScarProperties>

export interface ClimateProduct {
  manifest: ClimateManifest
  grid: ClimateGrid
  boundary: Feature<Polygon | MultiPolygon>
  humidity: ClimateMatrix
  precipitation: ClimateMatrix
  scars: ScarCollection
}
