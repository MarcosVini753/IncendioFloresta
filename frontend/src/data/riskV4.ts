import {
  RISK_V4_CLASSES,
  RISK_V4_MODELS,
  type RiskV4Manifest,
  type RiskV4Product,
} from '../types/riskV4'

export const RISK_V4_BASE = '/data/risk/v4/2026/'
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)
const number = (v: unknown): v is number =>
  typeof v === 'number' && Number.isFinite(v)
const score = (v: unknown): v is number => number(v) && v >= 0 && v <= 100
const positive = (v: unknown): v is number =>
  number(v) && Number.isInteger(v) && v > 0
const point = (v: unknown): v is number[] =>
  Array.isArray(v) && v.length === 2 && v.every(number)
const bbox = (v: unknown): v is number[] =>
  Array.isArray(v) &&
  v.length === 4 &&
  v.every(number) &&
  v[0] < v[2] &&
  v[1] < v[3]
const safeFile = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-z-]+\.(json|geojson)$/.test(v)

export function validateRiskV4Manifest(v: unknown): RiskV4Manifest {
  if (
    !record(v) ||
    v.schema_version !== '4.0' ||
    v.product !== 'wildfire_annual_risk' ||
    v.year !== 2026 ||
    v.default_model !== 'random_forest' ||
    v.scenario !== 'AB30C_suave' ||
    typeof v.label !== 'string' ||
    typeof v.generated_at !== 'string' ||
    !Number.isFinite(Date.parse(v.generated_at))
  )
    throw new Error('Manifesto do Risco v4 de 2026 inválido.')
  if (
    !record(v.training) ||
    JSON.stringify(v.training.years) !== '[2016,2025]' ||
    v.training.climate_year !== 2025 ||
    v.training.climate_smoothing !== true ||
    !Array.isArray(v.training.predictors) ||
    v.training.predictors.length !== 13
  )
    throw new Error('Protocolo científico v4 incompatível.')
  const models = v.models
  if (
    !Array.isArray(models) ||
    models.length !== 2 ||
    !RISK_V4_MODELS.every((id) => {
      const model = models.find((m) => record(m) && m.id === id)
      return (
        record(model) &&
        typeof model.label === 'string' &&
        model.value_unit === 'percent' &&
        model.value_property === `value_${id}` &&
        model.percentile_property === `percentile_${id}` &&
        typeof model.value_label === 'string' &&
        model.calibrated === (id === 'random_forest') &&
        (id === 'random_forest'
          ? point(model.calibration)
          : model.calibration === null)
      )
    })
  )
    throw new Error('Modelos ou calibração v4 incompatíveis.')
  if (
    !record(v.percentile) ||
    v.percentile.origin !== 'received_histogram_statewide' ||
    v.percentile.aggregation !== 'mean_of_received_pixel_percentiles' ||
    JSON.stringify(v.percentile.domain) !== '[0,100]'
  )
    throw new Error('Percentis recebidos incompatíveis.')
  if (
    !record(v.representation) ||
    v.representation.grid_size_m !== 5000 ||
    v.representation.grid_crs !== 'EPSG:31979' ||
    v.representation.native_zoom !== 8.5 ||
    v.representation.native_resolution_m !== 30 ||
    v.representation.aggregation !== 'mean' ||
    JSON.stringify(v.classes) !== JSON.stringify(RISK_V4_CLASSES)
  )
    throw new Error('Resolução ou classes v4 incompatíveis.')
  const files = v.files
  if (
    !record(v.counts) ||
    !positive(v.counts.source_pixels) ||
    !positive(v.counts.features) ||
    !positive(v.counts.sectors) ||
    !bbox(v.bounds) ||
    !record(files) ||
    !['grid', 'boundary', 'index'].every((key) => safeFile(files[key]))
  )
    throw new Error('Arquivos ou cobertura v4 inválidos.')
  if (
    !record(v.provenance) ||
    typeof v.provenance.identity !== 'string' ||
    v.provenance.source_values_unchanged !== true
  )
    throw new Error('Proveniência do produto ausente.')
  if (
    !record(v.evaluation) ||
    v.evaluation.target_year_available !== false ||
    v.evaluation.origin !== 'received_professor' ||
    v.evaluation.level !== '30m_fogo' ||
    !record(v.evaluation.historical)
  )
    throw new Error('Avaliação recebida incompatível.')
  for (const model of RISK_V4_MODELS) {
    const rows = v.evaluation.historical[model]
    if (
      !Array.isArray(rows) ||
      rows.length !== 3 ||
      rows.some((row, i) => {
        if (
          !record(row) ||
          row.year !== 2023 + i ||
          row.level !== '30m_fogo' ||
          row.origin !== 'received_professor' ||
          !record(row.metrics)
        )
          return true
        const metrics = row.metrics
        return (
          !positive(metrics.n) ||
          !positive(metrics.positivos) ||
          ![
            'pr_auc',
            'roc_auc',
            'brier',
            'captura_1%',
            'captura_5%',
            'captura_10%',
          ].every(
            (key) =>
              number(metrics[key]) &&
              Number(metrics[key]) >= 0 &&
              Number(metrics[key]) <= 1,
          )
        )
      })
    )
      throw new Error('Série histórica v4 incompleta.')
  }
  return v as unknown as RiskV4Manifest
}

export function validateRiskV4Product(
  manifest: RiskV4Manifest,
  cells: unknown,
  boundary: unknown,
  index: unknown,
): RiskV4Product {
  if (
    !record(cells) ||
    cells.type !== 'FeatureCollection' ||
    !Array.isArray(cells.features) ||
    cells.features.length !== manifest.counts.features
  )
    throw new Error('Grade de 5 km ausente ou incompleta.')
  let count = 0
  const ids = new Set<string>()
  for (const feature of cells.features) {
    if (
      !record(feature) ||
      feature.type !== 'Feature' ||
      !record(feature.geometry) ||
      !['Polygon', 'MultiPolygon'].includes(String(feature.geometry.type)) ||
      !record(feature.properties) ||
      typeof feature.properties.id !== 'string' ||
      ids.has(feature.properties.id)
    )
      throw new Error('Polígono ou identificador agregado inválido.')
    const p = feature.properties
    if (
      p.aggregation !== 'mean' ||
      !point(p.centroid) ||
      !positive(p.n_source_pixels)
    )
      throw new Error('Propriedades agregadas inválidas.')
    for (const model of RISK_V4_MODELS) {
      if (!score(p[`value_${model}`]) || !score(p[`percentile_${model}`]))
        throw new Error('Valor agregado fora de [0,100].')
      let sum = 0
      for (const category of RISK_V4_CLASSES) {
        const share = p[`share_${model}_${category.id}`]
        if (!number(share) || share < 0 || share > 1)
          throw new Error('Distribuição de classes inválida.')
        sum += share
      }
      if (Math.abs(sum - 1) > 1e-7)
        throw new Error('Distribuição de classes incompleta.')
    }
    ids.add(p.id as string)
    count += p.n_source_pixels
  }
  if (count !== manifest.counts.source_pixels)
    throw new Error('A agregação não cobre todos os pixels-fonte.')
  if (
    !record(boundary) ||
    boundary.type !== 'Feature' ||
    !record(boundary.geometry) ||
    !['Polygon', 'MultiPolygon'].includes(String(boundary.geometry.type))
  )
    throw new Error('Limite do Acre inválido.')
  if (
    !record(index) ||
    index.schema_version !== '4.0' ||
    index.year !== 2026 ||
    index.crs !== 'EPSG:4326' ||
    index.sector_size !== 1024 ||
    !positive(index.width) ||
    !positive(index.height) ||
    !Array.isArray(index.transform) ||
    index.transform.length !== 6 ||
    !index.transform.every(number) ||
    index.transform[0] <= 0 ||
    index.transform[4] >= 0 ||
    index.transform[1] !== 0 ||
    index.transform[3] !== 0 ||
    JSON.stringify(index.bands) !==
      JSON.stringify([
        'value_random_forest',
        'percentile_random_forest',
        'value_xgboost',
        'percentile_xgboost',
      ]) ||
    index.valid_pixels !== count ||
    !Array.isArray(index.sectors) ||
    index.sectors.length !== manifest.counts.sectors
  )
    throw new Error('Índice raster v4 inválido.')
  let sourceCount = 0
  const sectorIds = new Set<string>(),
    windows = new Set<string>()
  for (const sector of index.sectors) {
    if (
      !record(sector) ||
      typeof sector.id !== 'string' ||
      sectorIds.has(sector.id) ||
      sector.url !== `sectors/${sector.id}.tif` ||
      !/^AC-V4-R\d{3}C\d{3}$/.test(sector.id) ||
      !bbox(sector.bbox) ||
      !positive(sector.valid_pixels) ||
      !positive(sector.bytes) ||
      sector.bytes > 32 * 1024 * 1024 ||
      !Array.isArray(sector.window) ||
      sector.window.length !== 4 ||
      !sector.window.every(Number.isInteger)
    )
      throw new Error('Setor raster inválido.')
    const [x, y, w, h] = sector.window as number[]
    const windowId = `${x}/${y}`
    if (
      x < 0 ||
      y < 0 ||
      w <= 0 ||
      h <= 0 ||
      w > 1024 ||
      h > 1024 ||
      x % 1024 ||
      y % 1024 ||
      x + w > index.width ||
      y + h > index.height ||
      sector.valid_pixels > w * h ||
      windows.has(windowId)
    )
      throw new Error('Janela raster inválida ou duplicada.')
    sectorIds.add(sector.id)
    windows.add(windowId)
    sourceCount += sector.valid_pixels
  }
  if (sourceCount !== count)
    throw new Error('Setores não cobrem todos os pixels-fonte.')
  return { manifest, cells, boundary, index } as unknown as RiskV4Product
}

async function json(url: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal })
  if (!response.ok || !response.headers.get('content-type')?.includes('json'))
    throw new Error(
      `Produto v4 ausente ou resposta inválida: ${url}. Execute o importador e sincronize os produtos.`,
    )
  return response.json()
}

export async function loadRiskV4(signal?: AbortSignal): Promise<RiskV4Product> {
  const manifest = validateRiskV4Manifest(
    await json(`${RISK_V4_BASE}manifest.json`, signal),
  )
  const [cells, boundary, index] = await Promise.all(
    [manifest.files.grid, manifest.files.boundary, manifest.files.index].map(
      (file) => json(RISK_V4_BASE + file, signal),
    ),
  )
  return validateRiskV4Product(manifest, cells, boundary, index)
}
