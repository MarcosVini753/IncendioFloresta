import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'

export const SUSCEPTIBILITY_MODEL_IDS = [
  'gradboost',
  'random_forest',
  'logistic_regression',
  'fuzzy_knn',
  'xgboost',
] as const

export type SusceptibilityModelId = (typeof SUSCEPTIBILITY_MODEL_IDS)[number]
export type RiskScenario = 'unico' | 'regional'
export type SusceptibilityScoreProperty = `score_${RiskScenario}_${SusceptibilityModelId}`
export type SusceptibilityScores = Record<SusceptibilityScoreProperty, number>

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
  properties: Record<RiskScenario, SusceptibilityScoreProperty>
  validation: {
    protocol: 'group_kfold_by_year_balanced'
    folds: number
    roc_auc: number | null
    pr_auc: number | null
  }
}

export interface SusceptibilityManifest {
  schema_version: '1.0'
  product: 'wildfire_annual_risk'
  label: string
  generated_at: string
  source_period: string
  crs: 'EPSG:4326'
  default_model: SusceptibilityModelId
  default_scenario: RiskScenario
  scenarios: { id: RiskScenario; label: string }[]
  models: SusceptibilityModelManifest[]
  provenance: {
    models: Record<string, {
      parameters: Record<string, number | string | null>
      selection: string
      table_hash: string
    }>
  }
  training: {
    target: string
    sample: string
    seed: number
    predictors: string[]
    evaluation: string
    train_years: [number, number]
    climate_year: number
  }
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
  region?: 'oeste' | 'leste'
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
  product: 'wildfire_annual_risk_native_index'
  generated_at: string
  crs: 'EPSG:4326'
  sector_step_degrees: number
  feature_count: number
  sectors: NativeSectorIndexEntry[]
}

export interface NativeSusceptibilityManifest {
  schema_version: '1.0'
  product: 'wildfire_annual_risk'
  label: string
  generated_at: string
  source_period: string
  crs: 'EPSG:4326'
  default_model: SusceptibilityModelId
  default_scenario: RiskScenario
  scenarios: { id: RiskScenario; label: string }[]
  models: SusceptibilityModelManifest[]
  training: SusceptibilityManifest['training']
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

export function modelScoreProperty(model: SusceptibilityModelId, scenario: RiskScenario = 'regional'): SusceptibilityScoreProperty {
  return `score_${scenario}_${model}`
}

export const MODEL_SCORE_PROPERTY = Object.fromEntries(
  SUSCEPTIBILITY_MODEL_IDS.map((id) => [id, modelScoreProperty(id)]),
) as Record<SusceptibilityModelId, SusceptibilityScoreProperty>

export const SCORE_PROPERTIES = (['unico', 'regional'] as const).flatMap(
  (scenario) => SUSCEPTIBILITY_MODEL_IDS.map((model) => modelScoreProperty(model, scenario)),
)
