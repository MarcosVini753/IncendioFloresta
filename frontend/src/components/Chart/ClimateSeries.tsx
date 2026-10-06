import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ClimateProduct, ClimateVariable } from '../../types/climate'

interface Props {
  product: ClimateProduct
  variable: ClimateVariable
  date: string
  cellId: string | null
}

export function ClimateSeries({ product, variable, date, cellId }: Props) {
  const cell = product.manifest.cell_order.indexOf(cellId ?? '')
  if (cell < 0) return null
  const data = product.manifest.dates.map((day, index) => {
    const [min, mean, max] = product[variable].values[index][cell]
    return { date: day, min, mean, max }
  })
  const unit = product.manifest.variables[variable].unit
  return <section className="chart-card" aria-label="Série climática anual">
    <div className="section-heading"><div><span className="eyebrow">365 dias observados</span>
      <h2>{variable === 'humidity' ? 'Umidade relativa' : 'Precipitação do produto'} — {cellId} · 2025</h2>
    </div></div>
    <p>Estatísticas espaciais por dia ({unit}); lacunas indicam ausência de dados.</p>
    <div className="chart-wrapper"><ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 12, right: 20, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" tickFormatter={(value: string) => value.slice(5).split('-').reverse().join('/')} minTickGap={40} />
        <YAxis domain={variable === 'humidity' ? [0, 100] : [0, 'auto']} unit={unit} />
        <Tooltip labelFormatter={(value) => String(value).split('-').reverse().join('/')} />
        <Legend />
        <ReferenceLine x={date} stroke="#173f32" strokeDasharray="5 5" />
        <Line type="linear" dataKey="min" name="Mínimo espacial" stroke="#4279a0" dot={false} isAnimationActive={false} />
        <Line type="linear" dataKey="mean" name="Média espacial ponderada" stroke="#173f32" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line type="linear" dataKey="max" name="Máximo espacial" stroke="#bb6336" dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer></div>
  </section>
}
