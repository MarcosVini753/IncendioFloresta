import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'

export const SUSCEPTIBILITY_MODEL_IDS = [
  'gradboost',
  'random_forest',
  'logistic_regression',
  'xgboost',
] as const

export type SusceptibilityModelId = (typeof SUSCEPTIBILITY_MODEL_IDS)[number]
export const RISK_SCENARIO_IDS = ['todos', 'todos_regional', 'razao_1x19', 'todos_historico'] as const
export type RiskScenario = (typeof RISK_SCENARIO_IDS)[number]
export type SusceptibilityScoreProperty = `score_${RiskScenario}_${SusceptibilityModelId}`
export type SusceptibilityPercentileProperty = `percentile_${RiskScenario}_${SusceptibilityModelId}`
export type AggregatedMaxPercentileProperty = `max_${SusceptibilityPercentileProperty}`
export type SusceptibilityScores = Record<SusceptibilityScoreProperty, number> & Record<SusceptibilityPercentileProperty, number>

export const RISK_PRIORITY_CUTS = [1, 5, 10, 20] as const
export type RiskPriorityCut = (typeof RISK_PRIORITY_CUTS)[number]

export type RiskEvaluationMetrics = {
  prevalencia: number
  roc_auc: number
  pr_auc: number
  brier: number
} & Record<`det@${RiskPriorityCut}%`, number>

export interface RiskEvaluation {
  historical_test_2025: Record<RiskScenario, Record<SusceptibilityModelId, RiskEvaluationMetrics>>
  test_positive_cells: number
  notice: string
  received_rolling_2017_2024: {
    ano: string
    cenario: RiskScenario
    model_id: SusceptibilityModelId
    pr_auc: string
    roc_auc: string
    n_positivos: string
  }[]
}

export interface AggregatedCellProperties extends SusceptibilityScores, Record<AggregatedMaxPercentileProperty, number> {
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
  percentile_properties: Record<RiskScenario, SusceptibilityPercentileProperty>
  validation: {
    protocol: 'group_kfold_by_year_full_map'
    folds: number
  }
}

export interface SusceptibilityManifest {
  schema_version: '2.0'
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
      selection: { selection: string; parameter_source_scenario: string }
      table_hash: string
    }>
  }
  training: {
    target: string
    seed: number
    predictors: string[]
    history_predictors: string[]
    interpolation: 'bilinear'
    categorical_vegetation: true
    evaluation: string
    train_years: [number, number]
    climate_year: number
  }
  value: {
    semantics: 'relative_score'
    domain: [number, number]
    calibrated_probability: false
  }
  percentile: {
    semantics: 'statewide_rank_percentile'
    domain: [0, 100]
    population: 307410
    ties: 'average'
    aggregation: 'mean_of_native_percentiles'
    notice: string
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
    color_aggregation: 'max'
    color_property_prefix: 'max_'
    notice: string
  }
  counts: {
    source_cells: number
    features: number
  }
  evaluation: RiskEvaluation
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
  schema_version: '2.0'
  product: 'wildfire_annual_risk_native_index'
  generated_at: string
  crs: 'EPSG:4326'
  sector_step_degrees: number
  feature_count: number
  sectors: NativeSectorIndexEntry[]
}

export interface NativeSusceptibilityManifest {
  schema_version: '2.0'
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
  percentile: SusceptibilityManifest['percentile']
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

export function modelScoreProperty(model: SusceptibilityModelId, scenario: RiskScenario = 'todos_historico'): SusceptibilityScoreProperty {
  return `score_${scenario}_${model}`
}

export const MODEL_SCORE_PROPERTY = Object.fromEntries(
  SUSCEPTIBILITY_MODEL_IDS.map((id) => [id, modelScoreProperty(id)]),
) as Record<SusceptibilityModelId, SusceptibilityScoreProperty>

export const SCORE_PROPERTIES = RISK_SCENARIO_IDS.flatMap(
  (scenario) => SUSCEPTIBILITY_MODEL_IDS.map((model) => modelScoreProperty(model, scenario)),
)

export function modelPercentileProperty(model: SusceptibilityModelId, scenario: RiskScenario = 'todos_historico'): SusceptibilityPercentileProperty {
  return `percentile_${scenario}_${model}`
}

export const PERCENTILE_PROPERTIES = RISK_SCENARIO_IDS.flatMap(
  (scenario) => SUSCEPTIBILITY_MODEL_IDS.map((model) => modelPercentileProperty(model, scenario)),
)

export function modelMaxPercentileProperty(model: SusceptibilityModelId, scenario: RiskScenario = 'todos_historico'): AggregatedMaxPercentileProperty {
  return `max_${modelPercentileProperty(model, scenario)}`
}
