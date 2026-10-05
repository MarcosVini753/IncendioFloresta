import type {
  ClimateGrid,
  ClimateManifest,
  ClimateMatrix,
  ClimateProduct,
  ClimateStats,
  ClimateVariable,
  ScarCollection,
} from '../types/climate'

const BASE_URL = '/data/climate/v1/2025'
const VARIABLES: ClimateVariable[] = ['humidity', 'precipitation']

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function safeFile(value: unknown): value is string {
  return typeof value === 'string' && /^[a-z-]+\.(json|geojson)$/.test(value)
}

export function validateClimateManifest(value: unknown): ClimateManifest {
  if (!record(value) || value.schema_version !== '1.0' || value.product !== 'historical_climate_and_scars'
    || value.year !== 2025 || value.crs !== 'EPSG:4326') {
    throw new Error('Manifesto de clima de 2025 inválido.')
  }
  if (!Array.isArray(value.dates) || value.dates.length !== 365
    || value.dates.some((date, index) => date !== new Date(Date.UTC(2025, 0, index + 1)).toISOString().slice(0, 10))) {
    throw new Error('Calendário diário de 2025 incompleto.')
  }
  if (!Array.isArray(value.cell_order) || value.cell_order.length !== 212
    || value.cell_order.some((id) => typeof id !== 'string')
    || new Set(value.cell_order).size !== 212
    || !Array.isArray(value.n_valid_pixels) || value.n_valid_pixels.length !== 212
    || value.n_valid_pixels.some((count) => !Number.isInteger(count) || count < 0)) {
    throw new Error('Ordem das células ou cobertura climática inválida.')
  }
  if (!Array.isArray(value.bounds) || value.bounds.length !== 4 || !value.bounds.every(finite)
    || value.bounds[0] >= value.bounds[2] || value.bounds[1] >= value.bounds[3]) {
    throw new Error('Limites geográficos climáticos inválidos.')
  }
  const files = value.files
  if (!record(files) || !['grid', 'boundary', ...VARIABLES, 'scars'].every((key) => safeFile(files[key]))) {
    throw new Error('Arquivos do produto climático inválidos.')
  }
  const variables = value.variables
  if (!record(value.grid) || value.grid.step_degrees !== 0.28 || !finite(value.grid.source_step_degrees)
    || !record(value.statistics) || value.statistics.scope !== 'spatial_per_day'
    || !record(variables) || !VARIABLES.every((name) => record(variables[name]) && typeof variables[name].unit === 'string')
    || !record(value.scars) || !Number.isInteger(value.scars.feature_count)) {
    throw new Error('Metadados do produto climático inválidos.')
  }
  return value as unknown as ClimateManifest
}

export function validateClimateGrid(value: unknown, manifest: ClimateManifest): ClimateGrid {
  if (!record(value) || value.type !== 'FeatureCollection' || !Array.isArray(value.features)
    || value.features.length !== manifest.cell_order.length) {
    throw new Error('Grade climática ausente ou incompleta.')
  }
  value.features.forEach((feature, index) => {
    if (!record(feature) || feature.type !== 'Feature' || !record(feature.geometry)
      || !['Polygon', 'MultiPolygon'].includes(String(feature.geometry.type))
      || !record(feature.properties) || feature.properties.id !== manifest.cell_order[index]
      || !Array.isArray(feature.properties.centroid) || feature.properties.centroid.length !== 2
      || !feature.properties.centroid.every(finite)) {
      throw new Error(`Célula climática inválida na posição ${index}.`)
    }
  })
  return value as unknown as ClimateGrid
}

export function validateClimateMatrix(value: unknown, variable: ClimateVariable, manifest: ClimateManifest): ClimateMatrix {
  if (!record(value) || value.variable !== variable || !Array.isArray(value.values)
    || value.values.length !== manifest.dates.length) {
    throw new Error(`Matriz de ${variable} ausente ou incompleta.`)
  }
  value.values.forEach((day, dayIndex) => {
    if (!Array.isArray(day) || day.length !== manifest.cell_order.length) {
      throw new Error(`Matriz de ${variable} incompleta em ${manifest.dates[dayIndex]}.`)
    }
    day.forEach((stats, cellIndex) => {
      if (!Array.isArray(stats) || stats.length !== 3) throw new Error(`Estatísticas inválidas em ${variable}.`)
      if (stats.every((item) => item === null)) return
      if (!stats.every(finite) || !(stats[0] <= stats[1] && stats[1] <= stats[2])
        || (variable === 'humidity' && (stats[0] < 0 || stats[2] > 100))
        || (variable === 'precipitation' && stats[0] < 0)
        || manifest.n_valid_pixels[cellIndex] === 0) {
        throw new Error(`Valor climático inválido em ${manifest.dates[dayIndex]}.`)
      }
    })
  })
  return value as unknown as ClimateMatrix
}

export function validateScarCollection(value: unknown, manifest: ClimateManifest): ScarCollection {
  if (!record(value) || value.type !== 'FeatureCollection' || !Array.isArray(value.features)
    || value.features.length !== manifest.scars.feature_count) {
    throw new Error('Cicatrizes de 2025 ausentes ou incompletas.')
  }
  value.features.forEach((feature) => {
    if (!record(feature) || feature.type !== 'Feature' || !record(feature.geometry)
      || !['Polygon', 'MultiPolygon'].includes(String(feature.geometry.type))
      || !record(feature.properties) || !Number.isInteger(feature.properties.day_of_year)
      || feature.properties.date !== manifest.dates[Number(feature.properties.day_of_year) - 1]
      || !Array.isArray(feature.properties.center) || feature.properties.center.length !== 2
      || !feature.properties.center.every(finite)) {
      throw new Error('Cicatriz com geometria ou data inválida.')
    }
  })
  return value as unknown as ScarCollection
}

function validateBoundary(value: unknown): ClimateProduct['boundary'] {
  if (!record(value) || value.type !== 'Feature' || !record(value.geometry)
    || !['Polygon', 'MultiPolygon'].includes(String(value.geometry.type))) {
    throw new Error('Limite do Acre inválido no produto climático.')
  }
  return value as unknown as ClimateProduct['boundary']
}

async function fetchJson(url: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`Falha ao carregar ${url} (HTTP ${response.status}).`)
  return response.json()
}

export async function loadClimateProduct(signal?: AbortSignal): Promise<ClimateProduct> {
  const manifest = validateClimateManifest(await fetchJson(`${BASE_URL}/manifest.json`, signal))
  const [grid, boundary, humidity, precipitation, scars] = await Promise.all([
    fetchJson(`${BASE_URL}/${manifest.files.grid}`, signal),
    fetchJson(`${BASE_URL}/${manifest.files.boundary}`, signal),
    fetchJson(`${BASE_URL}/${manifest.files.humidity}`, signal),
    fetchJson(`${BASE_URL}/${manifest.files.precipitation}`, signal),
    fetchJson(`${BASE_URL}/${manifest.files.scars}`, signal),
  ])
  return {
    manifest,
    grid: validateClimateGrid(grid, manifest),
    boundary: validateBoundary(boundary),
    humidity: validateClimateMatrix(humidity, 'humidity', manifest),
    precipitation: validateClimateMatrix(precipitation, 'precipitation', manifest),
    scars: validateScarCollection(scars, manifest),
  }
}

export function cellStats(product: ClimateProduct, variable: ClimateVariable, date: string, cellId: string): ClimateStats {
  const day = product.manifest.dates.indexOf(date)
  const cell = product.manifest.cell_order.indexOf(cellId)
  if (day < 0 || cell < 0) return [null, null, null]
  return product[variable].values[day][cell]
}
