"""Geometria usada pelas observações climáticas da aplicação v4."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import rasterio


@dataclass(frozen=True)
class GradeRaster:
    n_lin: int
    n_col: int
    lon0: float
    lat0: float
    passo: float


def ler_grade(caminho: str) -> GradeRaster:
    """Lê apenas metadados de uma grade geográfica quadrada, norte-acima."""
    with rasterio.open(caminho) as source:
        affine = source.transform
        if (source.crs.to_epsg() != 4326 or affine.b != 0 or affine.d != 0
                or affine.a <= 0 or affine.e >= 0 or not np.isclose(affine.a, -affine.e)):
            raise ValueError(f"{caminho}: grade climática incompatível.")
        return GradeRaster(source.height, source.width, affine.c, affine.f, affine.a)


def _round(value: float, digits: int = 7) -> float:
    return round(float(value), digits)


def _positions(value: Any) -> Iterable[tuple[float, float]]:
    if isinstance(value, list) and len(value) >= 2 and all(
        isinstance(item, (int, float)) for item in value[:2]
    ):
        yield float(value[0]), float(value[1])
    elif isinstance(value, list):
        for child in value:
            yield from _positions(child)


def geometry_bounds(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    points = list(_positions(geometry["coordinates"]))
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def _equal(a: list[float], b: list[float]) -> bool:
    return abs(a[0] - b[0]) < 1e-12 and abs(a[1] - b[1]) < 1e-12


def _clip_edge(points, inside, intersection):
    if not points:
        return []
    result = []
    previous = points[-1]
    previous_inside = inside(previous)
    for current in points:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                result.append(intersection(previous, current))
            result.append(current)
        elif previous_inside:
            result.append(intersection(previous, current))
        previous, previous_inside = current, current_inside
    return result


def clip_ring(ring: list[list[float]], bounds: tuple[float, float, float, float]):
    west, south, east, north = bounds
    points = [[float(x), float(y)] for x, y, *_ in ring]
    if len(points) > 1 and _equal(points[0], points[-1]):
        points.pop()

    def vertical(a, b, x):
        ratio = 0.0 if abs(b[0] - a[0]) < 1e-14 else (x - a[0]) / (b[0] - a[0])
        return [x, a[1] + ratio * (b[1] - a[1])]

    def horizontal(a, b, y):
        ratio = 0.0 if abs(b[1] - a[1]) < 1e-14 else (y - a[1]) / (b[1] - a[1])
        return [a[0] + ratio * (b[0] - a[0]), y]

    points = _clip_edge(points, lambda p: p[0] >= west, lambda a, b: vertical(a, b, west))
    points = _clip_edge(points, lambda p: p[0] <= east, lambda a, b: vertical(a, b, east))
    points = _clip_edge(points, lambda p: p[1] >= south, lambda a, b: horizontal(a, b, south))
    points = _clip_edge(points, lambda p: p[1] <= north, lambda a, b: horizontal(a, b, north))
    if len(points) < 3:
        return []
    if not _equal(points[0], points[-1]):
        points.append(points[0].copy())
    return [[_round(x), _round(y)] for x, y in points]


def clip_boundary(geometry: dict[str, Any], bounds):
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    clipped = []
    for polygon in polygons:
        exterior = clip_ring(polygon[0], bounds)
        if exterior:
            clipped.append([exterior])
    if not clipped:
        return None
    if len(clipped) == 1:
        return {"type": "Polygon", "coordinates": clipped[0]}
    return {"type": "MultiPolygon", "coordinates": clipped}

