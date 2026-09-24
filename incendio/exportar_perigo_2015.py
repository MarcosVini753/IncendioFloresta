"""Exporta a reconstituicao diaria de perigo de incendio para 2015.

O exportador carrega o cubo climatico uma unica vez, ajusta os quatro modelos
com o protocolo temporal existente e agrega cada previsao imediatamente para a
grade publica de 0,28 grau. Checkpoints locais permitem retomar por modelo e
data sem versionar resultados intermediarios.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from exportar_suscetibilidade import (
    GRID_STEP,
    carregar_limite,
    clip_boundary,
    geometry_bounds,
    sector_id,
    sector_indices,
)
from pipeline import dados, geo, modelos

BASE = Path(__file__).resolve().parent
RESULTADOS = BASE / "resultados"
CHECKPOINTS = RESULTADOS / "perigo_2015_checkpoints"
PRODUTO = BASE / "produtos" / "perigo" / "v1" / "2015"
AMOSTRA = RESULTADOS / "amostra_celula_dia.parquet"
ESTATICA = RESULTADOS / "estatica.parquet"
NOMES_CLIMA = RESULTADOS / "nomes_clima.json"

SEMENTE = 42
ANO = 2015
N_SOURCE_CELLS = 307_410
DEFAULT_DATE = "2015-08-25"

MODEL_SPECS = (
    {
        "id": "gradboost", "training_name": "GradBoost", "label": "GradBoost",
        "validation": {"roc_auc": 0.983462, "pr_auc": 0.821555},
        "test": {"roc_auc": 0.976538, "pr_auc": 0.779165},
    },
    {
        "id": "random_forest", "training_name": "RandomForest", "label": "Random Forest",
        "validation": {"roc_auc": 0.979192, "pr_auc": 0.810696},
        "test": {"roc_auc": 0.974980, "pr_auc": 0.777088},
    },
    {
        "id": "logistic_regression", "training_name": "RegLogistica", "label": "Regressão logística",
        "validation": {"roc_auc": 0.972802, "pr_auc": 0.779675},
        "test": {"roc_auc": 0.970432, "pr_auc": 0.739004},
    },
    {
        "id": "fuzzy_knn_k29", "training_name": "FuzzyKNN_k29", "label": "Fuzzy k-NN (k=29)",
        "validation": {"roc_auc": 0.920768, "pr_auc": 0.761170},
        "test": {"roc_auc": 0.916687, "pr_auc": 0.723283},
    },
)


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, path)


def calendar_2015() -> list[str]:
    return [str(value) for value in np.arange(
        np.datetime64("2015-01-01"), np.datetime64("2016-01-01"), np.timedelta64(1, "D")
    )]


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    missing = [path for path in (AMOSTRA, ESTATICA, NOMES_CLIMA) if not path.exists()]
    if missing:
        names = ", ".join(str(path.relative_to(BASE)) for path in missing)
        raise FileNotFoundError(
            f"Caches científicos ausentes: {names}. Execute treinar_perigo_diario.py primeiro."
        )
    sample = pd.read_parquet(AMOSTRA)
    static = pd.read_parquet(ESTATICA).reset_index(drop=True)
    names = json.loads(NOMES_CLIMA.read_text(encoding="utf-8"))
    if len(static) != N_SOURCE_CELLS or (static["cli_id"] < 0).any():
        raise ValueError("A tabela estática não representa as 307410 células climáticas válidas.")
    return sample, static, names


def fit_models(sample: pd.DataFrame, climate_names: list[str], selected: set[str]):
    predictors = dados.colunas_preditoras(sample, climate_names)
    if len(predictors) != 44:
        raise ValueError(f"Esperados 44 preditores; recebidos {len(predictors)}.")
    train = sample[sample["ano"].isin(range(2006, 2013))]
    X = train[predictors].to_numpy(dtype=np.float64)
    y = train["y"].to_numpy()
    zoo = modelos.zoo(SEMENTE, k_fuzzy=29)
    fitted = {}
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    for spec in MODEL_SPECS:
        if spec["id"] not in selected:
            continue
        cache = CHECKPOINTS / f"fitted_{spec['id']}.joblib"
        if cache.exists():
            payload = joblib.load(cache)
            if payload.get("predictors") == predictors:
                fitted[spec["id"]] = payload["model"]
                print(f"[modelo] {spec['label']} recuperado de {cache}", flush=True)
                continue
        model = zoo[spec["training_name"]]
        print(f"[modelo] ajustando {spec['label']} com {len(train)} pares...", flush=True)
        model.fit(X, y)
        joblib.dump({"model": model, "predictors": predictors}, cache)
        fitted[spec["id"]] = model
    return fitted, predictors


def build_grid(static: pd.DataFrame):
    boundary = carregar_limite()
    bounds = geometry_bounds(boundary["geometry"])
    rows, columns = sector_indices(static["lon"], static["lat"], bounds)
    keys = sorted({(int(row), int(column)) for row, column in zip(rows, columns)})
    key_to_position = {key: position for position, key in enumerate(keys)}
    group_index = np.fromiter(
        (key_to_position[(int(row), int(column))] for row, column in zip(rows, columns)),
        dtype=np.int64,
        count=len(static),
    )
    counts = np.bincount(group_index, minlength=len(keys))
    features = []
    for position, (row, column) in enumerate(keys):
        selected = group_index == position
        west = bounds[0] + column * GRID_STEP
        south = bounds[1] + row * GRID_STEP
        east = min(west + GRID_STEP, bounds[2])
        north = min(south + GRID_STEP, bounds[3])
        geometry = clip_boundary(boundary["geometry"], (west, south, east, north))
        if geometry is None:
            raise ValueError(f"Setor {row}/{column} não intersecta o limite do Acre.")
        cell = sector_id(row, column)
        features.append({
            "type": "Feature", "id": cell, "geometry": geometry,
            "properties": {
                "id": cell,
                "centroid": [round(float(static.loc[selected, "lon"].mean()), 7),
                             round(float(static.loc[selected, "lat"].mean()), 7)],
                "n_source_cells": int(counts[position]),
                "aggregation": "mean",
            },
        })
    if len(features) != 212 or int(counts.sum()) != N_SOURCE_CELLS:
        raise ValueError(f"Grade agregada divergente: {len(features)} células / {counts.sum()} fontes.")
    return features, group_index, counts, list(map(float, bounds))


def build_day_features(
    static: pd.DataFrame,
    climate_cube: np.ndarray,
    climate_names: list[str],
    predictors: list[str],
    date: str,
) -> np.ndarray:
    day = np.datetime64(date)
    band = int((day - geo.DATA_INICIO_CLIMA).astype(int))
    day_of_year = int((day - np.datetime64(f"{ANO}-01-01")).astype(int)) + 1
    frame = pd.DataFrame(index=static.index)
    for column in dados.COLUNAS_ESTATICAS:
        frame[column] = static[column].to_numpy()
    years = np.array(geo.ANOS_CICATRIZ)
    burned = np.column_stack(
        [static[f"queimou_{year}"].to_numpy() for year in geo.ANOS_CICATRIZ]
    ).astype(np.float32)
    frame["taxa_queima_hist"] = burned[:, years < ANO].mean(axis=1)
    frame["queimou_ano_anterior"] = burned[:, years == ANO - 1].ravel()
    angle = 2 * np.pi * day_of_year / 366.0
    frame["dia_sin"] = np.sin(angle)
    frame["dia_cos"] = np.cos(angle)
    frame["dia_ano"] = day_of_year
    climate_ids = static["cli_id"].to_numpy(dtype=np.int64)
    for offset, name in enumerate(climate_names):
        frame[name] = climate_cube[climate_ids, band, offset]

    fire_day = static[f"dia_{ANO}"].to_numpy(dtype=np.int64)
    burned_before_or_after = fire_day > 0
    contagion = dados.contagio(
        static["x_g"].to_numpy(), static["y_g2"].to_numpy(),
        np.full(len(static), day_of_year, dtype=np.int64),
        static.loc[burned_before_or_after, "x_g"].to_numpy(),
        static.loc[burned_before_or_after, "y_g2"].to_numpy(),
        fire_day[burned_before_or_after],
    )
    for name, values in contagion.items():
        frame[name] = values
    return frame[predictors].to_numpy(dtype=np.float64)


def _checkpoint_path(model_id: str) -> Path:
    return CHECKPOINTS / f"scores_{model_id}.npz"


def load_checkpoint(model_id: str, n_dates: int, n_cells: int):
    """Carrega o checkpoint legado e os arquivos independentes por data."""
    path = _checkpoint_path(model_id)
    values = np.full((n_dates, n_cells), np.nan)
    completed = np.zeros(n_dates, dtype=bool)
    if path.exists():
        with np.load(path) as payload:
            legacy_values, legacy_completed = payload["values"], payload["completed"]
        if legacy_values.shape != (n_dates, n_cells) or legacy_completed.shape != (n_dates,):
            raise ValueError(f"Checkpoint incompatível: {path}")
        values[legacy_completed] = legacy_values[legacy_completed]
        completed |= legacy_completed.astype(bool)
    directory = CHECKPOINTS / model_id
    if directory.exists():
        for day_path in directory.glob("*.npy"):
            try:
                date_index = int(day_path.stem)
            except ValueError as error:
                raise ValueError(f"Checkpoint diário inválido: {day_path}") from error
            row = np.load(day_path)
            if not 0 <= date_index < n_dates or row.shape != (n_cells,):
                raise ValueError(f"Checkpoint diário incompatível: {day_path}")
            values[date_index] = row
            completed[date_index] = True
    return values, completed.astype(bool)


def save_checkpoint(model_id: str, values: np.ndarray, completed: np.ndarray) -> None:
    directory = CHECKPOINTS / model_id
    directory.mkdir(parents=True, exist_ok=True)
    for date_index in np.flatnonzero(completed):
        path = directory / f"{date_index:03d}.npy"
        if path.exists():
            continue
        temporary = directory / f"{date_index:03d}.tmp.npy"
        np.save(temporary, values[date_index])
        os.replace(temporary, path)


def aggregate(values: np.ndarray, group_index: np.ndarray, counts: np.ndarray) -> np.ndarray:
    aggregated = np.bincount(group_index, weights=values, minlength=len(counts)) / counts
    if not np.isfinite(aggregated).all() or ((aggregated < 0) | (aggregated > 1)).any():
        raise ValueError("A previsão agregada contém valor não finito ou fora de [0,1].")
    return aggregated


def process(
    models_by_id, predictors, static, climate_cube, climate_names,
    dates, group_index, counts,
) -> None:
    states = {
        model_id: load_checkpoint(model_id, len(dates), len(counts))
        for model_id in models_by_id
    }
    for date_index, date in enumerate(dates):
        pending = [model_id for model_id, (_, done) in states.items() if not done[date_index]]
        if not pending:
            continue
        print(f"[dia {date_index + 1:03d}/{len(dates)}] {date}", flush=True)
        X = build_day_features(static, climate_cube, climate_names, predictors, date)
        for model_id in pending:
            prediction = models_by_id[model_id].predict_proba(X)[:, 1]
            matrix, completed = states[model_id]
            matrix[date_index] = aggregate(prediction, group_index, counts)
            completed[date_index] = True
            save_checkpoint(model_id, matrix, completed)
            print(f"  {model_id}: checkpoint salvo", flush=True)


def export_product(features, dates, bounds, predictors) -> None:
    matrices = {}
    for spec in MODEL_SPECS:
        values, completed = load_checkpoint(spec["id"], len(dates), len(features))
        if not completed.all():
            raise ValueError(f"{spec['label']} incompleto: {int(completed.sum())}/{len(dates)} datas.")
        matrices[spec["id"]] = values
    staging = PRODUTO.with_name(f".{PRODUTO.name}.building")
    backup = PRODUTO.with_name(f".{PRODUTO.name}.previous")
    if staging.exists():
        shutil.rmtree(staging)
    scores_dir = staging / "scores"
    scores_dir.mkdir(parents=True)
    _json_dump(staging / "grid.geojson", {"type": "FeatureCollection", "features": features})
    for spec in MODEL_SPECS:
        _json_dump(scores_dir / f"{spec['id']}.json", {
            "schema_version": "1.0", "model": spec["id"],
            "values": np.round(matrices[spec["id"]], 7).tolist(),
        })
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest = {
        "schema_version": "1.0",
        "product": "wildfire_historical_daily_danger",
        "label": "Perigo histórico diário — 2015",
        "generated_at": generated,
        "source_period": "2015-01-01/2015-12-31",
        "crs": "EPSG:4326",
        "default_model": "gradboost",
        "default_date": DEFAULT_DATE,
        "dates": dates,
        "cell_order": [feature["properties"]["id"] for feature in features],
        "models": [{
            "id": spec["id"], "label": spec["label"],
            "validation_2013": spec["validation"], "test_2014_2015": spec["test"],
            "file": f"scores/{spec['id']}.json",
        } for spec in MODEL_SPECS],
        "value": {"semantics": "relative_score", "domain": [0, 1], "calibrated_probability": False},
        "protocol": {
            "training": "2006-2012", "validation": "2013", "historical_test": "2014-2015",
            "predictor_count": len(predictors), "seed": SEMENTE,
            "fire_context": "previous_days_only",
        },
        "original_grid": {
            "crs": f"EPSG:{geo.EPSG_CENTROIDES}", "cell_width_m": geo.XG_A,
            "cell_height_m": geo.YG_A, "cell_count": N_SOURCE_CELLS,
        },
        "representation": {"type": "aggregated_grid", "step_degrees": GRID_STEP, "aggregation": "mean"},
        "counts": {"dates": len(dates), "features": len(features), "source_cells_per_date": N_SOURCE_CELLS},
        "bounds": [round(value, 7) for value in bounds],
        "files": {"grid": "grid.geojson"},
    }
    _json_dump(staging / "manifest.json", manifest)
    validate_product(staging)
    if backup.exists():
        shutil.rmtree(backup)
    if PRODUTO.exists():
        os.replace(PRODUTO, backup)
    try:
        os.replace(staging, PRODUTO)
    except Exception:
        if backup.exists() and not PRODUTO.exists():
            os.replace(backup, PRODUTO)
        raise
    if backup.exists():
        shutil.rmtree(backup)
    validate_product()
    print(f"Produto público gravado em {PRODUTO}")


def audit_samples(
    fitted, predictors, static, climate_cube, climate_names, group_index, counts, dates
) -> None:
    """Recalcula datas sazonais e compara previsao nativa com o checkpoint agregado."""
    for date in ("2015-01-15", "2015-08-25", "2015-12-15"):
        date_index = dates.index(date)
        X = build_day_features(static, climate_cube, climate_names, predictors, date)
        for model_id, model in fitted.items():
            native = model.predict_proba(X)[:, 1]
            expected = aggregate(native, group_index, counts)
            matrix, completed = load_checkpoint(model_id, 365, len(counts))
            if not completed[date_index] or not np.allclose(
                expected, matrix[date_index], rtol=0, atol=1e-12
            ):
                raise ValueError(f"Auditoria divergente em {date}/{model_id}.")
            print(f"[auditoria] {date}/{model_id}: médias reproduzidas", flush=True)


def validate_product(product_dir: Path = PRODUTO) -> None:
    manifest = json.loads((product_dir / "manifest.json").read_text(encoding="utf-8"))
    dates = manifest["dates"]
    expected = calendar_2015()
    if dates != expected or len(manifest["cell_order"]) != 212:
        raise ValueError("Manifesto não contém o calendário contínuo ou as 212 células esperadas.")
    grid = json.loads((product_dir / manifest["files"]["grid"]).read_text(encoding="utf-8"))
    if [item["properties"]["id"] for item in grid["features"]] != manifest["cell_order"]:
        raise ValueError("Ordem da grade diverge de cell_order.")
    if sum(item["properties"]["n_source_cells"] for item in grid["features"]) != N_SOURCE_CELLS:
        raise ValueError("Cobertura diária não soma 307410 células-fonte.")
    for model in manifest["models"]:
        payload = json.loads((product_dir / model["file"]).read_text(encoding="utf-8"))
        matrix = np.asarray(payload["values"], dtype=float)
        if matrix.shape != (365, 212):
            raise ValueError(f"Matriz {model['id']} possui forma {matrix.shape}.")
        if not np.isfinite(matrix).all() or ((matrix < 0) | (matrix > 1)).any():
            raise ValueError(f"Matriz {model['id']} contém escores inválidos.")
    print("Validação aprovada: 365 datas, 212 células e quatro matrizes em [0,1].")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", choices=[item["id"] for item in MODEL_SPECS])
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2015-12-31")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--audit-samples", action="store_true", help="recalcula janeiro, agosto e dezembro")
    args = parser.parse_args()
    if args.validate_only:
        validate_product()
        return
    all_dates = calendar_2015()
    selected_dates = [date for date in all_dates if args.start <= date <= args.end]
    if not selected_dates:
        raise ValueError("Intervalo não contém datas de 2015.")
    sample, static, climate_names = load_inputs()
    features, group_index, counts, bounds = build_grid(static)
    predictors = dados.colunas_preditoras(sample, climate_names)
    if not args.export_only:
        selected = set(args.models or [item["id"] for item in MODEL_SPECS])
        fitted, predictors = fit_models(sample, climate_names, selected)
        print("[clima] carregando o cubo uma única vez...", flush=True)
        climate_cube, loaded_names = dados.features_climaticas()
        if loaded_names != climate_names:
            raise ValueError("Ordem das variáveis climáticas difere do cache de treinamento.")
        indices = [all_dates.index(date) for date in selected_dates]
        # Checkpoints têm sempre as 365 linhas; processa só o intervalo solicitado.
        states = {model_id: load_checkpoint(model_id, 365, len(features)) for model_id in fitted}
        for date_index in indices:
            date = all_dates[date_index]
            pending = [mid for mid, (_, done) in states.items() if not done[date_index]]
            if not pending:
                continue
            print(f"[dia {date_index + 1:03d}/365] {date}", flush=True)
            X = build_day_features(static, climate_cube, climate_names, predictors, date)
            for model_id in pending:
                prediction = fitted[model_id].predict_proba(X)[:, 1]
                matrix, completed = states[model_id]
                matrix[date_index] = aggregate(prediction, group_index, counts)
                completed[date_index] = True
                save_checkpoint(model_id, matrix, completed)
                print(f"  {model_id}: checkpoint salvo", flush=True)
        if args.audit_samples:
            audit_samples(
                fitted, predictors, static, climate_cube, climate_names,
                group_index, counts, all_dates,
            )
    if all(load_checkpoint(item["id"], 365, len(features))[1].all() for item in MODEL_SPECS):
        export_product(features, all_dates, bounds, predictors)
    else:
        print("Checkpoints ainda incompletos; o produto público será gerado ao concluir os quatro modelos.")


if __name__ == "__main__":
    main()
