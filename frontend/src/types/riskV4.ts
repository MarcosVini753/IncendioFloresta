import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'

export const RISK_V4_MODELS = ['random_forest', 'xgboost'] as const
export type RiskV4Model = (typeof RISK_V4_MODELS)[number]
export const RISK_V4_CLASSES = [
  {
    id: 'very_low',
    label: 'Muito baixo',
    lower: 0,
    upper: 50,
    color: '#238677',
  },
  { id: 'low', label: 'Baixo', lower: 50, upper: 70, color: '#8cc89a' },
  { id: 'moderate', label: 'Moderado', lower: 70, upper: 90, color: '#efd47b' },
  { id: 'high', label: 'Alto', lower: 90, upper: 95, color: '#e9a066' },
  {
    id: 'very_high',
    label: 'Muito alto',
    lower: 95,
    upper: 100,
    color: '#cb5c52',
  },
] as const

export interface RiskV4Values {
  value_random_forest: number
  percentile_random_forest: number
  value_xgboost: number
  percentile_xgboost: number
}

export interface RiskV4Cell extends RiskV4Values {
  id: string
  centroid: [number, number]
  n_source_pixels: number
  aggregation: 'mean'
  [key: string]: unknown
}

export type RiskV4Grid = FeatureCollection<Polygon | MultiPolygon, RiskV4Cell>
export interface RiskV4Pixel extends RiskV4Values {
  id: string
  row: number
  column: number
  centroid: [number, number]
  bbox: [number, number, number, number]
}
export type RiskV4Selection =
  | { kind: 'aggregated'; properties: RiskV4Cell }
  | { kind: 'pixel'; properties: RiskV4Pixel }

export interface RiskV4Sector {
  id: string
  url: string
  window: [number, number, number, number]
  bbox: [number, number, number, number]
  valid_pixels: number
  bytes: number
}

export interface RiskV4Index {
  schema_version: '4.0'
  year: 2025 | 2026
  crs: 'EPSG:4326'
  width: number
  height: number
  transform: [number, number, number, number, number, number]
  sector_size: 1024
  bands: string[]
  valid_pixels: number
  sectors: RiskV4Sector[]
}

export interface RiskV4Historical {
  year: number
  level: '30m_fogo'
  origin: 'received_professor'
  training: string
  metrics: {
    n: number
    positivos: number
    pr_auc: number
    roc_auc: number
    brier: number
    'captura_1%': number
    'captura_5%': number
    'captura_10%': number
  }
}

export interface RiskV4Manifest {
  schema_version: '4.0'
  product: 'wildfire_annual_risk'
  label: string
  year: 2025 | 2026
  generated_at: string
  default_model: RiskV4Model
  scenario: 'AB30C_suave'
  models: {
    id: RiskV4Model
    label: string
    value_property: string
    percentile_property: string
    value_unit: 'percent'
    calibrated: boolean
    value_label: string
    calibration: [number, number] | null
    sampling: string
  }[]
  training: {
    years: [2016, number]
    climate_year: number
    fire_source: string
    predictors: string[]
    climate_smoothing: true
  }
  representation: {
    grid_size_m: 5000
    native_resolution_m: 30
    native_zoom: 8.5
    aggregation: 'mean'
    grid_crs: 'EPSG:31979'
    class_share_semantics: string
  }
  percentile: {
    domain: [0, 100]
    origin: 'received_histogram_statewide'
    aggregation: 'mean_of_received_pixel_percentiles'
  }
  classes: typeof RISK_V4_CLASSES
  counts: { source_pixels: number; features: number; sectors: number }
  bounds: [number, number, number, number]
  files: { grid: string; boundary: string; index: string }
  evaluation: {
    origin: 'received_professor'
    level: '30m_fogo'
    target_year_available: boolean
    historical: Record<RiskV4Model, RiskV4Historical[]>
  }
  provenance: { identity: string; source_values_unchanged: true }
}

export interface RiskV4Product {
  manifest: RiskV4Manifest
  cells: RiskV4Grid
  boundary: Feature<Polygon | MultiPolygon>
  index: RiskV4Index
  /** null: this deployment includes only the scientific 5 km aggregates. */
  rasterBase: string | null
}
