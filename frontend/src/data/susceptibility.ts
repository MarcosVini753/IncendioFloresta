import type { Feature, MultiPolygon, Polygon } from 'geojson'
import {
  MODEL_SCORE_PROPERTY,
  SCORE_PROPERTIES,
  modelScoreProperty,
  type RiskScenario,
  SUSCEPTIBILITY_MODEL_IDS,
  type AggregatedCellCollection,
  type AggregatedCellProperties,
  type SusceptibilityManifest,
  type SusceptibilityModelId,
  type SusceptibilityProduct,
  type SusceptibilityScoreProperty,
} from '../types/susceptibility'

const PRODUCT_BASE_URL = '/data/risk/v1/2025/aggregated'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isFiniteScore(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
}

function isModelId(value: unknown): value is SusceptibilityModelId {
  return typeof value === 'string' && SUSCEPTIBILITY_MODEL_IDS.includes(value as SusceptibilityModelId)
}

export function validateManifest(value: unknown): SusceptibilityManifest {
  if (!isRecord(value)) throw new Error('Manifesto do produto de risco inválido.')
  if (value.schema_version !== '1.0' || value.product !== 'wildfire_annual_risk') {
    throw new Error('Contrato do produto de risco não é compatível com o frontend.')
  }
  if (value.crs !== 'EPSG:4326' || typeof value.source_period !== 'string' || !/^\d{4}$/.test(value.source_period)) {
    throw new Error('O produto deve indicar um único ano de referência.')
  }
  if (!isRecord(value.training) || value.training.target !== `burned_in_${value.source_period}`) {
    throw new Error('O alvo não corresponde ao ano de referência do produto publicado.')
  }
  if (value.default_model !== 'random_forest' || !isModelId(value.default_model) || !Array.isArray(value.models) || value.models.length !== 5) {
    throw new Error('O manifesto não descreve os cinco modelos esperados.')
  }
  const modelIds = new Set<string>()
  for (const model of value.models) {
    if (!isRecord(model) || !isModelId(model.id) || typeof model.label !== 'string') {
      throw new Error('Modelo inválido no manifesto do produto de risco.')
    }
    if (model.property !== MODEL_SCORE_PROPERTY[model.id] || modelIds.has(model.id)) {
      throw new Error('Mapeamento ou ID de modelo inválido no manifesto.')
    }
    if (!isRecord(model.properties) || model.properties.unico !== modelScoreProperty(model.id, 'unico') || model.properties.regional !== modelScoreProperty(model.id, 'regional')) {
      throw new Error('Mapeamento dos cenários inválido.')
    }
    modelIds.add(model.id)
  }
  if (value.default_scenario !== 'regional' || !Array.isArray(value.scenarios) || value.scenarios.length !== 2 || new Set(value.scenarios.map((s) => isRecord(s) ? s.id : null)).size !== 2 || !value.scenarios.every((s) => isRecord(s) && ['unico', 'regional'].includes(String(s.id)) && typeof s.label === 'string')) {
    throw new Error('Cenários de risco inválidos.')
  }
  if (value.training.climate_year !== 2024 || !Array.isArray(value.training.train_years) || value.training.train_years.join(',') !== '2007,2024' || value.source_period !== '2025' || value.training.seed !== 42 || !Array.isArray(value.training.predictors) || value.training.predictors.join(',') !== 'veg,dist_estrada,dist_agua,altitude,ur_media_ano,prec_acum_ano') {
    throw new Error('Protocolo temporal ou preditores incompatíveis.')
  }
  if (!isRecord(value.value) || value.value.semantics !== 'relative_score' || value.value.calibrated_probability !== false || !Array.isArray(value.value.domain) || value.value.domain.join(',') !== '0,1') {
    throw new Error('A semântica do produto deve ser relative_score.')
  }
  if (!isRecord(value.representation) || value.representation.type !== 'aggregated_grid') {
    throw new Error('O produto não representa a grade agregada esperada.')
  }
  if (!isRecord(value.counts) || value.counts.source_cells !== 307410) {
    throw new Error('A contagem de células científicas do manifesto é inválida.')
  }
  if (!isRecord(value.provenance) || !isRecord(value.provenance.models)) {
    throw new Error('Proveniência dos modelos ausente.')
  }
  for (const scope of ['acre', 'oeste', 'leste']) {
    const fuzzy = value.provenance.models[`fuzzy_knn/${scope}`]
    if (!isRecord(fuzzy) || !isRecord(fuzzy.parameters) || !Number.isInteger(fuzzy.parameters.k) || Number(fuzzy.parameters.k) < 1) {
      throw new Error('Parâmetros Fuzzy inválidos na proveniência.')
    }
  }
  if (!isRecord(value.original_grid) || value.original_grid.crs !== 'EPSG:31979' || value.original_grid.cell_count !== 307410 ||
    typeof value.original_grid.cell_width_m !== 'number' || !Number.isFinite(value.original_grid.cell_width_m) || value.original_grid.cell_width_m <= 0 ||
    typeof value.original_grid.cell_height_m !== 'number' || !Number.isFinite(value.original_grid.cell_height_m) || value.original_grid.cell_height_m <= 0) {
    throw new Error('Resolução científica original inválida.')
  }
  if (!Array.isArray(value.bounds) || value.bounds.length !== 4 || !value.bounds.every(Number.isFinite)) {
    throw new Error('Os limites geográficos do manifesto são inválidos.')
  }
  if (!isRecord(value.files) || typeof value.files.geojson !== 'string' || typeof value.files.boundary !== 'string') {
    throw new Error('O manifesto não informa os arquivos públicos esperados.')
  }
  return value as unknown as SusceptibilityManifest
}

function validateProperties(value: unknown): AggregatedCellProperties {
  if (!isRecord(value) || typeof value.id !== 'string' || value.aggregation !== 'mean') {
    throw new Error('Célula agregada com propriedades inválidas.')
  }
  if (
    !Array.isArray(value.centroid) ||
    value.centroid.length !== 2 ||
    !value.centroid.every(Number.isFinite) ||
    !Number.isInteger(value.n_source_cells) ||
    Number(value.n_source_cells) <= 0
  ) {
    throw new Error(`Célula ${value.id} sem centroide ou contagem válida.`)
  }
  for (const property of SCORE_PROPERTIES) {
    if (!isFiniteScore(value[property])) {
      throw new Error(`Célula ${value.id} possui ${property} fora de [0, 1].`)
    }
  }
  return value as unknown as AggregatedCellProperties
}

function validateCells(value: unknown, manifest: SusceptibilityManifest): AggregatedCellCollection {
  if (!isRecord(value) || value.type !== 'FeatureCollection' || !Array.isArray(value.features)) {
    throw new Error('O mapa de risco não é uma FeatureCollection.')
  }
  if (value.features.length !== manifest.counts.features || value.features.length === 0) {
    throw new Error('A quantidade de células do GeoJSON difere do manifesto.')
  }
  const ids = new Set<string>()
  let sourceCellCount = 0
  for (const rawFeature of value.features) {
    if (!isRecord(rawFeature) || rawFeature.type !== 'Feature' || !isRecord(rawFeature.geometry)) {
      throw new Error('Feature inválida no mapa de risco.')
    }
    if (rawFeature.geometry.type !== 'Polygon' && rawFeature.geometry.type !== 'MultiPolygon') {
      throw new Error('A grade agregada deve conter apenas Polygon/MultiPolygon.')
    }
    const properties = validateProperties(rawFeature.properties)
    if (ids.has(properties.id)) throw new Error(`ID de célula duplicado: ${properties.id}.`)
    ids.add(properties.id)
    sourceCellCount += properties.n_source_cells
  }
  if (sourceCellCount !== manifest.counts.source_cells) {
    throw new Error('A soma de células científicas agregadas difere do manifesto.')
  }
  return value as unknown as AggregatedCellCollection
}

function validateBoundary(value: unknown): Feature<Polygon | MultiPolygon> {
  if (!isRecord(value) || value.type !== 'Feature' || !isRecord(value.geometry)) {
    throw new Error('Limite do Acre inválido.')
  }
  if (value.geometry.type !== 'Polygon' && value.geometry.type !== 'MultiPolygon') {
    throw new Error('O limite do Acre não contém Polygon/MultiPolygon.')
  }
  return value as unknown as Feature<Polygon | MultiPolygon>
}

async function fetchJson(url: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`Falha ao carregar ${url} (HTTP ${response.status}).`)
  return response.json()
}

export async function loadSusceptibilityProduct(signal?: AbortSignal): Promise<SusceptibilityProduct> {
  const manifest = validateManifest(await fetchJson(`${PRODUCT_BASE_URL}/manifest.json`, signal))
  const [cellsRaw, boundaryRaw] = await Promise.all([
    fetchJson(`${PRODUCT_BASE_URL}/${manifest.files.geojson}`, signal),
    fetchJson(`${PRODUCT_BASE_URL}/${manifest.files.boundary}`, signal),
  ])
  const cells = validateCells(cellsRaw, manifest)
  const boundary = validateBoundary(boundaryRaw)
  const [west, south, east, north] = manifest.bounds
  return { manifest, cells, boundary, bounds: [[west, south], [east, north]] }
}

export function scoreForModel(
  properties: Record<SusceptibilityScoreProperty, number>,
  model: SusceptibilityModelId,
  scenario: RiskScenario = 'regional',
) {
  return properties[modelScoreProperty(model, scenario)]
}
