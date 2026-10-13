"""Geometria determinística compartilhada com a grade web anterior."""
from __future__ import annotations
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
from affine import Affine
import numpy as np
import pandas as pd
import rasterio.features
import rasterio.warp
from .pipeline import geo
BASE = Path(__file__).resolve().parents[1]
LIMITE = BASE / "recursos/limite_acre.geojson"
GRID_STEP = 0.28
WIDTH_M, HEIGHT_M = geo.XG_A, geo.YG_A
MODELS = ("gradboost", "random_forest", "logistic_regression", "xgboost")
SCENARIOS = ("todos", "todos_regional", "razao_1x19", "todos_historico")
SCORE_COLUMNS = tuple(f"{kind}_{scenario}_{model}" for kind in ("score", "percentile") for scenario in SCENARIOS for model in MODELS)
PERCENTILE_COLUMNS = tuple(column for column in SCORE_COLUMNS if column.startswith("percentile_"))
VISUAL_CELL_SIZE_M = 5_000
RISK_CLASSES = (
    {"id": "very_low", "label": "Muito baixo", "lower": 0, "upper": 50},
    {"id": "low", "label": "Baixo", "lower": 50, "upper": 70},
    {"id": "moderate", "label": "Moderado", "lower": 70, "upper": 90},
    {"id": "high", "label": "Alto", "lower": 90, "upper": 95},
    {"id": "very_high", "label": "Muito alto", "lower": 95, "upper": 100},
)


def class_share_property(scenario: str, model: str, class_id: str) -> str:
    return f"class_share_{scenario}_{model}_{class_id}"


def _risk_class_ids(percentiles: np.ndarray) -> np.ndarray:
    return np.clip(np.searchsorted([50, 70, 90, 95], percentiles, side="right"), 0, len(RISK_CLASSES) - 1)


def visual_representation():
    return {
        "type": "aggregated_grid",
        "grid_size_m": VISUAL_CELL_SIZE_M,
        "grid_crs": "EPSG:31979",
        "aggregation": "arithmetic_mean",
        "color_statistic": "mean_native_percentile_classified",
        "risk_classes": list(RISK_CLASSES),
        "class_share_semantics": "fraction_of_source_cells_in_each_fixed_percentile_class",
        "area_approximation": "source_cell_count; scientific cells have similar dimensions",
        "notice": "Cada quadrado visual agrega células científicas de cerca de 893 × 598 m. A cor classifica a média dos percentis; a distribuição por classe no clique conta as células-fonte.",
    }

def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _round(value: float, digits: int = 9) -> float:
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
    grouped = scores.copy()
    projected_x = geo.XG_B + grouped["X"].to_numpy(dtype=np.float64) * geo.XG_A
    projected_y = geo.YG_B + grouped["Y"].to_numpy(dtype=np.float64) * geo.YG_A
    grouped["_tile_x"] = np.floor(projected_x / VISUAL_CELL_SIZE_M).astype(np.int32)
    grouped["_tile_y"] = np.floor(projected_y / VISUAL_CELL_SIZE_M).astype(np.int32)
    grouped["_class"] = np.column_stack([_risk_class_ids(np.round(grouped[column].to_numpy(dtype=np.float64), 9)) for column in PERCENTILE_COLUMNS]).tolist()
    features = []
    for (tile_y, tile_x), group in grouped.groupby(["_tile_y", "_tile_x"], sort=True):
        properties = {
            "id": f"AC-5KM-E{int(tile_x):03d}N{int(tile_y):04d}",
            "centroid": [_round(group["lon"].mean()), _round(group["lat"].mean())],
            "n_source_cells": int(len(group)),
            "aggregation": "mean",
        }
        for column in SCORE_COLUMNS:
            properties[column] = _round(group[column].mean())
        classes = np.vstack(group["_class"].to_numpy())
        for pair, percentile_column in enumerate(PERCENTILE_COLUMNS):
            scenario, model = percentile_column.removeprefix("percentile_").rsplit("_", 1)
            counts = np.bincount(classes[:, pair], minlength=len(RISK_CLASSES))
            for index, risk_class in enumerate(RISK_CLASSES):
                properties[class_share_property(scenario, model, risk_class["id"])] = _round(counts[index] / len(group), 8)
        features.append({"type": "Feature", "id": properties["id"], "properties": properties})

    if sum(feature["properties"]["n_source_cells"] for feature in features) != len(scores):
        raise ValueError("Agregação de 5 km perdeu células científicas.")
    geometry_by_id = _visual_geometries(scores)
    for feature in features:
        feature["geometry"] = geometry_by_id[feature["properties"]["id"]]

    bounds = geometry_bounds(boundary["geometry"])
    output.mkdir(parents=True, exist_ok=True)
    _json_dump(output / "mapa.geojson", {"type": "FeatureCollection", "features": features})
    _json_dump(output / "limite_acre.geojson", boundary)
    manifest = dict(manifest_base)
    manifest.update({
        "representation": visual_representation(),
        "counts": {"source_cells": len(scores), "features": len(features)},
        "bounds": list(map(_round, bounds)),
        "files": {"geojson": "mapa.geojson", "boundary": "limite_acre.geojson"},
    })
    _json_dump(output / "manifest.json", manifest)
    print(f"Produto visual: {len(features)} quadrados de ~5 km; {len(scores)} células-fonte.", flush=True)
    return features


def _visual_geometries(scores: pd.DataFrame):
    xs = scores["X"].to_numpy(dtype=np.int32)
    ys = scores["Y"].to_numpy(dtype=np.int32)
    x_min, x_max, y_min, y_max = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    tile_x = np.floor((geo.XG_B + xs.astype(np.float64) * geo.XG_A) / VISUAL_CELL_SIZE_M).astype(np.int32)
    tile_y = np.floor((geo.YG_B + ys.astype(np.float64) * geo.YG_A) / VISUAL_CELL_SIZE_M).astype(np.int32)
    tile_keys = sorted(set(zip(tile_y.tolist(), tile_x.tolist())))
    key_to_id = {key: f"AC-5KM-E{key[1]:03d}N{key[0]:04d}" for key in tile_keys}
    key_to_code = {key: index + 1 for index, key in enumerate(tile_keys)}
    labels = np.zeros((y_max - y_min + 1, x_max - x_min + 1), dtype=np.int32)
    rows = y_max - ys
    columns = xs - x_min
    labels[rows, columns] = [key_to_code[(row, column)] for row, column in zip(tile_y, tile_x)]
    transform = Affine(
        geo.XG_A, 0, geo.XG_B + x_min * geo.XG_A - geo.XG_A / 2,
        0, -geo.YG_A, geo.YG_B + (y_max + 0.5) * geo.YG_A,
    )
    geometries: dict[str, list[dict]] = defaultdict(list)
    for geometry, code in rasterio.features.shapes(labels, mask=labels > 0, transform=transform, connectivity=4):
        geometries[key_to_id[tile_keys[int(code) - 1]]].append(rasterio.warp.transform_geom("EPSG:31979", "EPSG:4326", geometry, precision=9))
    output = {}
    for cell_id, parts in geometries.items():
        output[cell_id] = parts[0] if len(parts) == 1 else {"type": "MultiPolygon", "coordinates": [part["coordinates"] for part in parts]}
    if set(output) != set(key_to_id.values()):
        raise ValueError("Geometria ausente em um quadrado visual de 5 km.")
    return output


def atualizar_grade_visual(root: Path, validate_product):
    """Refaz a malha de 5 km a partir das previsões nativas já publicadas."""
    index = json.loads((root / "native_sharded_grid/index.json").read_text())
    expected_count = index["feature_count"]
    native = np.empty((expected_count, 4 + len(SCORE_COLUMNS)), dtype=np.float64)
    seen = set()
    offset = 0
    for sector in index["sectors"]:
        collection = json.loads((root / "native_sharded_grid" / sector["url"]).read_text())
        if len(collection["features"]) != sector["feature_count"]:
            raise ValueError(f"Setor incompleto: {sector['id']}")
        for feature in collection["features"]:
            properties = feature["properties"]
            if properties["id"] in seen:
                raise ValueError(f"ID científico duplicado: {properties['id']}")
            seen.add(properties["id"])
            native[offset, :4] = (properties["grid_x"], properties["grid_y"],
                                  properties["centroid"][0], properties["centroid"][1])
            native[offset, 4:] = [properties[column] for column in SCORE_COLUMNS]
            offset += 1
    if len(seen) != 307410:
        raise ValueError(f"Grade científica incompleta: {len(seen)} células.")
    if offset != expected_count or expected_count != 307410:
        raise ValueError(f"Contagem nativa inesperada: {offset} células.")
    native = pd.DataFrame(native, columns=["X", "Y", "lon", "lat", *SCORE_COLUMNS])
    native["x_g"] = geo.XG_B + native["X"] * geo.XG_A
    native["y_g2"] = geo.YG_B + native["Y"] * geo.YG_A
    root = Path(root)
    original_manifest = json.loads((root / "aggregated/manifest.json").read_text())
    manifest_base = {key: value for key, value in original_manifest.items()
                     if key not in {"representation", "counts", "bounds", "files"}}
    temporary = root / "aggregated-5km-staging"
    if temporary.exists():
        shutil.rmtree(temporary)
    exportar_agregado(native, carregar_limite(), original_manifest["generated_at"], temporary, manifest_base)
    validate_product(root, aggregate_dir=temporary)
    backup_root = BASE / "resultados/risco_professor_v2"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f"previous-aggregated-grid-{int(__import__('time').time())}"
    current = root / "aggregated"
    current.replace(backup)
    try:
        temporary.replace(current)
    except BaseException:
        backup.replace(current)
        raise
    new_manifest = json.loads((current / "manifest.json").read_text())
    print(f"Malha visual atualizada: {new_manifest['counts']['features']} quadrados de cerca de 5 km.", flush=True)

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
            "schema_version": "2.0",
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
