import {
  MODEL_SCORE_PROPERTY,
  SUSCEPTIBILITY_MODEL_IDS,
  type AggregatedCellCollection,
  type SusceptibilityModelId,
} from '../types/susceptibility'
import type {
  DangerGridCollection,
  DangerManifest,
  DangerProduct,
  DangerScoreMatrix,
} from '../types/danger'

const PRODUCT_BASE_URL = '/data/danger/v1/2015'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isModelId(value: unknown): value is SusceptibilityModelId {
  return typeof value === 'string' && SUSCEPTIBILITY_MODEL_IDS.includes(value as SusceptibilityModelId)
}

function expectedDates() {
  return Array.from({ length: 365 }, (_, offset) => {
    const date = new Date(Date.UTC(2015, 0, offset + 1))
    return date.toISOString().slice(0, 10)
  })
}

export function validateDangerManifest(value: unknown): DangerManifest {
  if (!isRecord(value) || value.schema_version !== '1.0' || value.product !== 'wildfire_historical_daily_danger') {
    throw new Error('Contrato do produto de perigo histórico não é compatível com o frontend.')
  }
  if (value.crs !== 'EPSG:4326' || value.source_period !== '2015-01-01/2015-12-31') {
    throw new Error('Período ou referência espacial inválida no perigo histórico.')
  }
  const canonicalDates = expectedDates()
  if (!Array.isArray(value.dates) || value.dates.length !== 365 ||
      value.dates.some((date, index) => date !== canonicalDates[index])) {
    throw new Error('O manifesto deve conter os 365 dias contínuos de 2015.')
  }
  if (!Array.isArray(value.cell_order) || value.cell_order.length !== 212 ||
      new Set(value.cell_order).size !== 212 || value.cell_order.some((id) => typeof id !== 'string')) {
    throw new Error('A ordem canônica das 212 células é inválida.')
  }
  if (!isModelId(value.default_model) || typeof value.default_date !== 'string' ||
      !value.dates.includes(value.default_date)) {
    throw new Error('Modelo ou data inicial inválida no manifesto.')
  }
  if (!Array.isArray(value.models) || value.models.length !== 4) {
    throw new Error('O manifesto não descreve os quatro modelos diários.')
  }
  const ids = new Set<string>()
  for (const model of value.models) {
    if (!isRecord(model) || !isModelId(model.id) || typeof model.label !== 'string' ||
        typeof model.file !== 'string' || !isRecord(model.implementation) ||
        typeof model.implementation.backend !== 'string' || ids.has(model.id)) {
      throw new Error('Modelo diário ausente, duplicado ou inválido.')
    }
    ids.add(model.id)
  }
  if (SUSCEPTIBILITY_MODEL_IDS.some((id) => !ids.has(id))) {
    throw new Error('O manifesto precisa conter exatamente os quatro modelos esperados.')
  }
  const fuzzy = value.models.find((model) => isRecord(model) && model.id === 'fuzzy_knn_k29')
  if (!isRecord(fuzzy) || !isRecord(fuzzy.implementation) ||
      fuzzy.implementation.backend !== 'sklearn.neighbors.NearestNeighbors' ||
      fuzzy.implementation.search !== 'exact' || fuzzy.implementation.k !== 29 ||
      fuzzy.implementation.m !== 2) {
    throw new Error('O Fuzzy k-NN precisa declarar busca exata com k=29 e m=2.')
  }
  if (!isRecord(value.counts) || value.counts.dates !== 365 || value.counts.features !== 212 ||
      value.counts.source_cells_per_date !== 307410) {
    throw new Error('Contagens do perigo histórico são inválidas.')
  }
  if (!isRecord(value.value) || value.value.semantics !== 'relative_score' ||
      !isRecord(value.representation) || value.representation.type !== 'aggregated_grid') {
    throw new Error('Semântica ou representação inesperada no perigo histórico.')
  }
  if (!Array.isArray(value.bounds) || value.bounds.length !== 4 || !value.bounds.every(Number.isFinite) ||
      !isRecord(value.files) || typeof value.files.grid !== 'string') {
    throw new Error('Arquivos ou limites ausentes no manifesto de perigo.')
  }
  if (!isRecord(value.provenance) || value.provenance.checkpoint_schema_version !== '1.0' ||
      typeof value.provenance.checkpoint_contract_sha256 !== 'string' ||
      !/^[a-f0-9]{64}$/.test(value.provenance.checkpoint_contract_sha256) ||
      value.provenance.training_rows !== 196455 || !Array.isArray(value.provenance.predictors) ||
      value.provenance.predictors.length !== 44 ||
      value.provenance.predictors.some((predictor) => typeof predictor !== 'string')) {
    throw new Error('A proveniência científica do perigo histórico é inválida.')
  }
  return value as unknown as DangerManifest
}

export function validateDangerGrid(value: unknown, manifest: DangerManifest): DangerGridCollection {
  if (!isRecord(value) || value.type !== 'FeatureCollection' || !Array.isArray(value.features) ||
      value.features.length !== 212) {
    throw new Error('A grade de perigo deve conter exatamente 212 features.')
  }
  let sourceCells = 0
  const order: string[] = []
  for (const feature of value.features) {
    if (!isRecord(feature) || feature.type !== 'Feature' || !isRecord(feature.geometry) ||
        !['Polygon', 'MultiPolygon'].includes(String(feature.geometry.type)) || !isRecord(feature.properties)) {
      throw new Error('Feature inválida na grade de perigo.')
    }
    const properties = feature.properties
    if (typeof properties.id !== 'string' || properties.aggregation !== 'mean' ||
        !Number.isInteger(properties.n_source_cells) || Number(properties.n_source_cells) <= 0 ||
        !Array.isArray(properties.centroid) || properties.centroid.length !== 2 ||
        !properties.centroid.every(Number.isFinite)) {
      throw new Error('Propriedades inválidas na grade de perigo.')
    }
    order.push(properties.id)
    sourceCells += Number(properties.n_source_cells)
  }
  if (sourceCells !== 307410 || order.some((id, index) => id !== manifest.cell_order[index])) {
    throw new Error('A grade não cobre ou não segue a ordem canônica do manifesto.')
  }
  return value as unknown as DangerGridCollection
}

export function validateDangerScores(
  value: unknown,
  model: SusceptibilityModelId,
): DangerScoreMatrix {
  if (!isRecord(value) || value.schema_version !== '1.0' || value.model !== model ||
      !Array.isArray(value.values) || value.values.length !== 365) {
    throw new Error(`Matriz anual ausente ou incompleta para ${model}.`)
  }
  for (const row of value.values) {
    if (!Array.isArray(row) || row.length !== 212 ||
        row.some((score) => typeof score !== 'number' || !Number.isFinite(score) || score < 0 || score > 1)) {
      throw new Error(`Matriz ${model} deve ter forma 365 × 212 e escores em [0,1].`)
    }
  }
  return value as unknown as DangerScoreMatrix
}

async function fetchJson(url: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`Falha ao carregar ${url} (HTTP ${response.status}).`)
  if (!response.headers.get('content-type')?.includes('json')) {
    throw new Error(`Resposta inválida ao carregar ${url}; o produto histórico ainda não está disponível.`)
  }
  return response.json()
}

export async function loadDangerProduct(signal?: AbortSignal): Promise<DangerProduct> {
  const manifest = validateDangerManifest(await fetchJson(`${PRODUCT_BASE_URL}/manifest.json`, signal))
  const [gridRaw, ...matrices] = await Promise.all([
    fetchJson(`${PRODUCT_BASE_URL}/${manifest.files.grid}`, signal),
    ...manifest.models.map((model) => fetchJson(`${PRODUCT_BASE_URL}/${model.file}`, signal)),
  ])
  const grid = validateDangerGrid(gridRaw, manifest)
  const scores = Object.fromEntries(manifest.models.map((model, index) => [
    model.id,
    validateDangerScores(matrices[index], model.id).values,
  ])) as Record<SusceptibilityModelId, number[][]>
  const [west, south, east, north] = manifest.bounds
  return { manifest, grid, scores, bounds: [[west, south], [east, north]] }
}

export function dangerCellsForDate(product: DangerProduct, date: string): AggregatedCellCollection {
  const dateIndex = product.manifest.dates.indexOf(date)
  if (dateIndex < 0) throw new Error(`Data ausente no produto de perigo: ${date}.`)
  return {
    type: 'FeatureCollection',
    features: product.grid.features.map((feature, cellIndex) => ({
      ...feature,
      properties: {
        ...feature.properties,
        ...Object.fromEntries(SUSCEPTIBILITY_MODEL_IDS.map((model) => [
          MODEL_SCORE_PROPERTY[model], product.scores[model][dateIndex][cellIndex],
        ])),
      },
    })) as AggregatedCellCollection['features'],
  }
}

export function dangerSeries(product: DangerProduct, model: SusceptibilityModelId, cellId?: string) {
  const cellIndex = cellId == null ? -1 : product.manifest.cell_order.indexOf(cellId)
  if (cellId != null && cellIndex < 0) throw new Error(`Célula ausente no produto: ${cellId}.`)
  const weights = product.grid.features.map((feature) => feature.properties.n_source_cells)
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0)
  return product.manifest.dates.map((date, dateIndex) => {
    const row = product.scores[model][dateIndex]
    const value = cellIndex >= 0
      ? row[cellIndex]
      : row.reduce((sum, score, index) => sum + score * weights[index], 0) / totalWeight
    return { date, value }
  })
}
