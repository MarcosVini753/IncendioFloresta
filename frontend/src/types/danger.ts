import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson'
import type {
  AggregatedCellCollection,
  AggregatedCellProperties,
  SusceptibilityModelId,
} from './susceptibility'

export interface DangerGridProperties {
  id: string
  centroid: [number, number]
  n_source_cells: number
  aggregation: 'mean'
}

export type DangerGridCollection = FeatureCollection<Polygon | MultiPolygon, DangerGridProperties>

export interface DangerModelManifest {
  id: SusceptibilityModelId
  label: string
  file: string
  validation_2013: { roc_auc: number; pr_auc: number }
  test_2014_2015: { roc_auc: number; pr_auc: number }
}

export interface DangerManifest {
  schema_version: '1.0'
  product: 'wildfire_historical_daily_danger'
  label: string
  generated_at: string
  source_period: '2015-01-01/2015-12-31'
  crs: 'EPSG:4326'
  default_model: SusceptibilityModelId
  default_date: string
  dates: string[]
  cell_order: string[]
  models: DangerModelManifest[]
  value: { semantics: 'relative_score'; domain: [number, number]; calibrated_probability: false }
  protocol: {
    training: string
    validation: string
    historical_test: string
    predictor_count: number
    seed: number
    fire_context: 'previous_days_only'
  }
  original_grid: {
    crs: string
    cell_width_m: number
    cell_height_m: number
    cell_count: number
  }
  representation: { type: 'aggregated_grid'; step_degrees: number; aggregation: 'mean' }
  counts: { dates: number; features: number; source_cells_per_date: number }
  bounds: [number, number, number, number]
  files: { grid: string }
}

export interface DangerScoreMatrix {
  schema_version: '1.0'
  model: SusceptibilityModelId
  values: number[][]
}

export interface DangerProduct {
  manifest: DangerManifest
  grid: DangerGridCollection
  scores: Record<SusceptibilityModelId, number[][]>
  bounds: [[number, number], [number, number]]
}

export interface DangerDayView {
  cells: AggregatedCellCollection
  statewideSeries: { date: string; value: number }[]
}

export type DangerCellProperties = AggregatedCellProperties
