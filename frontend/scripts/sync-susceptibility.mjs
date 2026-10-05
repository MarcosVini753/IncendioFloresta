import { cp, mkdir, rm, stat } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const products = [
  { source: '../incendio/produtos/risco/v1/2025', target: 'public/data/risk/v1/2025', label: 'risco anual 2025' },
  { source: '../incendio/produtos/clima/v1/2025', target: 'public/data/climate/v1/2025', label: 'clima histórico 2025' },
]

// Preflight all sources before touching generated copies.
for (const product of products) {
  const source = path.resolve(frontendRoot, product.source)
  try {
    if (!(await stat(source)).isDirectory()) throw new Error('a origem não é um diretório')
  } catch (error) {
    throw new Error(`Produto canônico ausente em ${source}. Gere-o antes de iniciar ou compilar o frontend.`, { cause: error })
  }
}

// Only generated copies: remove legacy years from public, never canonical products.
for (const name of ['susceptibility', 'risk', 'climate']) {
  await rm(path.resolve(frontendRoot, 'public/data', name), { recursive: true, force: true })
}

for (const product of products) {
  const source = path.resolve(frontendRoot, product.source)
  const destination = path.resolve(frontendRoot, product.target)
  try {
    const sourceStat = await stat(source)
    if (!sourceStat.isDirectory()) throw new Error('a origem não é um diretório')
  } catch (error) {
    throw new Error(`Produto canônico ausente em ${source}. Gere-o antes de iniciar ou compilar o frontend.`, { cause: error })
  }
  await rm(destination, { recursive: true, force: true })
  await mkdir(path.dirname(destination), { recursive: true })
  await cp(source, destination, { recursive: true })
  console.log(`Produto de ${product.label} sincronizado em ${destination}`)
}
