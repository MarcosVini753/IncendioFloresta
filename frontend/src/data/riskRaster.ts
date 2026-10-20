import type { RiskV4Index, RiskV4Model, RiskV4Pixel } from '../types/riskV4'
import { RISK_V4_BASE } from './riskV4'

export class RiskRasterClient {
  private worker = new Worker(
    new URL('./riskRaster.worker.ts', import.meta.url),
    { type: 'module' },
  )
  private serial = 0
  private pending = new Map<
    number,
    {
      resolve: (result: unknown) => void
      reject: (error: Error) => void
      cleanup: () => void
    }
  >()

  constructor(index: RiskV4Index) {
    this.worker.postMessage({
      type: 'init',
      index,
      base: new URL(RISK_V4_BASE, location.origin).href,
    })
    this.worker.onmessage = ({
      data,
    }: MessageEvent<{ id: number; result?: unknown; error?: string }>) => {
      const job = this.pending.get(data.id)
      if (!job) return
      this.pending.delete(data.id)
      job.cleanup()
      if (data.error) job.reject(new Error(data.error))
      else job.resolve(data.result)
    }
    this.worker.onerror = (event) => {
      this.failAll(
        new Error(event.message || 'O leitor raster não pôde iniciar.'),
      )
    }
  }

  private request<T>(
    data: Record<string, unknown>,
    signal: AbortSignal,
  ): Promise<T> {
    if (signal.aborted)
      return Promise.reject(
        new DOMException('Requisição cancelada', 'AbortError'),
      )
    const id = ++this.serial
    return new Promise<T>((resolve, reject) => {
      const cancel = () => {
        this.worker.postMessage({ type: 'cancel', id })
        this.pending.delete(id)
        signal.removeEventListener('abort', cancel)
        reject(new DOMException('Requisição cancelada', 'AbortError'))
      }
      signal.addEventListener('abort', cancel, { once: true })
      this.pending.set(id, {
        resolve: (result) => resolve(result as T),
        reject,
        cleanup: () => signal.removeEventListener('abort', cancel),
      })
      this.worker.postMessage({ ...data, id })
    })
  }

  tile(
    model: RiskV4Model,
    z: number,
    x: number,
    y: number,
    signal: AbortSignal,
  ) {
    return this.request<ArrayBuffer>({ type: 'tile', model, z, x, y }, signal)
  }

  query(lon: number, lat: number, signal: AbortSignal) {
    return this.request<RiskV4Pixel | null>({ type: 'query', lon, lat }, signal)
  }

  private failAll(error: Error) {
    for (const job of this.pending.values()) {
      job.cleanup()
      job.reject(error)
    }
    this.pending.clear()
  }

  destroy() {
    this.failAll(new DOMException('Leitor encerrado', 'AbortError'))
    this.worker.terminate()
  }
}
