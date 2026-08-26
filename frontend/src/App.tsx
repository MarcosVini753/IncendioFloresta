import { useState } from 'react'
import { FireMap } from './components/Map/FireMap'
import { LayerSelector } from './components/LayerSelector/LayerSelector'
import { TimeSlider } from './components/Timeline/TimeSlider'
import { TimeSeriesChart } from './components/Chart/TimeSeriesChart'
import { dangerDates, dangerSeries } from './data/danger.mock'
import type { LayerType } from './types/fire'

export default function App() {
  const [selectedLayer, setSelectedLayer] = useState<LayerType>('risk')
  const [selectedDate, setSelectedDate] = useState(dangerDates[dangerDates.length - 1])

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <span className="eyebrow">Protótipo v0.1</span>
          <h1>Monitoramento de Incêndios Florestais — Acre</h1>
          <p>Exploração inicial da visualização espacial e temporal de risco e perigo.</p>
        </div>
        <span className="prototype-badge">Dados demonstrativos</span>
      </header>

      <LayerSelector value={selectedLayer} onChange={setSelectedLayer} />

      <section className="map-section">
        <FireMap layer={selectedLayer} selectedDate={selectedDate} />
      </section>

      {selectedLayer === 'danger' ? (
        <div className="temporal-grid">
          <TimeSlider dates={dangerDates} selectedDate={selectedDate} onChange={setSelectedDate} />
          <TimeSeriesChart data={dangerSeries} selectedDate={selectedDate} />
        </div>
      ) : (
        <section className="static-risk-note">
          <span className="eyebrow">Risco</span>
          <strong>Camada estática no protótipo</strong>
          <p>
            A navegação diária é exibida apenas para Perigo. Futuramente o Risco poderá ser associado a versões da base geográfica, não a uma série diária.
          </p>
        </section>
      )}
    </main>
  )
}
