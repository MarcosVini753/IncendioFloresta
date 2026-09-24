import { cp, mkdir, rm, stat } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const products = [
  ['susceptibility', 'suscetibilidade', true],
  ['danger', 'perigo', false],
]

for (const [publicName, canonicalName, required] of products) {
  const source = path.resolve(frontendRoot, `../incendio/produtos/${canonicalName}`)
  const destination = path.resolve(frontendRoot, `public/data/${publicName}`)
  try {
    const sourceStat = await stat(source)
    if (!sourceStat.isDirectory()) throw new Error('a origem não é um diretório')
  } catch (error) {
    if (!required) {
      console.log(`Produto ${canonicalName} ainda não foi gerado; sincronização ignorada.`)
      continue
    }
    throw new Error(
      `Produto canônico ausente em ${source}. Gere-o antes de iniciar ou compilar o frontend.`,
      { cause: error },
    )
  }

  await rm(destination, { recursive: true, force: true })
  await mkdir(path.dirname(destination), { recursive: true })
  await cp(source, destination, { recursive: true })
  console.log(`Produto ${canonicalName} sincronizado em ${destination}`)
}
