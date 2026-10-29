import { cp, mkdir, rm, stat, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { createHash } from 'node:crypto'

const frontendRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
)
// O repositório inclui os COGs de 2025 e 2026; ambos são publicados por padrão.
const remoteBase = process.env.RISK_RASTER_BASE_URL?.trim()
const rasterMode =
  process.env.RISK_RASTER_MODE ||
  (remoteBase ? 'remote' : 'local')
if (!['local', 'remote', 'aggregated'].includes(rasterMode))
  throw new Error('RISK_RASTER_MODE deve ser local, remote ou aggregated.')
if ((rasterMode === 'remote') !== Boolean(remoteBase))
  throw new Error(
    'Use RISK_RASTER_BASE_URL somente com RISK_RASTER_MODE=remote.',
  )
if (remoteBase) {
  const url = new URL(remoteBase)
  if (
    !['https:', 'http:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error(
      'RISK_RASTER_BASE_URL deve ser uma URL HTTP(S) pública, sem credenciais, query ou fragmento.',
    )
}
const remoteYearBase = (year) =>
  new URL(`${year}/`, `${remoteBase.replace(/\/+$/, '')}/`).href
const products = [
  {
    source: '../incendio/produtos/risco/v4/2025',
    target: 'public/data/risk/v4/2025',
    label: 'risco anual 2025 · professor v4',
  },
  {
    source: '../incendio/produtos/risco/v4/2026',
    target: 'public/data/risk/v4/2026',
    label: 'risco anual 2026 · professor v4',
  },
  {
    source: '../incendio/produtos/clima/v1/2025',
    target: 'public/data/climate/v1/2025',
    label: 'clima histórico 2025',
  },
]

// Preflight all sources before touching generated copies.
for (const product of products) {
  const source = path.resolve(frontendRoot, product.source)
  try {
    if (!(await stat(source)).isDirectory())
      throw new Error('a origem não é um diretório')
  } catch (error) {
    throw new Error(
      `Produto canônico ausente em ${source}. Gere-o antes de iniciar ou compilar o frontend.`,
      { cause: error },
    )
  }
}

// Conferir metadados em todos os modos; no modo local, também todos os setores.
for (const product of products.filter((item) =>
  item.target.includes('/risk/'),
)) {
  const riskRoot = path.resolve(frontendRoot, product.source)
  try {
    const manifest = JSON.parse(
      await readFile(path.join(riskRoot, 'manifest.json'), 'utf8'),
    )
    const index = JSON.parse(
      await readFile(path.join(riskRoot, 'index.json'), 'utf8'),
    )
    if (
      manifest.schema_version !== '4.0' ||
      manifest.year !== Number(path.basename(riskRoot)) ||
      index.year !== manifest.year ||
      !Array.isArray(index.sectors) ||
      !index.sectors.length
    )
      throw new Error('manifesto/índice inválido')
    const summaries = JSON.parse(await readFile(path.join(riskRoot, 'aggregation-stats.json'), 'utf8'))
    const grid = JSON.parse(await readFile(path.join(riskRoot, 'grid.geojson'), 'utf8'))
    if (summaries.schema_version !== '1.0' || summaries.product !== 'risk_v4_aggregation_stats' ||
        summaries.year !== manifest.year || summaries.source_identity !== manifest.provenance?.identity ||
        summaries.counts?.groups !== grid.features.length || summaries.counts?.source_pixels !== index.valid_pixels ||
        !summaries.groups || Object.keys(summaries.groups).length !== grid.features.length ||
        !grid.features.every(({ properties: p }) => summaries.groups[p.id]?.n_source_pixels === p.n_source_pixels))
      throw new Error('estatísticas derivadas incompatíveis')
    for (const name of ['manifest.json', 'index.json', 'grid.geojson']) {
      const hash = createHash('sha256').update(await readFile(path.join(riskRoot, name))).digest('hex')
      if (summaries.input_sha256?.[name] !== hash) throw new Error(`Estatísticas desatualizadas: ${name}`)
    }
    for (const entry of index.sectors) {
      if (
        typeof entry.id !== 'string' ||
        !/^AC-V4-R\d{3}C\d{3}$/.test(entry.id) ||
        entry.url !== `sectors/${entry.id}.tif`
      )
        throw new Error('URL de setor inválida')
      if (rasterMode === 'local') {
        const file = await stat(path.join(riskRoot, entry.url))
        if (!file.isFile() || file.size !== entry.bytes)
          throw new Error(`setor incompleto: ${entry.id}`)
      }
    }
  } catch (error) {
    throw new Error(
      `Produto v4 ausente, inválido ou incompleto em ${riskRoot}. Para pixels locais, execute incendio/.venv/bin/python incendio/importar_risco_professor_v4.py --year ${path.basename(riskRoot)} com os GeoTIFFs finais. Para gerar/atualizar os resumos, execute incendio/.venv/bin/python incendio/risco_anual_v4/exportar_resumos.py --year ${path.basename(riskRoot)}. Para publicar sem COGs locais, use RISK_RASTER_MODE=aggregated; para COGs externos, configure RISK_RASTER_BASE_URL (veja frontend/README.md).`,
      { cause: error },
    )
  }
}
// Only generated copies: remove legacy years from public, never canonical products.
for (const name of ['susceptibility', 'risk', 'climate']) {
  await rm(path.resolve(frontendRoot, 'public/data', name), {
    recursive: true,
    force: true,
  })
}

for (const product of products) {
  const source = path.resolve(frontendRoot, product.source)
  const destination = path.resolve(frontendRoot, product.target)
  try {
    const sourceStat = await stat(source)
    if (!sourceStat.isDirectory())
      throw new Error('a origem não é um diretório')
  } catch (error) {
    throw new Error(
      `Produto canônico ausente em ${source}. Gere-o antes de iniciar ou compilar o frontend.`,
      { cause: error },
    )
  }
  await rm(destination, { recursive: true, force: true })
  await mkdir(path.dirname(destination), { recursive: true })
  const isRisk = product.target.includes('/risk/')
  const year = Number(path.basename(source))
  const productMode = rasterMode
  await cp(source, destination, {
    recursive: true,
    dereference: true,
    filter: (file) =>
      !isRisk ||
      productMode === 'local' ||
      path.relative(source, file).split(path.sep)[0] !== 'sectors',
  })
  if (isRisk) {
    await writeFile(
      path.join(destination, 'deployment.json'),
      JSON.stringify(
        {
          schema_version: '1.0',
          year,
          raster_mode: productMode,
          raster_base_url:
            productMode === 'local'
              ? `/data/risk/v4/${year}/`
              : productMode === 'remote'
                ? remoteYearBase(year)
                : null,
        },
        null,
        2,
      ) + '\n',
    )
  }
  console.log(`Produto de ${product.label} sincronizado em ${destination}`)
}
if (rasterMode === 'aggregated')
  console.warn(
    'Risco 2025/2026 publicado somente em grupos de 5 km por configuração explícita. Nenhum treinamento foi executado.',
  )
else
  console.log(
    `Raster de 30 m em 2025 e 2026: ${rasterMode === 'remote' ? 'servido externamente; confira CORS e HTTP Range na origem' : '208 setores versionados por ano incluídos'}.`,
  )
