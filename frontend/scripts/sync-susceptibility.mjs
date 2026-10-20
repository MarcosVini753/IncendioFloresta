import { cp, mkdir, rm, stat, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontendRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
)
// A clean Vercel checkout has metadata, but intentionally no multi-GB COGs.
// Never pretend that native pixels are available when only the grid is shipped.
const remoteBase = process.env.RISK_RASTER_BASE_URL?.trim()
const rasterMode =
  process.env.RISK_RASTER_MODE ||
  (remoteBase ? 'remote' : process.env.VERCEL === '1' ? 'aggregated' : 'local')
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
      `Produto v4 ausente, inválido ou incompleto em ${riskRoot}. Para pixels locais, execute incendio/.venv/bin/python incendio/importar_risco_professor_v4.py --year ${path.basename(riskRoot)} com os GeoTIFFs finais. Para publicar sem COGs locais, use RISK_RASTER_MODE=aggregated; para COGs externos, configure RISK_RASTER_BASE_URL (veja frontend/README.md).`,
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
  await cp(source, destination, {
    recursive: true,
    dereference: true,
    filter: (file) =>
      !isRisk ||
      rasterMode === 'local' ||
      path.relative(source, file).split(path.sep)[0] !== 'sectors',
  })
  if (isRisk) {
    const year = Number(path.basename(source))
    await writeFile(
      path.join(destination, 'deployment.json'),
      JSON.stringify(
        {
          schema_version: '1.0',
          year,
          raster_mode: rasterMode,
          raster_base_url:
            rasterMode === 'local'
              ? `/data/risk/v4/${year}/`
              : rasterMode === 'remote'
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
    'Risco publicado somente em grupos de 5 km. Pixels de 30 m indisponíveis: configure RISK_RASTER_BASE_URL para habilitá-los. Nenhum treinamento foi executado.',
  )
else
  console.log(
    `Raster de 30 m: ${rasterMode === 'remote' ? 'servido externamente; confira CORS e HTTP Range na origem' : 'setores locais incluídos'}.`,
  )
