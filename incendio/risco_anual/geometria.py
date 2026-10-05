"""Geometria determinística compartilhada com a grade web anterior."""
from __future__ import annotations
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
import numpy as np
import pandas as pd
from .pipeline import geo
BASE = Path(__file__).resolve().parents[1]
LIMITE = BASE / "recursos/limite_acre.geojson"
GRID_STEP = 0.28
WIDTH_M, HEIGHT_M = geo.XG_A, geo.YG_A
MODELS = ("gradboost", "random_forest", "logistic_regression", "fuzzy_knn", "xgboost")
SCENARIOS = ("unico", "regional")
SCORE_COLUMNS = tuple(f"score_{scenario}_{model}" for scenario in SCENARIOS for model in MODELS)

def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _round(value: float, digits: int = 7) -> float:
    return round(float(value), digits)


def carregar_limite() -> dict[str, Any]:
    if not LIMITE.exists():
        raise FileNotFoundError(
            f"Limite ausente: {LIMITE}. Consulte incendio/README.md para obte-lo."
        )
    with LIMITE.open(encoding="utf-8") as stream:
        raw = json.load(stream)
    feature = raw["features"][0] if raw.get("type") == "FeatureCollection" else raw
    geometry = feature.get("geometry")
    if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("O limite versionado do Acre nao contem Polygon/MultiPolygon.")
    return {"type": "Feature", "properties": feature.get("properties", {}), "geometry": geometry}


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

def sector_indices(lon, lat, bounds):
    west, south, east, north = bounds
    columns = np.floor((np.asarray(lon) - west) / GRID_STEP).astype(int)
    rows = np.floor((np.asarray(lat) - south) / GRID_STEP).astype(int)
    max_column = max(math.ceil((east - west) / GRID_STEP) - 1, 0)
    max_row = max(math.ceil((north - south) / GRID_STEP) - 1, 0)
    return np.clip(rows, 0, max_row), np.clip(columns, 0, max_column)


def sector_id(row: int, column: int) -> str:
    return f"AC-R{row + 1:02d}C{column + 1:02d}"

def exportar_agregado(scores: pd.DataFrame, boundary: dict[str, Any], generated_at: str, output: Path, manifest_base: dict):
    bounds = geometry_bounds(boundary["geometry"])
    rows, columns = sector_indices(scores["lon"], scores["lat"], bounds)
    work = scores.copy()
    work["_row"], work["_column"] = rows, columns
    grouped = work.groupby(["_row", "_column"], sort=True)
    features = []
    for (row, column), group in grouped:
        west = bounds[0] + int(column) * GRID_STEP
        south = bounds[1] + int(row) * GRID_STEP
        east = min(west + GRID_STEP, bounds[2])
        north = min(south + GRID_STEP, bounds[3])
        geometry = clip_boundary(boundary["geometry"], (west, south, east, north))
        if geometry is None:
            raise ValueError(f"Setor com celulas-fonte nao intersecta o limite: {row}/{column}")
        properties = {
            "id": sector_id(int(row), int(column)),
            "centroid": [_round(group["lon"].mean()), _round(group["lat"].mean())],
            "n_source_cells": int(len(group)),
            "aggregation": "mean",
        }
        for score in SCORE_COLUMNS:
            properties[score] = _round(group[score].astype(np.float64).mean())
        features.append(
            {"type": "Feature", "id": properties["id"], "properties": properties, "geometry": geometry}
        )

    count = sum(feature["properties"]["n_source_cells"] for feature in features)
    if count != len(scores):
        raise ValueError(f"Agregacao perdeu celulas: soma={count}; fonte={len(scores)}")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    _json_dump(output / "mapa.geojson", {"type": "FeatureCollection", "features": features})
    _json_dump(output / "limite_acre.geojson", boundary)
    manifest = dict(manifest_base)
    manifest.update(
        {
            "representation": {
                "type": "aggregated_grid",
                "step_degrees": GRID_STEP,
                "aggregation": "mean",
                "notice": "Visualizacao agregada; a grade cientifica original possui maior resolucao.",
            },
            "counts": {"source_cells": len(scores), "features": len(features)},
            "bounds": list(map(_round, bounds)),
            "files": {"geojson": "mapa.geojson", "boundary": "limite_acre.geojson"},
        }
    )
    _json_dump(output / "manifest.json", manifest)
    print(f"Produto agregado: {len(features)} features; {count} celulas-fonte -> {output}")
    return features

def exportar_nativo(scores: pd.DataFrame, boundary: dict[str, Any], generated_at: str, output: Path, manifest_base: dict):
    bounds = geometry_bounds(boundary["geometry"])
    rows, columns = sector_indices(scores["lon"], scores["lat"], bounds)
    half_w, half_h = WIDTH_M / 2, HEIGHT_M / 2
    x_values = scores["x_g"].to_numpy(dtype=float)
    y_values = scores["y_g2"].to_numpy(dtype=float)
    corners = []
    for offset_x, offset_y in (
        (-half_w, -half_h),
        (half_w, -half_h),
        (half_w, half_h),
        (-half_w, half_h),
    ):
        corners.append(geo.utm_para_lonlat(x_values + offset_x, y_values + offset_y))
    sectors: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen = set()
    for position, row in enumerate(scores.itertuples(index=False)):
        cell_id = f"AC-Y{int(row.Y)}-X{int(row.X)}"
        if cell_id in seen:
            raise ValueError(f"ID nativo duplicado: {cell_id}")
        seen.add(cell_id)
        sid = sector_id(int(rows[position]), int(columns[position]))
        properties = {
            "id": cell_id,
            "grid_x": int(row.X),
            "grid_y": int(row.Y),
            "region": "oeste" if row.x_g < 337100 else "leste",
            "centroid": [_round(row.lon), _round(row.lat)],
            "aggregation": "none",
        }
        for column in SCORE_COLUMNS:
            properties[column] = _round(getattr(row, column))
        ring = [
            [_round(corner_lon[position]), _round(corner_lat[position])]
            for corner_lon, corner_lat in corners
        ]
        ring.append(ring[0].copy())
        sectors[sid].append(
            {
                "type": "Feature",
                "id": cell_id,
                "properties": properties,
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    if len(seen) != 307_410:
        raise ValueError(f"Grade nativa incompleta: {len(seen)} IDs unicos.")

    if output.exists():
        shutil.rmtree(output)
    sector_dir = output / "sectors"
    sector_dir.mkdir(parents=True)
    index_entries = []
    for sid, features in sorted(sectors.items()):
        file_name = f"{sid}.geojson"
        _json_dump(sector_dir / file_name, {"type": "FeatureCollection", "features": features})
        positions = [point for feature in features for point in _positions(feature["geometry"]["coordinates"])]
        xs, ys = zip(*positions)
        index_entries.append(
            {
                "id": sid,
                "url": f"sectors/{file_name}",
                "bbox": [_round(min(xs)), _round(min(ys)), _round(max(xs)), _round(max(ys))],
                "feature_count": len(features),
            }
        )
    _json_dump(
        output / "index.json",
        {
            "schema_version": "1.0",
            "product": "wildfire_annual_risk_native_index",
            "generated_at": generated_at,
            "crs": "EPSG:4326",
            "sector_step_degrees": GRID_STEP,
            "feature_count": len(seen),
            "sectors": index_entries,
        },
    )
    manifest = dict(manifest_base)
    manifest.update(
        {
            "representation": {
                "type": "native_sharded_grid",
                "aggregation": "none",
                "sector_step_degrees": GRID_STEP,
            },
            "counts": {"source_cells": len(scores), "features": len(seen), "sectors": len(index_entries)},
            "bounds": list(map(_round, bounds)),
            "files": {"index": "index.json"},
        }
    )
    _json_dump(output / "manifest.json", manifest)
    print(f"Produto nativo: {len(seen)} features em {len(index_entries)} setores -> {output}")
