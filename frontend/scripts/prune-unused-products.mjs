import { rm } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

// Vite copies public/ wholesale. Remove only this generated build copy;
// scientific files and local public/data/danger remain untouched.
const generatedDanger = fileURLToPath(new URL('../dist/data/danger/', import.meta.url))
await rm(generatedDanger, { recursive: true, force: true })
console.log('Build limitado a Risco e Clima de 2025; arquivos locais de Perigo preservados.')
