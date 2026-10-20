import { cp, mkdir, rm, stat, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontendRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
)
const products = [
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

// Conferir todos os setores antes de tocar nas cópias geradas.
const riskRoot = path.resolve(frontendRoot, products[0].source)
try {
  const manifest = JSON.parse(
    await readFile(path.join(riskRoot, 'manifest.json'), 'utf8'),
  )
  const index = JSON.parse(
    await readFile(path.join(riskRoot, 'index.json'), 'utf8'),
  )
  if (
    manifest.schema_version !== '4.0' ||
    manifest.year !== 2026 ||
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
    const file = await stat(path.join(riskRoot, entry.url))
    if (!file.isFile() || file.size !== entry.bytes)
      throw new Error(`setor incompleto: ${entry.id}`)
  }
} catch (error) {
  throw new Error(
    'Produto raster v4 ausente ou incompleto. Na raiz, execute incendio/.venv/bin/python incendio/importar_risco_professor_v4.py com os dois GeoTIFFs finais de 2026 disponíveis; depois repita npm run dev/build.',
    { cause: error },
  )
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
  await cp(source, destination, { recursive: true, dereference: true })
  console.log(`Produto de ${product.label} sincronizado em ${destination}`)
}
