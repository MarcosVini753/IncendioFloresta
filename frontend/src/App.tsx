import { useEffect, useMemo, useState } from 'react'
import { FireMap } from './components/Map/FireMap'
import { LayerSelector } from './components/LayerSelector/LayerSelector'
import { TimeSlider } from './components/Timeline/TimeSlider'
import { TimeSeriesChart } from './components/Chart/TimeSeriesChart'
import { CellDetails } from './components/CellDetails/CellDetails'
import { HotspotLayerControl } from './components/HotspotControl/HotspotLayerControl'
import { dangerDates } from './data/danger.mock'
import { loadInpeHotspots } from './data/inpeHotspots'
import { loadPrototypeGrid, type PrototypeGridData } from './data/prototypeGrid'
import type { LayerType, TimeSeriesPoint } from './types/fire'
import type { InpeHotspotCollection } from './types/inpe'

function formatReferenceDate(value: string | undefined) {
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : null
}

export default function App() {
  const [selectedLayer, setSelectedLayer] = useState<LayerType>('risk')
  const [selectedDate, setSelectedDate] = useState(dangerDates[dangerDates.length - 1])
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null)
  const [grid, setGrid] = useState<PrototypeGridData | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [hotspots, setHotspots] = useState<InpeHotspotCollection | null>(null)
  const [showHotspots, setShowHotspots] = useState(true)
  const [hotspotsError, setHotspotsError] = useState<string | null>(null)

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

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    loadInpeHotspots(controller.signal)
      .then((result) => {
        if (!cancelled) setHotspots(result)
      })
      .catch((error: unknown) => {
        if (!cancelled && !(error instanceof DOMException && error.name === 'AbortError')) {
          setHotspotsError(
            error instanceof Error ? error.message : 'Erro ao carregar os focos do INPE.',
          )
        }
      })

    return () => {
      cancelled = true
      controller.abort()
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

  const hotspotReferenceDate = formatReferenceDate(
    hotspots?.metadata.data_referencia ?? hotspots?.features[0]?.properties.data_hora_gmt ?? undefined,
  )

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <span className="eyebrow">Protótipo v0.2</span>
          <h1>Monitoramento de Incêndios Florestais — Acre</h1>
          <p>Índices demonstrativos com sobreposição de focos de calor observados pelo INPE.</p>
        </div>
        <span className="prototype-badge">Índices demonstrativos · focos INPE reais</span>
      </header>

      <div className="map-controls">
        <LayerSelector value={selectedLayer} onChange={setSelectedLayer} />
        <HotspotLayerControl
          checked={showHotspots}
          count={hotspots?.features.length ?? null}
          referenceDate={hotspotReferenceDate}
          loading={!hotspots && !hotspotsError}
          error={hotspotsError}
          onChange={setShowHotspots}
        />
      </div>

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
              hotspots={hotspots}
              showHotspots={showHotspots}
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
