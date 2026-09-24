import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TimeSeriesPoint } from '../../types/fire'

interface TimeSeriesChartProps {
  data: TimeSeriesPoint[]
  selectedDate: string
  title?: string
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`))
}

export function TimeSeriesChart({ data, selectedDate, title }: TimeSeriesChartProps) {
  return (
    <section className="chart-card">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Série temporal</span>
          <h2>{title ?? 'Perigo histórico médio — Acre'}</h2>
        </div>
        <span className="prototype-badge">365 dias reais do produto</span>
      </div>

      <div className="chart-wrapper">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 12, right: 20, bottom: 0, left: -14 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={shortDate} />
            <YAxis domain={[0, 1]} tickFormatter={(value) => Number(value).toFixed(1)} />
            <Tooltip
              labelFormatter={(value) => `Data: ${shortDate(String(value))}`}
              formatter={(value) => [Number(value).toFixed(3), 'Escore relativo']}
            />
            <ReferenceLine x={selectedDate} strokeDasharray="5 5" />
            <Line type="monotone" dataKey="value" stroke="currentColor" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
