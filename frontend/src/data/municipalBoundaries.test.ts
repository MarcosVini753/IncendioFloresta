import { describe, expect, it } from 'vitest'
import geojsonText from '../../public/data/reference/acre-municipalities.geojson?raw'
import { ACRE_MUNICIPALITY_SEATS } from './acreMunicipalities'
import { MUNICIPAL_GEOJSON_URL, MUNICIPAL_LINE_ID, MUNICIPAL_SOURCE_ID } from './municipalBoundaries'

type Geometry = { type: 'Polygon' | 'MultiPolygon'; coordinates: unknown[] }
type MunicipalFeature = {
  type: 'Feature'
  properties: { id: string; name: string }
  geometry: Geometry
}
const collection = JSON.parse(geojsonText) as {
  type: 'FeatureCollection'
  features: MunicipalFeature[]
}

describe('limites municipais de referência do Acre', () => {
  it('inclui exatamente os 22 municípios e corresponde à busca por sedes', () => {
    expect(collection.type).toBe('FeatureCollection')
    expect(collection.features).toHaveLength(22)
    const ids = collection.features.map((feature) => feature.properties.id)
    expect(new Set(ids).size).toBe(22)
    expect(new Set(ids)).toEqual(new Set(ACRE_MUNICIPALITY_SEATS.map((item) => item.id)))
    expect(collection.features.every((feature) =>
      feature.type === 'Feature' &&
      feature.properties.name.trim().length > 0 &&
      ['Polygon', 'MultiPolygon'].includes(feature.geometry.type),
    )).toBe(true)
  })

  it('possui polígonos dentro da região geográfica esperada, não apenas sedes', () => {
    let count = 0
    for (const feature of collection.features) {
      const visit = (coords: unknown): void => {
        if (!Array.isArray(coords)) throw new Error('Coordenada inválida')
        if (coords.length === 2 && typeof coords[0] === 'number' && typeof coords[1] === 'number') {
          const [lon, lat] = coords
          expect(lon).toBeGreaterThan(-74.5)
          expect(lon).toBeLessThan(-66)
          expect(lat).toBeGreaterThan(-12)
          expect(lat).toBeLessThan(-6.5)
          count += 1
        } else coords.forEach(visit)
      }
      visit(feature.geometry.coordinates)
    }
    expect(count).toBeGreaterThan(300)
  })

  it('registra a URL e as IDs da camada separada do risco', () => {
    expect(MUNICIPAL_GEOJSON_URL).toBe('/data/reference/acre-municipalities.geojson')
    expect(MUNICIPAL_LINE_ID).not.toBe(MUNICIPAL_SOURCE_ID)
    expect(MUNICIPAL_LINE_ID).not.toMatch(/^risk-v4-/)
  })
})
