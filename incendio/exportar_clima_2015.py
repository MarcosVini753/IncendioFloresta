"""Exporta clima diario e cicatrizes observadas de 2015 para o navegador.

As estatisticas sao espaciais dentro de cada setor visual, nao extremos horarios.
Pixels climaticos contribuem conforme a area de intersecao com o setor recortado.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pyproj import Geod

from pipeline import geo
from exportar_suscetibilidade import clip_boundary, clip_ring, geometry_bounds

BASE = Path(__file__).resolve().parent
GRID_SOURCE = BASE / "produtos/suscetibilidade/v1/aggregated/mapa.geojson"
OUTPUT = BASE / "produtos/clima/v1/2015"
YEAR = 2015
DATES = [str(day) for day in geo.datas_clima() if str(day).startswith("2015-")]
GEOD = Geod(ellps="WGS84")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def ring_area(ring: list[list[float]]) -> float:
    if not ring:
        return 0.0
    area, _ = GEOD.polygon_area_perimeter([p[0] for p in ring], [p[1] for p in ring])
    return abs(area)


def overlap_area(geometry: dict, bounds: tuple[float, float, float, float]) -> float:
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    area = 0.0
    for polygon in polygons:
        exterior = clip_ring(polygon[0], bounds)
        area += ring_area(exterior) if exterior else 0.0
        for hole in polygon[1:]:
            interior = clip_ring(hole, bounds)
            area -= ring_area(interior) if interior else 0.0
    return max(area, 0.0)


def raster_bounds(grid: geo.GradeRaster, row: int, col: int) -> tuple[float, float, float, float]:
    west = grid.lon0 + col * grid.passo
    north = grid.lat0 - row * grid.passo
    return west, north - grid.passo, west + grid.passo, north


def candidate_pixels(geometry: dict, grid: geo.GradeRaster):
    west, south, east, north = geometry_bounds(geometry)
    c0 = max(0, math.floor((west - grid.lon0) / grid.passo))
    c1 = min(grid.n_col - 1, math.ceil((east - grid.lon0) / grid.passo) - 1)
    r0 = max(0, math.floor((grid.lat0 - north) / grid.passo))
    r1 = min(grid.n_lin - 1, math.ceil((grid.lat0 - south) / grid.passo) - 1)
    for row in range(r0, r1 + 1):
        for col in range(c0, c1 + 1):
            yield row, col


def climate_membership(features: list[dict], grid: geo.GradeRaster, mask: np.ndarray):
    memberships = []
    for feature in features:
        members = []
        for row, col in candidate_pixels(feature["geometry"], grid):
            if not mask[row, col]:
                continue
            weight = overlap_area(feature["geometry"], raster_bounds(grid, row, col))
            if weight > 1e-12:
                members.append((row, col, weight))
        memberships.append(members)
    return memberships


def daily_stats(cube: np.ndarray, members: list[tuple[int, int, float]], first_day: int):
    if not members:
        return [[None, None, None] for _ in DATES]
    rows = [row for row, _, _ in members]
    cols = [col for _, col, _ in members]
    weights = np.array([weight for _, _, weight in members], dtype=np.float64)
    values = cube[rows, cols, first_day:first_day + len(DATES)].astype(np.float64).T
    result = []
    for day in values:
        valid = np.isfinite(day)
        if not valid.any():
            result.append([None, None, None])
            continue
        selected = day[valid]
        result.append([
            round(float(selected.min()), 3),
            round(float(np.average(selected, weights=weights[valid])), 3),
            round(float(selected.max()), 3),
        ])
    return result


def export_scars(boundary: dict) -> dict:
    cube = geo.ler_cubo(str(BASE / geo.ARQ_CICATRIZES))
    if cube.shape[2] != len(geo.ANOS_CICATRIZ):
        raise ValueError("Quantidade de bandas de cicatrizes inesperada.")
    band = cube[:, :, geo.ANOS_CICATRIZ.index(YEAR)]
    grid = geo.ler_grade(str(BASE / geo.ARQ_CICATRIZES))
    result = []
    for row, col in zip(*np.nonzero(band > 0)):
        day_of_year = int(band[row, col])
        if day_of_year > len(DATES):
            raise ValueError(f"Dia de cicatriz invalido: {day_of_year}.")
        pixel = raster_bounds(grid, int(row), int(col))
        geometry = clip_boundary(boundary, pixel)
        if geometry is None:
            continue
        west, south, east, north = geometry_bounds(geometry)
        result.append({
            "type": "Feature",
            "properties": {"date": DATES[day_of_year - 1], "day_of_year": day_of_year,
                           "center": [round((west + east) / 2, 7), round((south + north) / 2, 7)]},
            "geometry": geometry,
        })
    return {"type": "FeatureCollection", "features": result}


def validate_product(manifest: dict, grid: dict, climate: dict, scars: dict) -> None:
    dates = manifest["dates"]
    order = manifest["cell_order"]
    if dates != DATES or len(dates) != 365:
        raise ValueError("Calendario de 2015 incompleto.")
    if len(order) != 212 or len(set(order)) != 212:
        raise ValueError("A grade visual nao contem 212 IDs unicos.")
    if [f["properties"]["id"] for f in grid["features"]] != order:
        raise ValueError("Ordem da grade visual difere do manifesto.")
    if len(manifest["n_valid_pixels"]) != len(order):
        raise ValueError("Contagens de pixels climaticos incompletas.")
    for name, source in climate.items():
        values = source["values"]
        if len(values) != 365 or any(len(day) != 212 for day in values):
            raise ValueError(f"Matriz {name} nao tem dimensao 365 x 212.")
        for day in values:
            for value in day:
                if value == [None, None, None]:
                    continue
                if len(value) != 3 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in value):
                    raise ValueError(f"Valor invalido em {name}.")
                if not value[0] <= value[1] <= value[2]:
                    raise ValueError(f"Estatisticas fora de ordem em {name}.")
    if any(f["properties"]["date"] not in dates for f in scars["features"]):
        raise ValueError("Cicatriz fora de 2015.")


def export() -> None:
    with GRID_SOURCE.open(encoding="utf-8") as stream:
        source = json.load(stream)
    features = [{
        "type": "Feature",
        "id": f["properties"]["id"],
        "properties": {"id": f["properties"]["id"], "centroid": f["properties"]["centroid"]},
        "geometry": f["geometry"],
    } for f in source["features"]]
    grid = {"type": "FeatureCollection", "features": features}
    grid_geo = geo.ler_grade(str(BASE / geo.ARQ_UMIDADE))
    humidity = geo.ler_cubo(str(BASE / geo.ARQ_UMIDADE), dtype=np.float32)
    rainfall = geo.ler_cubo(str(BASE / geo.ARQ_PRECIPITACAO), dtype=np.float32)
    if humidity.shape != rainfall.shape or humidity.shape != (41, 75, geo.N_DIAS_CLIMA):
        raise ValueError("Grades climaticas incompatíveis com o calendario esperado.")
    rain_geo = geo.ler_grade(str(BASE / geo.ARQ_PRECIPITACAO))
    if grid_geo != rain_geo:
        raise ValueError("Grades de umidade e precipitacao nao coincidem.")
    valid = np.isfinite(humidity).any(axis=2) & np.isfinite(rainfall).any(axis=2)
    members = climate_membership(features, grid_geo, valid)
    first_day = int(np.searchsorted(geo.datas_clima(), np.datetime64(DATES[0])))
    climate = {}
    for key, cube in (("humidity", humidity), ("precipitation", rainfall)):
        by_cell = [daily_stats(cube, pixels, first_day) for pixels in members]
        values = [[by_cell[cell][day] for cell in range(len(features))] for day in range(len(DATES))]
        climate[key] = {"variable": key, "values": values}
    del humidity, rainfall

    with (BASE / "recursos/limite_acre.geojson").open(encoding="utf-8") as stream:
        boundary_raw = json.load(stream)
    boundary_feature = boundary_raw["features"][0] if boundary_raw["type"] == "FeatureCollection" else boundary_raw
    boundary = boundary_feature["geometry"]
    scars = export_scars(boundary)
    manifest = {
        "schema_version": "1.0", "product": "historical_climate_and_scars", "year": YEAR,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "crs": "EPSG:4326", "dates": DATES,
        "cell_order": [f["properties"]["id"] for f in features],
        "bounds": list(geometry_bounds(boundary)),
        "n_valid_pixels": [len(pixels) for pixels in members],
        "grid": {"step_degrees": 0.28, "source_step_degrees": grid_geo.passo},
        "statistics": {"scope": "spatial_per_day", "mean": "pixel_overlap_area_weighted", "extrema": "intersecting_valid_pixels"},
        "variables": {"humidity": {"unit": "%", "source": geo.ARQ_UMIDADE},
                      "precipitation": {"unit": "mm", "source": geo.ARQ_PRECIPITACAO}},
        "scars": {"source": geo.ARQ_CICATRIZES, "meaning": "day_of_year_of_detection",
                  "feature_count": len(scars["features"])},
        "files": {"grid": "grid.geojson", "boundary": "boundary.geojson", "humidity": "humidity.json",
                  "precipitation": "precipitation.json", "scars": "scars.geojson"},
    }
    validate_product(manifest, grid, climate, scars)
    staging = OUTPUT.with_name("2015-staging")
    if staging.exists():
        shutil.rmtree(staging)
    write_json(staging / "grid.geojson", grid)
    write_json(staging / "boundary.geojson", boundary_feature)
    write_json(staging / "humidity.json", climate["humidity"])
    write_json(staging / "precipitation.json", climate["precipitation"])
    write_json(staging / "scars.geojson", scars)
    write_json(staging / "manifest.json", manifest)
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    staging.rename(OUTPUT)
    print(f"Produto: {OUTPUT} | {len(DATES)} dias | {len(features)} celulas | {len(scars['features'])} pixels de cicatriz")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        with (OUTPUT / "manifest.json").open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        with (OUTPUT / "grid.geojson").open(encoding="utf-8") as stream:
            grid = json.load(stream)
        climate = {}
        for variable in ("humidity", "precipitation"):
            with (OUTPUT / f"{variable}.json").open(encoding="utf-8") as stream:
                climate[variable] = json.load(stream)
        with (OUTPUT / "scars.geojson").open(encoding="utf-8") as stream:
            scars = json.load(stream)
        validate_product(manifest, grid, climate, scars)
        print("Produto validado: 365 dias, 212 celulas e estatisticas espaciais validas.")
    else:
        export()
