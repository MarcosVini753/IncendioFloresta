"""Exporta a suscetibilidade experimental para consumo pelo frontend.

O produto agregado e a grade cientifica nativa partem exatamente dos mesmos
quatro escores. Os valores sao escores relativos em [0, 1], nao probabilidades
calibradas nem previsoes operacionais de incendio.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from pipeline import dados, geo, modelos
from treinar_suscetibilidade import PREDITORES, equilibrar, montar

BASE = Path(__file__).resolve().parent
RESULTADOS = BASE / "resultados"
ESTATICA = RESULTADOS / "estatica.parquet"
CACHE_SCORES = RESULTADOS / "suscetibilidade_scores.parquet"
LIMITE = BASE / "recursos" / "limite_acre.geojson"
PRODUTO = BASE / "produtos" / "suscetibilidade" / "v1"
AGREGADO = PRODUTO / "aggregated"
NATIVO = PRODUTO / "native_sharded_grid"

GRID_STEP = 0.28
SEMENTE = 42
K_FUZZY = 29
WIDTH_M = geo.XG_A
HEIGHT_M = geo.YG_A

MODEL_SPECS = (
    {
        "id": "gradboost",
        "training_name": "GradBoost",
        "label": "GradBoost",
        "property": "score_gradboost",
        "roc_auc": 0.8626046879537765,
        "pr_auc": 0.8209198956599393,
    },
    {
        "id": "random_forest",
        "training_name": "RandomForest",
        "label": "Random Forest",
        "property": "score_random_forest",
        "roc_auc": 0.8620899542894825,
        "pr_auc": 0.8189487409531366,
    },
    {
        "id": "logistic_regression",
        "training_name": "RegLogistica",
        "label": "Regressão logística",
        "property": "score_logistic_regression",
        "roc_auc": 0.8542878212075525,
        "pr_auc": 0.8102112687664871,
    },
    {
        "id": "fuzzy_knn_k29",
        "training_name": "FuzzyKNN_k29",
        "label": "Fuzzy k-NN (k=29)",
        "property": "score_fuzzy_knn_k29",
        "roc_auc": 0.8447305875567344,
        "pr_auc": 0.7943606296911658,
    },
)
SCORE_COLUMNS = tuple(spec["property"] for spec in MODEL_SPECS)


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))


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


def carregar_estatica() -> pd.DataFrame:
    if ESTATICA.exists():
        print(f"Tabela estatica: {ESTATICA}")
        est = pd.read_parquet(ESTATICA)
    else:
        print("Tabela estatica ausente; reconstruindo a partir dos insumos locais...")
        est = dados.tabela_estatica()
        RESULTADOS.mkdir(exist_ok=True)
        est.to_parquet(ESTATICA, index=False)
    required = {*PREDITORES, "X", "Y", "x_g", "y_g2", "lon", "lat"}
    required.update(f"queimou_{year}" for year in geo.ANOS_CICATRIZ)
    missing = sorted(required.difference(est.columns))
    if missing:
        raise ValueError(f"Tabela estatica sem colunas obrigatorias: {', '.join(missing)}")
    if len(est) != 307_410:
        raise ValueError(f"Esperadas 307410 celulas cientificas; recebidas {len(est)}.")
    return est.reset_index(drop=True)


def treinar_e_calcular(est: pd.DataFrame, reutilizar: bool) -> pd.DataFrame:
    cache_columns = ["X", "Y", "x_g", "y_g2", "lon", "lat", *SCORE_COLUMNS]
    if reutilizar and CACHE_SCORES.exists():
        scores = pd.read_parquet(CACHE_SCORES)
        if len(scores) == len(est) and all(column in scores for column in cache_columns):
            print(f"Escores reutilizados: {CACHE_SCORES}")
            validar_scores(scores)
            return scores[cache_columns]

    _, target = montar(est, "qualquer")
    index = equilibrar(target, np.random.default_rng(SEMENTE), razao=1)
    X_train = est.iloc[index][PREDITORES].to_numpy(dtype=np.float64)
    y_train = target[index]
    X_all = est[PREDITORES].to_numpy(dtype=np.float64)
    print(
        f"Treino balanceado: {len(index)} celulas, {int(y_train.sum())} positivas, "
        f"semente {SEMENTE}."
    )
    model_zoo = modelos.zoo(SEMENTE, k_fuzzy=K_FUZZY)
    scores = est[["X", "Y", "x_g", "y_g2", "lon", "lat"]].copy()
    for spec in MODEL_SPECS:
        model = model_zoo[spec["training_name"]]
        print(f"Treinando e calculando {spec['label']}...")
        model.fit(X_train, y_train)
        values = model.predict_proba(X_all)[:, 1]
        scores[spec["property"]] = values
        print(f"  faixa [{values.min():.6f}, {values.max():.6f}]")
    validar_scores(scores)
    RESULTADOS.mkdir(exist_ok=True)
    scores.to_parquet(CACHE_SCORES, index=False)
    print(f"Cache local: {CACHE_SCORES}")
    return scores


def validar_scores(scores: pd.DataFrame) -> None:
    for column in SCORE_COLUMNS:
        values = scores[column].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"{column} contem valores nao finitos.")
        if ((values < 0) | (values > 1)).any():
            raise ValueError(f"{column} contem valores fora de [0, 1].")


def sector_indices(lon, lat, bounds):
    west, south, east, north = bounds
    columns = np.floor((np.asarray(lon) - west) / GRID_STEP).astype(int)
    rows = np.floor((np.asarray(lat) - south) / GRID_STEP).astype(int)
    max_column = max(math.ceil((east - west) / GRID_STEP) - 1, 0)
    max_row = max(math.ceil((north - south) / GRID_STEP) - 1, 0)
    return np.clip(rows, 0, max_row), np.clip(columns, 0, max_column)


def sector_id(row: int, column: int) -> str:
    return f"AC-R{row + 1:02d}C{column + 1:02d}"


def public_models():
    return [
        {
            "id": spec["id"],
            "label": spec["label"],
            "property": spec["property"],
            "validation": {
                "protocol": "spatial_group_kfold_25km",
                "folds": 5,
                "roc_auc": spec["roc_auc"],
                "pr_auc": spec["pr_auc"],
            },
        }
        for spec in MODEL_SPECS
    ]


def base_manifest(generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "product": "wildfire_susceptibility",
        "label": "Suscetibilidade — modelo experimental",
        "generated_at": generated_at,
        "source_period": "2006-2016",
        "crs": "EPSG:4326",
        "default_model": "gradboost",
        "models": public_models(),
        "value": {
            "semantics": "relative_score",
            "domain": [0, 1],
            "calibrated_probability": False,
        },
        "training": {
            "target": "burned_at_least_once_2006_2016",
            "sample": "balanced_1_to_1",
            "seed": SEMENTE,
            "predictors": PREDITORES,
        },
        "original_grid": {
            "crs": f"EPSG:{geo.EPSG_CENTROIDES}",
            "cell_width_m": WIDTH_M,
            "cell_height_m": HEIGHT_M,
            "cell_count": 307_410,
        },
    }


def exportar_agregado(scores: pd.DataFrame, boundary: dict[str, Any], generated_at: str):
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
            properties[score] = _round(group[score].mean())
        features.append(
            {"type": "Feature", "id": properties["id"], "properties": properties, "geometry": geometry}
        )

    count = sum(feature["properties"]["n_source_cells"] for feature in features)
    if count != len(scores):
        raise ValueError(f"Agregacao perdeu celulas: soma={count}; fonte={len(scores)}")

    if AGREGADO.exists():
        shutil.rmtree(AGREGADO)
    AGREGADO.mkdir(parents=True)
    _json_dump(AGREGADO / "mapa.geojson", {"type": "FeatureCollection", "features": features})
    _json_dump(AGREGADO / "limite_acre.geojson", boundary)
    manifest = base_manifest(generated_at)
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
    _json_dump(AGREGADO / "manifest.json", manifest)
    print(f"Produto agregado: {len(features)} features; {count} celulas-fonte -> {AGREGADO}")
    return features


def native_geometry(x: float, y: float):
    half_w, half_h = WIDTH_M / 2, HEIGHT_M / 2
    xs = np.array([x - half_w, x + half_w, x + half_w, x - half_w, x - half_w])
    ys = np.array([y - half_h, y - half_h, y + half_h, y + half_h, y - half_h])
    lon, lat = geo.utm_para_lonlat(xs, ys)
    return {
        "type": "Polygon",
        "coordinates": [[[ _round(px), _round(py)] for px, py in zip(lon, lat)]],
    }


def exportar_nativo(scores: pd.DataFrame, boundary: dict[str, Any], generated_at: str):
    bounds = geometry_bounds(boundary["geometry"])
    rows, columns = sector_indices(scores["lon"], scores["lat"], bounds)
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
            "centroid": [_round(row.lon), _round(row.lat)],
            "aggregation": "none",
        }
        for column in SCORE_COLUMNS:
            properties[column] = _round(getattr(row, column))
        sectors[sid].append(
            {
                "type": "Feature",
                "id": cell_id,
                "properties": properties,
                "geometry": native_geometry(float(row.x_g), float(row.y_g2)),
            }
        )
    if len(seen) != 307_410:
        raise ValueError(f"Grade nativa incompleta: {len(seen)} IDs unicos.")

    if NATIVO.exists():
        shutil.rmtree(NATIVO)
    sector_dir = NATIVO / "sectors"
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
        NATIVO / "index.json",
        {
            "schema_version": "1.0",
            "product": "wildfire_susceptibility_native_index",
            "generated_at": generated_at,
            "crs": "EPSG:4326",
            "sector_step_degrees": GRID_STEP,
            "feature_count": len(seen),
            "sectors": index_entries,
        },
    )
    manifest = base_manifest(generated_at)
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
    _json_dump(NATIVO / "manifest.json", manifest)
    print(f"Produto nativo: {len(seen)} features em {len(index_entries)} setores -> {NATIVO}")


def validar_produto_agregado() -> None:
    with (AGREGADO / "manifest.json").open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    with (AGREGADO / manifest["files"]["geojson"]).open(encoding="utf-8") as stream:
        collection = json.load(stream)
    features = collection.get("features", [])
    if collection.get("type") != "FeatureCollection" or not features:
        raise ValueError("GeoJSON agregado vazio ou invalido.")
    if sum(item["properties"]["n_source_cells"] for item in features) != 307_410:
        raise ValueError("Contagem agregada diferente de 307410.")
    for item in features:
        for column in SCORE_COLUMNS:
            value = item["properties"].get(column)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Escore agregado invalido em {item.get('id')}: {column}")
    print("Validacao agregada aprovada: escores finitos em [0,1] e 307410 celulas-fonte.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true", help="tambem exporta a grade nativa por setores")
    parser.add_argument("--reuse-scores", action="store_true", help="reutiliza o cache local de escores quando valido")
    parser.add_argument("--validate-only", action="store_true", help="valida o produto agregado ja gerado")
    args = parser.parse_args()
    if args.validate_only:
        validar_produto_agregado()
        return
    boundary = carregar_limite()
    est = carregar_estatica()
    scores = treinar_e_calcular(est, args.reuse_scores)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    exportar_agregado(scores, boundary, generated_at)
    validar_produto_agregado()
    if args.native:
        exportar_nativo(scores, boundary, generated_at)


if __name__ == "__main__":
    main()
