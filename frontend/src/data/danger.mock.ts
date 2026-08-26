import { mockCells } from './risk.mock'
import type { TimeSeriesPoint } from '../types/fire'

export const dangerDates = [
  '2026-08-20',
  '2026-08-21',
  '2026-08-22',
  '2026-08-23',
  '2026-08-24',
  '2026-08-25',
  '2026-08-26'
]

export const dangerSeries: TimeSeriesPoint[] = dangerDates.map((date) => ({
  date,
  value:
    mockCells.reduce((sum, cell) => sum + (cell.danger[date] ?? 0), 0) /
    mockCells.length,
}))
