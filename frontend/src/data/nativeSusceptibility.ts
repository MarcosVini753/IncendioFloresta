import { MODEL_SCORE_PROPERTY, SUSCEPTIBILITY_MODEL_IDS } from '../types/susceptibility'
import type {
  NativeCellCollection,
  NativeCellProperties,
  NativeGridIndex,
  NativeGridProduct,
  NativeSectorIndexEntry,
  NativeSusceptibilityManifest,
  SusceptibilityModelId,
} from '../types/susceptibility'

const NATIVE_BASE_URL = '/data/susceptibility/v1/native_sharded_grid'
const SCORE_PROPERTIES = Object.values(MODEL_SCORE_PROPERTY)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isModelId(value: unknown): value is SusceptibilityModelId {
  return typeof value === 'string' && SUSCEPTIBILITY_MODEL_IDS.includes(value as SusceptibilityModelId)
}

function isBbox(value: unknown): value is [number, number, number, number] {
  return Array.isArray(value) && value.length === 4 && value.every(Number.isFinite)
}

export function validateNativeManifest(value: unknown): NativeSusceptibilityManifest {
  if (!isRecord(value) || value.schema_version !== '1.0' || value.product !== 'wildfire_susceptibility') {
    throw new Error('Manifesto da grade científica original inválido.')
  }
  if (value.crs !== 'EPSG:4326' || value.default_model !== 'gradboost') {
    throw new Error('CRS ou modelo padrão inesperado na grade científica.')
  }
  if (!Array.isArray(value.models) || value.models.length !== 4) {
    throw new Error('A grade científica não informa os quatro modelos.')
  }
  for (const model of value.models) {
    if (!isRecord(model) || !isModelId(model.id) || model.property !== MODEL_SCORE_PROPERTY[model.id]) {
      throw new Error('Modelo inválido no manifesto da grade científica.')
    }
  }
  if (!isRecord(value.representation) || value.representation.type !== 'native_sharded_grid') {
    throw new Error('Representação nativa incompatível.')
  }
  if (!isRecord(value.counts) || value.counts.features !== 307410 || value.counts.source_cells !== 307410) {
    throw new Error('Contagem inválida no manifesto da grade científica.')
  }
  if (!isRecord(value.files) || typeof value.files.index !== 'string' || !isBbox(value.bounds)) {
    throw new Error('Arquivos ou limites inválidos no manifesto da grade científica.')
  }
  return value as unknown as NativeSusceptibilityManifest
}

export function validateNativeIndex(value: unknown, manifest: NativeSusceptibilityManifest): NativeGridIndex {
  if (!isRecord(value) || value.schema_version !== '1.0' || value.product !== 'wildfire_susceptibility_native_index') {
    throw new Error('Índice de setores da grade científica inválido.')
  }
  if (value.feature_count !== manifest.counts.features || !Array.isArray(value.sectors)) {
    throw new Error('Contagens divergentes no índice da grade científica.')
  }
  const ids = new Set<string>()
  let featureCount = 0
  for (const entry of value.sectors) {
    if (
      !isRecord(entry) ||
      typeof entry.id !== 'string' ||
      !/^AC-R\d{2}C\d{2}$/.test(entry.id) ||
      typeof entry.url !== 'string' ||
      !isBbox(entry.bbox) ||
      !Number.isInteger(entry.feature_count) ||
      Number(entry.feature_count) <= 0 ||
      ids.has(entry.id)
    ) {
      throw new Error('Setor inválido, vazio ou duplicado no índice da grade científica.')
    }
    ids.add(entry.id)
    featureCount += Number(entry.feature_count)
  }
  if (ids.size !== manifest.counts.sectors || featureCount !== manifest.counts.features) {
    throw new Error('A soma dos setores não cobre a grade científica completa.')
  }
  return value as unknown as NativeGridIndex
}

export function validateNativeSector(value: unknown, entry: NativeSectorIndexEntry): NativeCellCollection {
  if (!isRecord(value) || value.type !== 'FeatureCollection' || !Array.isArray(value.features)) {
    throw new Error(`Setor ${entry.id} não é uma FeatureCollection.`)
  }
  if (!value.features.length || value.features.length !== entry.feature_count) {
    throw new Error(`Setor ${entry.id} vazio ou com contagem divergente.`)
  }
  const ids = new Set<string>()
  for (const rawFeature of value.features) {
    if (!isRecord(rawFeature) || rawFeature.type !== 'Feature' || !isRecord(rawFeature.geometry)) {
      throw new Error(`Feature inválida no setor ${entry.id}.`)
    }
    if (rawFeature.geometry.type !== 'Polygon' || !isRecord(rawFeature.properties)) {
      throw new Error(`Geometria inválida no setor ${entry.id}.`)
    }
    const properties = rawFeature.properties
    if (
      typeof properties.id !== 'string' ||
      !/^AC-Y-?\d+-X-?\d+$/.test(properties.id) ||
      !Number.isInteger(properties.grid_x) ||
      !Number.isInteger(properties.grid_y) ||
      properties.aggregation !== 'none' ||
      !Array.isArray(properties.centroid) ||
      properties.centroid.length !== 2 ||
      !properties.centroid.every(Number.isFinite) ||
      ids.has(properties.id)
    ) {
      throw new Error(`Propriedades inválidas no setor ${entry.id}.`)
    }
    for (const property of SCORE_PROPERTIES) {
      const score = properties[property]
      if (typeof score !== 'number' || !Number.isFinite(score) || score < 0 || score > 1) {
        throw new Error(`Escore ${property} inválido em ${properties.id}.`)
      }
    }
    ids.add(properties.id)
  }
  return value as unknown as NativeCellCollection
}

async function fetchJson(url: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`Falha ao carregar ${url} (HTTP ${response.status}).`)
  return response.json()
}

export async function loadNativeGridProduct(signal?: AbortSignal): Promise<NativeGridProduct> {
  const manifest = validateNativeManifest(await fetchJson(`${NATIVE_BASE_URL}/manifest.json`, signal))
  const index = validateNativeIndex(
    await fetchJson(`${NATIVE_BASE_URL}/${manifest.files.index}`, signal),
    manifest,
  )
  return { manifest, index }
}

export async function loadNativeSector(
  entry: NativeSectorIndexEntry,
  signal?: AbortSignal,
): Promise<NativeCellCollection> {
  return validateNativeSector(await fetchJson(`${NATIVE_BASE_URL}/${entry.url}`, signal), entry)
}

function intersects(a: [number, number, number, number], b: [number, number, number, number]) {
  return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1]
}

export function selectNativeSectors(
  index: NativeGridIndex,
  bounds: [number, number, number, number],
  margin = 0,
) {
  const expanded: [number, number, number, number] = [
    bounds[0] - margin,
    bounds[1] - margin,
    bounds[2] + margin,
    bounds[3] + margin,
  ]
  return index.sectors.filter((entry) => intersects(entry.bbox, expanded))
}

export class NativeSectorCache {
  private readonly values = new Map<string, NativeCellCollection>()

  constructor(private readonly capacity = 32) {}

  get(id: string) {
    const value = this.values.get(id)
    if (!value) return undefined
    this.values.delete(id)
    this.values.set(id, value)
    return value
  }

  set(id: string, value: NativeCellCollection) {
    this.values.delete(id)
    this.values.set(id, value)
    while (this.values.size > this.capacity) {
      const oldest = this.values.keys().next().value
      if (oldest === undefined) break
      this.values.delete(oldest)
    }
  }

  get size() {
    return this.values.size
  }
}

export type { NativeCellProperties }
