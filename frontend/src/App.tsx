import { useEffect, useMemo, useState } from 'react'
import { FireMap } from './components/Map/FireMap'
import { LayerSelector } from './components/LayerSelector/LayerSelector'
import { TimeSlider } from './components/Timeline/TimeSlider'
import { TimeSeriesChart } from './components/Chart/TimeSeriesChart'
import { CellDetails } from './components/CellDetails/CellDetails'
import { dangerDates } from './data/danger.mock'
import { loadPrototypeGrid, type PrototypeGridData } from './data/prototypeGrid'
import type { LayerType, TimeSeriesPoint } from './types/fire'

export default function App() {
  const [selectedLayer, setSelectedLayer] = useState<LayerType>('risk')
  const [selectedDate, setSelectedDate] = useState(dangerDates[dangerDates.length - 1])
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null)
  const [grid, setGrid] = useState<PrototypeGridData | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    loadPrototypeGrid()
      .then((result) => {
        if (!cancelled) setGrid(result)
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : 'Erro ao carregar a malha demonstrativa.')
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const selectedCell = useMemo(
    () => grid?.cells.find((cell) => cell.id === selectedCellId) ?? null,
    [grid, selectedCellId],
  )

  const dangerSeries = useMemo<TimeSeriesPoint[]>(() => {
    if (!grid) return []

    if (selectedCell) {
      return dangerDates.flatMap((date) => {
        const value = selectedCell.danger[date]
        return value == null ? [] : [{ date, value }]
      })
    }

    return dangerDates.map((date) => {
      const values = grid.cells
        .map((cell) => cell.danger[date])
        .filter((value): value is number => value != null)

      return {
        date,
        value: values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1),
      }
    })
  }, [grid, selectedCell])

  const chartTitle = selectedCell
    ? `Perigo demonstrativo — ${selectedCell.id}`
    : 'Perigo médio demonstrativo — Acre'

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <span className="eyebrow">Protótipo v0.2</span>
          <h1>Monitoramento de Incêndios Florestais — Acre</h1>
          <p>Exploração inicial da visualização espacial e temporal de risco e perigo.</p>
        </div>
        <span className="prototype-badge">Dados demonstrativos</span>
      </header>

      <LayerSelector value={selectedLayer} onChange={setSelectedLayer} />

      {grid ? (
        <section className="map-workspace">
          <div className="map-section">
            <FireMap
              layer={selectedLayer}
              selectedDate={selectedDate}
              cells={grid.cells}
              boundary={grid.boundary}
              bounds={grid.bounds}
              selectedCellId={selectedCellId}
              onCellSelect={setSelectedCellId}
            />
          </div>
          <CellDetails
            cell={selectedCell}
            layer={selectedLayer}
            selectedDate={selectedDate}
            onClear={() => setSelectedCellId(null)}
          />
        </section>
      ) : (
        <section className="map-section">
          <div className="map-shell map-status" role="status">
            {loadError ? (
              <>
                <strong>Não foi possível carregar a malha.</strong>
                <span>{loadError}</span>
              </>
            ) : (
              <>
                <strong>Preparando a malha demonstrativa do Acre…</strong>
                <span>Carregando o limite geográfico e construindo as células do protótipo.</span>
              </>
            )}
          </div>
        </section>
      )}

      {selectedLayer === 'danger' && grid ? (
        <div className="temporal-grid">
          <TimeSlider dates={dangerDates} selectedDate={selectedDate} onChange={setSelectedDate} />
          <TimeSeriesChart data={dangerSeries} selectedDate={selectedDate} title={chartTitle} />
        </div>
      ) : selectedLayer === 'risk' ? (
        <section className="static-risk-note">
          <span className="eyebrow">Risco</span>
          <strong>Camada estática no protótipo</strong>
          <p>
            A navegação diária é exibida apenas para Perigo. A célula selecionada permanece ativa ao alternar entre Risco e Perigo.
          </p>
        </section>
      ) : null}
    </main>
  )
}
