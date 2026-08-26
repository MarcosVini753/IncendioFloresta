export type LayerType = 'risk' | 'danger' | 'alert'

export interface MockCell {
  id: string
  name: string
  coordinates: [number, number]
  risk: number
  danger: Record<string, number>
}

export interface TimeSeriesPoint {
  date: string
  value: number
}
