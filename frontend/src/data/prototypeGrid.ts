import type {
  Feature,
  FeatureCollection,
  MultiPolygon,
  Polygon,
  Position,
} from 'geojson'
import { dangerDates } from './danger.mock'
import type { CellGeometry, PrototypeCell } from '../types/fire'

const ACRE_BOUNDARY_URL =
  'https://raw.githubusercontent.com/giuliano-macedo/geodata-br-states/main/geojson/br_states/br_ac.json'

const GRID_STEP_DEGREES = 0.28

type Coordinate = [number, number]
type Bounds = [[number, number], [number, number]]
type CellBounds = [number, number, number, number]

export interface PrototypeGridData {
  boundary: Feature<Polygon | MultiPolygon>
  bounds: Bounds
  cells: PrototypeCell[]
}

function clamp(value: number, min = 0, max = 1) {
  return Math.min(max, Math.max(min, value))
}

function roundIndex(value: number) {
  return Math.round(value * 100) / 100
}

function deterministicUnit(id: string, salt = 0) {
  let hash = 2166136261 ^ salt

  for (let index = 0; index < id.length; index += 1) {
    hash ^= id.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }

  hash ^= hash >>> 13
  hash = Math.imul(hash, 2246822519)
  hash ^= hash >>> 16

  return (hash >>> 0) / 4294967295
}

function buildDangerSeries(id: string, risk: number) {
  const temporalProfile = [0.32, 0.38, 0.47, 0.56, 0.65, 0.72, 0.68]

  return Object.fromEntries(
    dangerDates.map((date, index) => {
      const localVariation = deterministicUnit(id, index + 31) - 0.5
      const value = clamp(
        0.08 + risk * 0.43 + temporalProfile[index] * 0.4 + localVariation * 0.16,
      )

      return [date, roundIndex(value)]
    }),
  )
}

function getGeometryBounds(geometry: Polygon | MultiPolygon): Bounds {
  let minX = Number.POSITIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  let maxX = Number.NEGATIVE_INFINITY
  let maxY = Number.NEGATIVE_INFINITY

  function visit(value: unknown) {
    if (!Array.isArray(value)) return

    if (
      value.length >= 2 &&
      typeof value[0] === 'number' &&
      typeof value[1] === 'number'
    ) {
      const [x, y] = value as Position
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x)
      maxY = Math.max(maxY, y)
      return
    }

    value.forEach(visit)
  }

  visit(geometry.coordinates)

  return [
    [minX, minY],
    [maxX, maxY],
  ]
}

function coordinatesEqual(a: Coordinate, b: Coordinate) {
  return Math.abs(a[0] - b[0]) < 1e-10 && Math.abs(a[1] - b[1]) < 1e-10
}

function openRing(ring: Position[]): Coordinate[] {
  const points = ring.map(([x, y]) => [x, y] as Coordinate)

  if (points.length > 1 && coordinatesEqual(points[0], points[points.length - 1])) {
    points.pop()
  }

  return points
}

function closeRing(points: Coordinate[]): Coordinate[] {
  if (points.length < 3) return []

  const result = [...points]
  if (!coordinatesEqual(result[0], result[result.length - 1])) {
    result.push([...result[0]] as Coordinate)
  }

  return result
}

function clipAgainstEdge(
  input: Coordinate[],
  inside: (point: Coordinate) => boolean,
  intersection: (from: Coordinate, to: Coordinate) => Coordinate,
) {
  if (input.length === 0) return input

  const output: Coordinate[] = []
  let previous = input[input.length - 1]
  let previousInside = inside(previous)

  for (const current of input) {
    const currentInside = inside(current)

    if (currentInside) {
      if (!previousInside) output.push(intersection(previous, current))
      output.push(current)
    } else if (previousInside) {
      output.push(intersection(previous, current))
    }

    previous = current
    previousInside = currentInside
  }

  return output
}

function intersectVertical(from: Coordinate, to: Coordinate, x: number): Coordinate {
  const deltaX = to[0] - from[0]
  if (Math.abs(deltaX) < 1e-12) return [x, from[1]]

  const ratio = (x - from[0]) / deltaX
  return [x, from[1] + ratio * (to[1] - from[1])]
}

function intersectHorizontal(from: Coordinate, to: Coordinate, y: number): Coordinate {
  const deltaY = to[1] - from[1]
  if (Math.abs(deltaY) < 1e-12) return [from[0], y]

  const ratio = (y - from[1]) / deltaY
  return [from[0] + ratio * (to[0] - from[0]), y]
}

function clipRingToBounds(ring: Position[], bounds: CellBounds) {
  const [west, south, east, north] = bounds
  let points = openRing(ring)

  points = clipAgainstEdge(
    points,
    ([x]) => x >= west,
    (from, to) => intersectVertical(from, to, west),
  )
  points = clipAgainstEdge(
    points,
    ([x]) => x <= east,
    (from, to) => intersectVertical(from, to, east),
  )
  points = clipAgainstEdge(
    points,
    ([, y]) => y >= south,
    (from, to) => intersectHorizontal(from, to, south),
  )
  points = clipAgainstEdge(
    points,
    ([, y]) => y <= north,
    (from, to) => intersectHorizontal(from, to, north),
  )

  return closeRing(points)
}

function clipBoundaryToCell(
  geometry: Polygon | MultiPolygon,
  bounds: CellBounds,
): CellGeometry | null {
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates
  const clippedPolygons: Coordinate[][][] = []

  for (const polygon of polygons) {
    const exteriorRing = polygon[0]
    if (!exteriorRing) continue

    const clippedRing = clipRingToBounds(exteriorRing, bounds)
    if (clippedRing.length >= 4) clippedPolygons.push([clippedRing])
  }

  if (clippedPolygons.length === 0) return null

  if (clippedPolygons.length === 1) {
    return {
      type: 'Polygon',
      coordinates: clippedPolygons[0],
    }
  }

  return {
    type: 'MultiPolygon',
    coordinates: clippedPolygons,
  }
}

function ringCentroid(ring: Position[]): { centroid: Coordinate; area: number } {
  let areaTwice = 0
  let centroidX = 0
  let centroidY = 0

  for (let index = 0; index < ring.length - 1; index += 1) {
    const [x1, y1] = ring[index]
    const [x2, y2] = ring[index + 1]
    const cross = x1 * y2 - x2 * y1
    areaTwice += cross
    centroidX += (x1 + x2) * cross
    centroidY += (y1 + y2) * cross
  }

  if (Math.abs(areaTwice) < 1e-12) {
    const points = ring.slice(0, -1)
    const sum = points.reduce(
      (accumulator, [x, y]) => [accumulator[0] + x, accumulator[1] + y] as Coordinate,
      [0, 0] as Coordinate,
    )

    return {
      centroid: [sum[0] / points.length, sum[1] / points.length],
      area: 0,
    }
  }

  return {
    centroid: [centroidX / (3 * areaTwice), centroidY / (3 * areaTwice)],
    area: Math.abs(areaTwice / 2),
  }
}

function geometryCentroid(geometry: CellGeometry): Coordinate {
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates
  let best: { centroid: Coordinate; area: number } | null = null

  for (const polygon of polygons) {
    const result = ringCentroid(polygon[0])
    if (!best || result.area > best.area) best = result
  }

  return best?.centroid ?? [0, 0]
}

function createPrototypeCells(boundary: Feature<Polygon | MultiPolygon>, bounds: Bounds) {
  const [[minX, minY], [maxX, maxY]] = bounds
  const cells: PrototypeCell[] = []
  let row = 0

  for (let south = minY; south < maxY; south += GRID_STEP_DEGREES) {
    let column = 0

    for (let west = minX; west < maxX; west += GRID_STEP_DEGREES) {
      const east = Math.min(west + GRID_STEP_DEGREES, maxX)
      const north = Math.min(south + GRID_STEP_DEGREES, maxY)
      const geometry = clipBoundaryToCell(boundary.geometry, [west, south, east, north])

      if (geometry) {
        const id = `AC-R${String(row + 1).padStart(2, '0')}C${String(column + 1).padStart(2, '0')}`
        const risk = roundIndex(0.12 + deterministicUnit(id, 11) * 0.82)

        cells.push({
          id,
          centroid: geometryCentroid(geometry),
          geometry,
          risk,
          danger: buildDangerSeries(id, risk),
        })
      }

      column += 1
    }

    row += 1
  }

  return cells
}

export async function loadPrototypeGrid(): Promise<PrototypeGridData> {
  const response = await fetch(ACRE_BOUNDARY_URL)

  if (!response.ok) {
    throw new Error(`Não foi possível carregar o limite do Acre (${response.status}).`)
  }

  const collection = (await response.json()) as FeatureCollection<Polygon | MultiPolygon>
  const boundary = collection.features[0]

  if (!boundary || (boundary.geometry.type !== 'Polygon' && boundary.geometry.type !== 'MultiPolygon')) {
    throw new Error('A fonte geográfica do Acre não retornou um polígono válido.')
  }

  const bounds = getGeometryBounds(boundary.geometry)
  const cells = createPrototypeCells(boundary, bounds)

  return {
    boundary,
    bounds,
    cells,
  }
}
