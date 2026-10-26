import {
  fromUrl,
  fromArrayBuffer,
  type GeoTIFF,
  type GeoTIFFImage,
} from 'geotiff'
import {
  type RiskV4Index,
  type RiskV4Model,
  type RiskV4Pixel,
  type RiskV4Sector,
} from '../types/riskV4'
import { RISK_DISPLAY_CLASSES } from './riskDisplayPalette'

// O limite também vale para os subpedidos HTTP que o leitor TIFF faz ao
// consultar diretórios e bandas. Liberar a vaga só depois de consumir o corpo.
const fetchOriginal = globalThis.fetch.bind(globalThis)
let transfers = 0
type TransferWaiter = { grant: () => void; cancel: () => void }
const transferQueue: TransferWaiter[] = []

async function acquireTransfer(signal?: AbortSignal | null) {
  signal?.throwIfAborted()
  if (transfers < 4) {
    transfers++
    return
  }
  await new Promise<void>((resolve, reject) => {
    const waiter: TransferWaiter = {
      grant: () => {
        signal?.removeEventListener('abort', waiter.cancel)
        resolve()
      },
      cancel: () => {
        const position = transferQueue.indexOf(waiter)
        if (position >= 0) transferQueue.splice(position, 1)
        reject(new DOMException('Transferência cancelada', 'AbortError'))
      },
    }
    transferQueue.push(waiter)
    signal?.addEventListener('abort', waiter.cancel, { once: true })
  })
}

globalThis.fetch = async (input, init) => {
  const signal =
    init?.signal ?? (input instanceof Request ? input.signal : undefined)
  await acquireTransfer(signal)
  try {
    signal?.throwIfAborted()
    const response = await fetchOriginal(input, init)
    const body = await response.arrayBuffer()
    return new Response(body, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    })
  } finally {
    const next = transferQueue.shift()
    if (next) next.grant()
    else transfers--
  }
}

type Job =
  | {
      id: number
      type: 'tile'
      model: RiskV4Model
      z: number
      x: number
      y: number
    }
  | { id: number; type: 'query'; lon: number; lat: number }
type Command =
  | Job
  | { type: 'init'; index: RiskV4Index; base: string }
  | { type: 'cancel'; id: number }
const channel = globalThis as unknown as {
  postMessage: (value: unknown, transfer?: Transferable[]) => void
  onmessage: (event: MessageEvent<Command>) => void
}
let index: RiskV4Index
let base = ''
const sectorByWindow = new Map<string, RiskV4Sector>()
const readers = new Map<string, Promise<GeoTIFF>>()
const blocks = new Map<string, Float32Array>()
let cacheBytes = 0
const CACHE_LIMIT = 128 * 1024 * 1024
const active = new Map<number, AbortController>()
const queue: Job[] = []
const colors = RISK_DISPLAY_CLASSES.map((category) =>
  category.color.match(/\w{2}/g)!.map((value) => parseInt(value, 16)),
)

function aborted(signal: AbortSignal) {
  signal.throwIfAborted()
}

async function reader(entry: RiskV4Sector) {
  let pending = readers.get(entry.id)
  if (!pending) {
    // Os setores têm no máximo 1024² × 4 Float32. Servidores sem Range podem
    // responder com o setor completo, nunca com um GeoTIFF de todo o estado.
    pending = (async () => {
      const url = new URL(entry.url, base).href
      const response = await fetch(url, { headers: { Range: 'bytes=0-16383' } })
      if (!response.ok)
        throw new Error(`Falha HTTP ${response.status} no setor ${entry.id}.`)
      if (response.status === 206) {
        await response.arrayBuffer()
        // O cache de blocos decodificados é controlado abaixo. O BlockedSource
        // opcional do GeoTIFF.js compartilha leituras e aborts entre tiles e
        // pode invalidar uma leitura ainda ativa durante pan/zoom rápido.
        const options = { allowFullFile: false, cache: false }
        return fromUrl(url, options)
      }
      const data = await response.arrayBuffer()
      if (data.byteLength !== entry.bytes || data.byteLength > 32 * 1024 * 1024)
        throw new Error(`Setor completo inválido: ${entry.id}.`)
      return fromArrayBuffer(data)
    })()
    readers.set(entry.id, pending)
    void pending.catch(() => {
      if (readers.get(entry.id) === pending) readers.delete(entry.id)
    })
  }
  readers.delete(entry.id)
  readers.set(entry.id, pending)
  while (readers.size > 32) {
    const oldest = readers.keys().next().value!
    readers.delete(oldest)
    for (const [key, pixels] of blocks)
      if (key.startsWith(`${oldest}/`)) {
        cacheBytes -= pixels.byteLength
        blocks.delete(key)
      }
  }
  return pending
}

async function block(
  entry: RiskV4Sector,
  level: number,
  image: GeoTIFFImage,
  bx: number,
  by: number,
  signal: AbortSignal,
) {
  aborted(signal)
  const key = `${entry.id}/${level}/${bx}/${by}`
  const existing = blocks.get(key)
  if (existing) {
    blocks.delete(key)
    blocks.set(key, existing)
    return existing
  }
  const window = [
    bx * 256,
    by * 256,
    Math.min((bx + 1) * 256, image.getWidth()),
    Math.min((by + 1) * 256, image.getHeight()),
  ]
  const pixels = (await image.readRasters({
    window,
    samples: [0, 1, 2, 3],
    interleave: true,
    signal,
  })) as Float32Array
  aborted(signal)
  // Um setor pode sair do LRU enquanto a decodificação está em andamento.
  // Nesse caso, entregar o resultado sem reintroduzir um 33º setor no cache.
  if (!readers.has(entry.id)) return pixels
  // Requisições concorrentes podem decodificar o mesmo bloco. Contabilizar só
  // a cópia que permanece no LRU e não reter promessas abortadas.
  const previous = blocks.get(key)
  if (previous) cacheBytes -= previous.byteLength
  blocks.set(key, pixels)
  cacheBytes += pixels.byteLength
  while (cacheBytes > CACHE_LIMIT && blocks.size) {
    const oldest = blocks.keys().next().value!
    cacheBytes -= blocks.get(oldest)!.byteLength
    blocks.delete(oldest)
  }
  return pixels
}

function locate(lon: number, lat: number) {
  const [a, , c, , , f] = index.transform
  const e = index.transform[4]
  const column = Math.floor((lon - c) / a),
    row = Math.floor((lat - f) / e)
  if (column < 0 || row < 0 || column >= index.width || row >= index.height)
    return null
  const entry = sectorByWindow.get(
    `${Math.floor(column / 1024) * 1024}/${Math.floor(row / 1024) * 1024}`,
  )
  return entry ? { entry, column, row } : null
}

async function query(
  lon: number,
  lat: number,
  signal: AbortSignal,
): Promise<RiskV4Pixel | null> {
  const position = locate(lon, lat)
  if (!position) return null
  const { entry, row, column } = position
  const tif = await reader(entry)
  aborted(signal)
  const image = await tif.getImage(0) // Consulta sempre a resolução original.
  const x = column - entry.window[0],
    y = row - entry.window[1]
  const bx = Math.floor(x / 256),
    by = Math.floor(y / 256)
  const pixels = await block(entry, 0, image, bx, by, signal)
  const width = Math.min(256, image.getWidth() - bx * 256)
  const offset = ((y - by * 256) * width + x - bx * 256) * 4
  const values = Array.from(pixels.subarray(offset, offset + 4))
  if (
    values.length !== 4 ||
    values.some((v) => !Number.isFinite(v) || v < 0 || v > 100)
  )
    return null
  const [a, , c, , , f] = index.transform,
    e = index.transform[4]
  const west = c + column * a,
    east = west + a,
    north = f + row * e,
    south = north + e
  return {
    id: `AC-V4-Y${row}-X${column}`,
    row,
    column,
    centroid: [(west + east) / 2, (south + north) / 2],
    bbox: [west, south, east, north],
    value_random_forest: values[0],
    percentile_random_forest: values[1],
    value_xgboost: values[2],
    percentile_xgboost: values[3],
  }
}

const tileLat = (y: number, n: number) =>
  (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / n))) * 180) / Math.PI

async function tile(job: Extract<Job, { type: 'tile' }>, signal: AbortSignal) {
  const { z, x, y, model } = job
  const n = 2 ** z,
    west = (x / n) * 360 - 180,
    east = ((x + 1) / n) * 360 - 180
  const north = tileLat(y, n),
    south = tileLat(y + 1, n)
  const rgba = new Uint8ClampedArray(256 * 256 * 4)
  const groups = new Map<
    string,
    { entry: RiskV4Sector; pixels: [number, number, number][] }
  >()
  for (let py = 0; py < 256; py++) {
    // Cada linha é convertida de Web Mercator para latitude. Uma interpolação
    // linear entre north/south deslocaria os pixels no mapa.
    const lat = tileLat(y + (py + 0.5) / 256, n)
    for (let px = 0; px < 256; px++) {
      const lon = west + ((px + 0.5) / 256) * (east - west)
      const position = locate(lon, lat)
      if (!position) continue
      let group = groups.get(position.entry.id)
      if (!group) {
        group = { entry: position.entry, pixels: [] }
        groups.set(position.entry.id, group)
      }
      group.pixels.push([py * 256 + px, lon, lat])
    }
  }
  for (const { entry, pixels } of groups.values()) {
    aborted(signal)
    const tif = await reader(entry)
    const imageCount = await tif.getImageCount()
    const desired =
      Math.min((east - west) / 256, (north - south) / 256) / index.transform[0]
    const level = Math.max(
      0,
      Math.min(imageCount - 1, Math.floor(Math.log2(Math.max(1, desired)))),
    )
    const image = await tif.getImage(level)
    const rx = (entry.bbox[2] - entry.bbox[0]) / image.getWidth(),
      ry = (entry.bbox[3] - entry.bbox[1]) / image.getHeight()
    const pieces = new Map<
      string,
      { bx: number; by: number; pixels: [number, number, number][] }
    >()
    for (const [target, lon, lat] of pixels) {
      const sx = Math.max(
        0,
        Math.min(image.getWidth() - 1, Math.floor((lon - entry.bbox[0]) / rx)),
      )
      const sy = Math.max(
        0,
        Math.min(image.getHeight() - 1, Math.floor((entry.bbox[3] - lat) / ry)),
      )
      const bx = Math.floor(sx / 256),
        by = Math.floor(sy / 256),
        key = `${bx}/${by}`
      let piece = pieces.get(key)
      if (!piece) {
        piece = { bx, by, pixels: [] }
        pieces.set(key, piece)
      }
      piece.pixels.push([target, sx, sy])
    }
    for (const piece of pieces.values()) {
      const data = await block(entry, level, image, piece.bx, piece.by, signal)
      const width = Math.min(256, image.getWidth() - piece.bx * 256)
      for (const [target, sx, sy] of piece.pixels) {
        const source = ((sy - piece.by * 256) * width + sx - piece.bx * 256) * 4
        const value = data[source + (model === 'random_forest' ? 1 : 3)]
        if (!Number.isFinite(value) || value < 0 || value > 100) continue
        const category =
          value < 50 ? 0 : value < 70 ? 1 : value < 90 ? 2 : value < 95 ? 3 : 4
        rgba.set([...colors[category], 255], target * 4)
      }
    }
  }
  aborted(signal)
  const canvas = new OffscreenCanvas(256, 256)
  canvas.getContext('2d')!.putImageData(new ImageData(rgba, 256, 256), 0, 0)
  const png = await canvas.convertToBlob({ type: 'image/png' })
  return png.arrayBuffer()
}

function pump() {
  while (active.size < 4 && queue.length) {
    const job = queue.shift()!
    const controller = new AbortController()
    active.set(job.id, controller)
    void (
      job.type === 'tile'
        ? tile(job, controller.signal)
        : query(job.lon, job.lat, controller.signal)
    )
      .then((result) => {
        if (!controller.signal.aborted)
          channel.postMessage(
            { id: job.id, result },
            result instanceof ArrayBuffer ? [result] : [],
          )
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          channel.postMessage({
            id: job.id,
            error:
              error instanceof Error
                ? error.message
                : 'Falha ao ler o setor raster.',
          })
      })
      .finally(() => {
        active.delete(job.id)
        pump()
      })
  }
}

channel.onmessage = ({ data }) => {
  if (data.type === 'init') {
    index = data.index
    base = data.base
    for (const entry of index.sectors)
      sectorByWindow.set(`${entry.window[0]}/${entry.window[1]}`, entry)
  } else if (data.type === 'cancel') {
    active.get(data.id)?.abort()
    const position = queue.findIndex((job) => job.id === data.id)
    if (position >= 0) queue.splice(position, 1)
  } else {
    queue.push(data)
    pump()
  }
}
