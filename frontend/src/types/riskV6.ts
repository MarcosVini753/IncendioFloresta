import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'

export const RISK_V6_MODELS = ['random_forest'] as const
export type RiskV6Model = (typeof RISK_V6_MODELS)[number]
export const RISK_V6_CLASSES = [
  {
    id: 'very_low',
    label: 'Muito baixo',
    lower: 0,
    upper: 50,
    color: '#1a9850',
  },
  { id: 'low', label: 'Baixo', lower: 50, upper: 70, color: '#91cf60' },
  { id: 'moderate', label: 'Moderado', lower: 70, upper: 90, color: '#fee08b' },
  { id: 'high', label: 'Alto', lower: 90, upper: 95, color: '#fc8d59' },
  {
    id: 'very_high',
    label: 'Muito alto',
    lower: 95,
    upper: 100,
    color: '#d73027',
  },
] as const

export interface RiskV6Values {
  value_random_forest: number
  percentile_random_forest: number
}

export interface RiskV6Cell extends RiskV6Values {
  id: string
  centroid: [number, number]
  n_source_pixels: number
  aggregation: 'mean'
  [key: string]: unknown
}

export type RiskV6Grid = FeatureCollection<Polygon | MultiPolygon, RiskV6Cell>
export interface RiskV6Pixel extends RiskV6Values {
  id: string
  row: number
  column: number
  centroid: [number, number]
  bbox: [number, number, number, number]
}
export type RiskV6Selection =
  | { kind: 'aggregated'; properties: RiskV6Cell }
  | { kind: 'pixel'; properties: RiskV6Pixel }

export interface RiskV6Sector {
  id: string
  url: string
  window: [number, number, number, number]
  bbox: [number, number, number, number]
  valid_pixels: number
  bytes: number
}

export interface RiskV6Index {
  schema_version: '6.0'
  year: 2025 | 2026
  crs: 'EPSG:4326'
  width: number
  height: number
  transform: [number, number, number, number, number, number]
  sector_size: 1024
  bands: string[]
  valid_pixels: number
  sectors: RiskV6Sector[]
}

export interface RiskV6Historical {
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

export interface RiskV6Manifest {
  schema_version: '6.0'
  product: 'wildfire_annual_risk'
  label: string
  year: 2025 | 2026
  generated_at: string
  default_model: RiskV6Model
  scenario: 'F30C'
  models: {
    id: RiskV6Model
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
    climate_year: null
    landcover_year: number
    uses_climate: false
    fire_source: string
    predictors: string[]
    climate_smoothing: false
    seed: 42
  }
  territory: { source: 'IBGE'; year: 2024; mask: 'received_geotiff_valid_pixels'; boundary_sha256: string; boundary_simplified: true }
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
  classes: typeof RISK_V6_CLASSES
  counts: { source_pixels: number; features: number; sectors: number }
  bounds: [number, number, number, number]
  files: { grid: string; boundary: string; index: string }
  evaluation: {
    origin: 'received_professor'
    level: '30m_fogo'
    target_year_available: boolean
    historical: Record<RiskV6Model, RiskV6Historical[]>
  }
  provenance: { identity: string; source_values_unchanged: true }
}

export interface RiskV6Product {
  manifest: RiskV6Manifest
  cells: RiskV6Grid
  boundary: Feature<Polygon | MultiPolygon>
  index: RiskV6Index
  /** null: this deployment includes only the scientific 5 km aggregates. */
  rasterBase: string | null
}
