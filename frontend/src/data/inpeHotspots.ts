import type {
  InpeHotspotCollection,
  InpeHotspotMetadata,
  InpeHotspotProperties,
} from '../types/inpe'

const INPE_HOTSPOTS_URL = '/data/inpe/focos_ac.geojson'

const OPTIONAL_TEXT_PROPERTIES = [
  'data_hora_gmt',
  'satelite',
  'pais',
  'estado',
  'municipio',
  'bioma',
] as const satisfies readonly (keyof InpeHotspotProperties)[]

const OPTIONAL_NUMBER_PROPERTIES = [
  'dias_sem_chuva',
  'precipitacao',
  'risco_fogo',
  'frp',
] as const satisfies readonly (keyof InpeHotspotProperties)[]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isOptionalText(value: unknown) {
  return value === undefined || value === null || typeof value === 'string'
}

function isOptionalNumber(value: unknown) {
  return value === undefined || value === null || (typeof value === 'number' && Number.isFinite(value))
}

function hasValidProperties(value: unknown): value is InpeHotspotProperties {
  if (!isRecord(value) || typeof value.fonte !== 'string' || !value.fonte.trim()) {
    return false
  }

  return (
    OPTIONAL_TEXT_PROPERTIES.every((property) => isOptionalText(value[property])) &&
    OPTIONAL_NUMBER_PROPERTIES.every((property) => isOptionalNumber(value[property]))
  )
}

function hasValidMetadata(value: unknown): value is InpeHotspotMetadata {
  if (!isRecord(value)) return false

  return (
    typeof value.fonte === 'string' &&
    (value.fonte_url === undefined || typeof value.fonte_url === 'string') &&
    typeof value.arquivo_origem === 'string' &&
    typeof value.estado === 'string' &&
    (value.data_referencia === undefined || typeof value.data_referencia === 'string') &&
    typeof value.gerado_em_utc === 'string' &&
    typeof value.quantidade_focos === 'number' &&
    Number.isInteger(value.quantidade_focos) &&
    value.quantidade_focos >= 0
  )
}

function assertValidHotspotCollection(value: unknown): asserts value is InpeHotspotCollection {
  if (!isRecord(value) || value.type !== 'FeatureCollection' || !Array.isArray(value.features)) {
    throw new Error('O arquivo de focos do INPE não contém uma FeatureCollection válida.')
  }

  if (!hasValidMetadata(value.metadata)) {
    throw new Error('O arquivo de focos do INPE não contém metadados válidos.')
  }

  value.features.forEach((feature, index) => {
    if (!isRecord(feature) || feature.type !== 'Feature' || !isRecord(feature.geometry)) {
      throw new Error(`O foco ${index + 1} não contém uma Feature válida.`)
    }

    const coordinates = feature.geometry.coordinates
    const hasValidCoordinates =
      feature.geometry.type === 'Point' &&
      Array.isArray(coordinates) &&
      coordinates.length === 2 &&
      coordinates.every((coordinate) => typeof coordinate === 'number' && Number.isFinite(coordinate)) &&
      coordinates[0] >= -180 &&
      coordinates[0] <= 180 &&
      coordinates[1] >= -90 &&
      coordinates[1] <= 90

    if (!hasValidCoordinates) {
      throw new Error(`O foco ${index + 1} não contém coordenadas [longitude, latitude] válidas.`)
    }

    if (!hasValidProperties(feature.properties)) {
      throw new Error(`O foco ${index + 1} não contém propriedades válidas.`)
    }
  })

  if (value.metadata.quantidade_focos !== value.features.length) {
    throw new Error(
      'A quantidade de focos informada nos metadados não corresponde às features do GeoJSON.',
    )
  }
}

export async function loadInpeHotspots(signal?: AbortSignal): Promise<InpeHotspotCollection> {
  const response = await fetch(INPE_HOTSPOTS_URL, { signal })

  if (!response.ok) {
    throw new Error(`Não foi possível carregar os focos do INPE (${response.status}).`)
  }

  let payload: unknown

  try {
    payload = await response.json()
  } catch {
    throw new Error('O arquivo de focos do INPE não contém JSON válido.')
  }

  assertValidHotspotCollection(payload)
  return payload
}
