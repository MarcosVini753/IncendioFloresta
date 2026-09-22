import type { Feature, MultiPolygon, Polygon } from 'geojson'
import {
  MODEL_SCORE_PROPERTY,
  SUSCEPTIBILITY_MODEL_IDS,
  type AggregatedCellCollection,
  type AggregatedCellProperties,
  type SusceptibilityManifest,
  type SusceptibilityModelId,
  type SusceptibilityProduct,
  type SusceptibilityScoreProperty,
} from '../types/susceptibility'

const PRODUCT_BASE_URL = '/data/susceptibility/v1/aggregated'
const SCORE_PROPERTIES = Object.values(MODEL_SCORE_PROPERTY)

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
  if (!isRecord(value)) throw new Error('Manifesto de suscetibilidade inválido.')
  if (value.schema_version !== '1.0' || value.product !== 'wildfire_susceptibility') {
    throw new Error('Contrato do produto de suscetibilidade não é compatível com o frontend.')
  }
  if (value.crs !== 'EPSG:4326' || value.source_period !== '2006-2016') {
    throw new Error('Metadados espaciais ou período-fonte inesperados no manifesto.')
  }
  if (!isModelId(value.default_model) || !Array.isArray(value.models) || value.models.length !== 4) {
    throw new Error('O manifesto não descreve os quatro modelos esperados.')
  }
  const modelIds = new Set<string>()
  for (const model of value.models) {
    if (!isRecord(model) || !isModelId(model.id) || typeof model.label !== 'string') {
      throw new Error('Modelo inválido no manifesto de suscetibilidade.')
    }
    if (model.property !== MODEL_SCORE_PROPERTY[model.id] || modelIds.has(model.id)) {
      throw new Error('Mapeamento ou ID de modelo inválido no manifesto.')
    }
    modelIds.add(model.id)
  }
  if (!isRecord(value.value) || value.value.semantics !== 'relative_score') {
    throw new Error('A semântica do produto deve ser relative_score.')
  }
  if (!isRecord(value.representation) || value.representation.type !== 'aggregated_grid') {
    throw new Error('O produto não representa a grade agregada esperada.')
  }
  if (!isRecord(value.counts) || value.counts.source_cells !== 307410) {
    throw new Error('A contagem de células científicas do manifesto é inválida.')
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
    throw new Error('O mapa de suscetibilidade não é uma FeatureCollection.')
  }
  if (value.features.length !== manifest.counts.features || value.features.length === 0) {
    throw new Error('A quantidade de células do GeoJSON difere do manifesto.')
  }
  const ids = new Set<string>()
  let sourceCellCount = 0
  for (const rawFeature of value.features) {
    if (!isRecord(rawFeature) || rawFeature.type !== 'Feature' || !isRecord(rawFeature.geometry)) {
      throw new Error('Feature inválida no mapa de suscetibilidade.')
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
) {
  return properties[MODEL_SCORE_PROPERTY[model]]
}
