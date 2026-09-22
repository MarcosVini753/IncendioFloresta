import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'

export const SUSCEPTIBILITY_MODEL_IDS = [
  'gradboost',
  'random_forest',
  'logistic_regression',
  'fuzzy_knn_k29',
] as const

export type SusceptibilityModelId = (typeof SUSCEPTIBILITY_MODEL_IDS)[number]
export type SusceptibilityScoreProperty =
  | 'score_gradboost'
  | 'score_random_forest'
  | 'score_logistic_regression'
  | 'score_fuzzy_knn_k29'

export interface SusceptibilityScores {
  score_gradboost: number
  score_random_forest: number
  score_logistic_regression: number
  score_fuzzy_knn_k29: number
}

export interface AggregatedCellProperties extends SusceptibilityScores {
  id: string
  centroid: [number, number]
  n_source_cells: number
  aggregation: 'mean'
}

export type AggregatedCellFeature = Feature<Polygon | MultiPolygon, AggregatedCellProperties>
export type AggregatedCellCollection = FeatureCollection<
  Polygon | MultiPolygon,
  AggregatedCellProperties
>

export interface SusceptibilityModelManifest {
  id: SusceptibilityModelId
  label: string
  property: SusceptibilityScoreProperty
  validation: {
    protocol: 'spatial_group_kfold_25km'
    folds: number
    roc_auc: number
    pr_auc: number
  }
}

export interface SusceptibilityManifest {
  schema_version: '1.0'
  product: 'wildfire_susceptibility'
  label: string
  generated_at: string
  source_period: string
  crs: 'EPSG:4326'
  default_model: SusceptibilityModelId
  models: SusceptibilityModelManifest[]
  value: {
    semantics: 'relative_score'
    domain: [number, number]
    calibrated_probability: false
  }
  original_grid: {
    crs: string
    cell_width_m: number
    cell_height_m: number
    cell_count: number
  }
  representation: {
    type: 'aggregated_grid'
    step_degrees: number
    aggregation: 'mean'
    notice: string
  }
  counts: {
    source_cells: number
    features: number
  }
  bounds: [number, number, number, number]
  files: {
    geojson: string
    boundary: string
  }
}

export interface SusceptibilityProduct {
  manifest: SusceptibilityManifest
  cells: AggregatedCellCollection
  boundary: Feature<Polygon | MultiPolygon>
  bounds: [[number, number], [number, number]]
}

export interface NativeCellProperties extends SusceptibilityScores {
  id: string
  grid_x: number
  grid_y: number
  centroid: [number, number]
  aggregation: 'none'
}

export type NativeCellFeature = Feature<Polygon, NativeCellProperties>
export type NativeCellCollection = FeatureCollection<Polygon, NativeCellProperties>

export interface NativeSectorIndexEntry {
  id: string
  url: string
  bbox: [number, number, number, number]
  feature_count: number
}

export interface NativeGridIndex {
  schema_version: '1.0'
  product: 'wildfire_susceptibility_native_index'
  generated_at: string
  crs: 'EPSG:4326'
  sector_step_degrees: number
  feature_count: number
  sectors: NativeSectorIndexEntry[]
}

export interface NativeSusceptibilityManifest {
  schema_version: '1.0'
  product: 'wildfire_susceptibility'
  label: string
  generated_at: string
  source_period: string
  crs: 'EPSG:4326'
  default_model: SusceptibilityModelId
  models: SusceptibilityModelManifest[]
  value: SusceptibilityManifest['value']
  original_grid: SusceptibilityManifest['original_grid']
  representation: {
    type: 'native_sharded_grid'
    aggregation: 'none'
    sector_step_degrees: number
  }
  counts: {
    source_cells: number
    features: number
    sectors: number
  }
  bounds: [number, number, number, number]
  files: { index: string }
}

export interface NativeGridProduct {
  manifest: NativeSusceptibilityManifest
  index: NativeGridIndex
}

export type SelectedSusceptibilityCell =
  | { kind: 'aggregated'; feature: AggregatedCellFeature }
  | { kind: 'native'; feature: NativeCellFeature }

export const MODEL_SCORE_PROPERTY: Record<
  SusceptibilityModelId,
  SusceptibilityScoreProperty
> = {
  gradboost: 'score_gradboost',
  random_forest: 'score_random_forest',
  logistic_regression: 'score_logistic_regression',
  fuzzy_knn_k29: 'score_fuzzy_knn_k29',
}
