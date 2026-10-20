"""Importa mapas finais de 2025/2026, sem treinar, prever ou recalibrar modelos.

Uso: incendio/.venv/bin/python incendio/importar_risco_professor_v4.py
Os setores/checkpoints são retomáveis; o produto é publicado após a auditoria.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyproj
import rasterio
from rasterio.shutil import copy as copy_raster
from rasterio.windows import Window, from_bounds
from shapely.geometry import box, mapping, shape
from shapely import transform as transform_geometry

BASE = Path(__file__).resolve().parent
REPO = BASE.parent
CACHE = BASE / "resultados/risco_professor_v4"
MODELS = ("random_forest", "xgboost")
NAMES = ("RandomForest", "XGBoost")
LABELS = ("Random Forest", "XGBoost")
CLASSES = (
    ("very_low", "Muito baixo", 0, 50, "#1a9850"),
    ("low", "Baixo", 50, 70, "#91cf60"),
    ("moderate", "Moderado", 70, 90, "#fee08b"),
    ("high", "Alto", 90, 95, "#fc8d59"),
    ("very_high", "Muito alto", 95, 100, "#d73027"),
)
CONTRACT = "4.0-import-1"
SIZE = 1024
GRID_METRES = 5000


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_sources(sources, window):
    blocks = [source.read(window=window, masked=True) for source in sources]
    mask = ~np.ma.getmaskarray(blocks[0])[0]
    for block in blocks:
        for band in range(2):
            if not np.array_equal(mask, ~np.ma.getmaskarray(block)[band]):
                raise ValueError("Máscaras dos dois modelos/bandas são diferentes.")
    values = np.concatenate(
        [np.asarray(block.data, dtype=np.float32) for block in blocks]
    )
    valid = values[:, mask]
    if not np.isfinite(valid).all() or ((valid < 0) | (valid > 100)).any():
        raise ValueError("Valor válido fora de [0,100] ou não finito.")
    values[:, ~mask] = -9999
    return values, mask


def aggregate_block(values, mask, window, affine, project):
    rows, cols = np.nonzero(mask)
    lon = affine.c + (cols + window.col_off + 0.5) * affine.a
    lat = affine.f + (rows + window.row_off + 0.5) * affine.e
    x, y = project.transform(lon, lat)
    tx, ty = np.floor(x / GRID_METRES).astype(np.int64), np.floor(
        y / GRID_METRES
    ).astype(np.int64)
    keys, inverse = np.unique(tx * 10000 + ty, return_inverse=True)
    counts = np.bincount(inverse, minlength=len(keys))
    sums = np.column_stack(
        [
            np.bincount(inverse, weights=band[mask], minlength=len(keys))
            for band in values
        ]
    )
    centres = np.column_stack(
        [np.bincount(inverse, weights=v, minlength=len(keys)) for v in (lon, lat)]
    )
    classes = np.empty((len(keys), 2, 5), dtype=np.int64)
    for model, band in enumerate((1, 3)):
        category = np.searchsorted([50, 70, 90, 95], values[band, mask], side="right")
        classes[:, model] = np.bincount(
            inverse * 5 + category, minlength=len(keys) * 5
        ).reshape(-1, 5)
    return dict(keys=keys, counts=counts, sums=sums, centres=centres, classes=classes)


def verify_cog(path, values, mask, affine):
    with rasterio.open(path) as cog:
        if cog.count != 4 or cog.crs.to_epsg() != 4326 or cog.transform != affine:
            raise ValueError(f"Contrato COG inválido: {path}")
        if cog.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") != "COG":
            raise ValueError(f"Arquivo não é COG: {path}")
        recovered = cog.read()
        if not np.array_equal(recovered, values):
            raise ValueError(f"COG alterou valores originais: {path}")
        if not np.array_equal(cog.dataset_mask() > 0, mask):
            raise ValueError(f"COG alterou a máscara: {path}")


def write_cog(path, values, mask, affine, year):
    # O staging pode conter um hard link de uma publicação anterior.
    # Remover somente esse link antes de regenerar, sem alterar o original.
    path.unlink(missing_ok=True)
    temporary = path.with_suffix(".source.tif")
    profile = dict(
        driver="GTiff",
        width=mask.shape[1],
        height=mask.shape[0],
        count=4,
        dtype="float32",
        crs="EPSG:4326",
        transform=affine,
        nodata=-9999,
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )
    with rasterio.open(temporary, "w", **profile) as dst:
        dst.write(values)
        dst.descriptions = (
            "random_forest_value_pct",
            "random_forest_percentile",
            "xgboost_value_pct",
            "xgboost_percentile",
        )
        dst.update_tags(year=year, scenario="AB30C_suave", source_values="unchanged")
    try:
        copy_raster(
            temporary,
            path,
            driver="COG",
            BLOCKSIZE=256,
            COMPRESS="DEFLATE",
            PREDICTOR="FLOATING_POINT",
            OVERVIEW_RESAMPLING="AVERAGE",
            NUM_THREADS="2",
        )
        verify_cog(path, values, mask, affine)
    finally:
        temporary.unlink(missing_ok=True)


def build(source_root, reports_root, year=2026):
    OUTPUT = BASE / f"produtos/risco/v4/{year}"
    paths = [source_root / f"risco_30m_{name}_AB30C_suave_{year}.tif" for name in NAMES]
    print(f"Conferindo hashes dos dois GeoTIFFs de {year}…", flush=True)
    provenance = [
        {"file": p.name, "sha256": digest(p), "bytes": p.stat().st_size} for p in paths
    ]
    boundary_path = BASE / "recursos/limite_acre.geojson"
    boundary_raw = load(boundary_path)
    boundary = (
        boundary_raw["features"][0]
        if boundary_raw.get("type") == "FeatureCollection"
        else boundary_raw
    )
    reports = []
    evaluation = {}
    report_files = []
    for model, name in zip(MODELS, NAMES):
        report = (
            reports_root / "tabelas/mapas" / f"avaliacao_{name}_AB30C_suave_{year}.json"
        )
        metadata = load(report)
        if (
            metadata["ano"],
            metadata["modelo"],
            metadata["cenario"],
            metadata["rotulo"],
            metadata["treino"],
        ) != (year, name, "AB30C", "fogo", f"2016-{year - 1}") or not metadata[
            "suavizado_no_clima"
        ]:
            raise ValueError(f"Relatório incompatível: {report}")
        if bool(metadata["calibracao"]) != (model == "random_forest"):
            raise ValueError("Semântica de calibração inesperada.")
        reports.append(metadata)
        evaluation[model] = []
        for historical_year in (2023, 2024, 2025):
            path = (
                reports_root
                / "tabelas/mapas"
                / f"avaliacao_{name}_AB30C_suave_{historical_year}.json"
            )
            received = load(path)
            if (
                received["nome"] != f"{name}_AB30C_suave"
                or received["rotulo"] != "fogo"
                or received["ano"] != historical_year
            ):
                raise ValueError(
                    "Avaliação histórica não corresponde ao mapa importado."
                )
            metrics = received["30m_fogo"]
            if not all(
                np.isfinite(metrics[k])
                for k in (
                    "pr_auc",
                    "roc_auc",
                    "brier",
                    "captura_1%",
                    "captura_5%",
                    "captura_10%",
                )
            ):
                raise ValueError("Métrica recebida não finita.")
            evaluation[model].append(
                {
                    "year": historical_year,
                    "level": "30m_fogo",
                    "origin": "received_professor",
                    "training": received["treino"],
                    "metrics": metrics,
                }
            )
            report_files.append({"file": path.name, "sha256": digest(path)})
        report_files.append({"file": report.name, "sha256": digest(report)})
    identity = hashlib.sha256(
        json.dumps(
            {
                "sources": provenance,
                "reports": report_files,
                "boundary": digest(boundary_path),
                "contract": CONTRACT,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    staging = OUTPUT.parent / f".{year}-staging"
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "sectors").mkdir(exist_ok=True)
    cache = CACHE / identity
    cache.mkdir(parents=True, exist_ok=True)
    project = pyproj.Transformer.from_crs(4326, 31979, always_xy=True)
    inverse_project = pyproj.Transformer.from_crs(31979, 4326, always_xy=True)
    merged = {}
    sectors = []
    sources = [rasterio.open(path) for path in paths]
    try:
        reference = sources[0]
        for source, name in zip(sources, NAMES):
            tags = source.tags()
            if (
                source.count != 2
                or source.crs.to_epsg() != 4326
                or source.descriptions != ("probabilidade_pct", "indice_risco")
            ):
                raise ValueError("CRS ou bandas inesperados.")
            if (source.shape, source.transform, source.nodata) != (
                reference.shape,
                reference.transform,
                -9999,
            ):
                raise ValueError("Grades de entrada não estão alinhadas.")
            if (
                tags.get("ano") != str(year)
                or tags.get("modelo") != f"{name}_AB30C_suave"
                or tags.get("rotulo_de_treino") != "fogo"
            ):
                raise ValueError("Metadados do GeoTIFF não correspondem à entrega.")
        affine = reference.transform
        if affine.b != 0 or affine.d != 0 or affine.a <= 0 or affine.e >= 0:
            raise ValueError("A grade deve ser north-up, sem rotação.")
        total = ((reference.height + SIZE - 1) // SIZE) * (
            (reference.width + SIZE - 1) // SIZE
        )
        done = 0
        reused = 0
        for row in range(0, reference.height, SIZE):
            for col in range(0, reference.width, SIZE):
                done += 1
                window = Window(
                    col,
                    row,
                    min(SIZE, reference.width - col),
                    min(SIZE, reference.height - row),
                )
                cell_id = f"AC-V4-R{row // SIZE:03d}C{col // SIZE:03d}"
                checkpoint, checkpoint_meta = (
                    cache / f"{cell_id}.npz",
                    cache / f"{cell_id}.json",
                )
                cog = staging / "sectors" / f"{cell_id}.tif"
                saved = load(checkpoint_meta) if checkpoint_meta.exists() else None
                published_cog = OUTPUT / "sectors" / cog.name
                previous_cog = cog if cog.exists() else published_cog
                if (
                    saved
                    and saved["identity"] == identity
                    and checkpoint.exists()
                    and (
                        saved.get("stats_sha256") is None
                        or saved["stats_sha256"] == digest(checkpoint)
                    )
                    and (
                        saved["entry"] is None
                        or previous_cog.exists()
                        and digest(previous_cog) == saved["cog_sha256"]
                    )
                ):
                    reused += int(saved["entry"] is not None)
                    if saved["entry"] is not None and not cog.exists():
                        # Reutilizar mapas já publicados sem copiá-los ou
                        # recalcular. Os setores permanecem imutáveis.
                        os.link(previous_cog, cog)
                    with np.load(checkpoint, allow_pickle=False) as raw:
                        stats = {key: raw[key] for key in raw.files}
                    entry = saved["entry"]
                    dump(checkpoint_meta, {**saved, "stats_sha256": digest(checkpoint)})
                else:
                    values, mask = read_sources(sources, window)
                    count = int(mask.sum())
                    stats = (
                        aggregate_block(values, mask, window, affine, project)
                        if count
                        else None
                    )
                    entry = None
                    if count:
                        write_cog(
                            cog, values, mask, reference.window_transform(window), year
                        )
                        entry = {
                            "id": cell_id,
                            "url": f"sectors/{cell_id}.tif",
                            "window": [
                                int(v) for v in (col, row, window.width, window.height)
                            ],
                            "bbox": list(rasterio.windows.bounds(window, affine)),
                            "valid_pixels": count,
                            "bytes": cog.stat().st_size,
                        }
                    else:
                        stats = dict(
                            keys=np.array([], dtype=np.int64),
                            counts=np.array([], dtype=np.int64),
                            sums=np.empty((0, 4)),
                            centres=np.empty((0, 2)),
                            classes=np.empty((0, 2, 5)),
                        )
                    np.savez_compressed(checkpoint, **stats)
                    dump(
                        checkpoint_meta,
                        {
                            "identity": identity,
                            "entry": entry,
                            "cog_sha256": digest(cog) if entry else None,
                            "stats_sha256": digest(checkpoint),
                        },
                    )
                if entry:
                    sectors.append(entry)
                for index, key in enumerate(stats["keys"]):
                    key = int(key)
                    if key not in merged:
                        merged[key] = [
                            0,
                            np.zeros(4),
                            np.zeros(2),
                            np.zeros((2, 5), dtype=np.int64),
                        ]
                    group = merged[key]
                    group[0] += int(stats["counts"][index])
                    for target, source in zip(
                        group[1:],
                        (
                            stats["sums"][index],
                            stats["centres"][index],
                            stats["classes"][index],
                        ),
                    ):
                        target += source
                dump(
                    CACHE / "progress.json",
                    {
                        "completed_sectors": done,
                        "total_sectors": total,
                        "valid_pixels": sum(entry["valid_pixels"] for entry in sectors),
                        "identity": identity,
                    },
                )
                if done % 5 == 0 or done == total:
                    print(
                        f'Setores: {done}/{total}; {len(sectors)} com dados; {sum(s["valid_pixels"] for s in sectors):,} pixels conferidos.',
                        flush=True,
                    )
        count = sum(entry["valid_pixels"] for entry in sectors)
        expected = evaluation["random_forest"][-1]["metrics"]["n"]
        if count != expected or sum(v[0] for v in merged.values()) != count:
            raise ValueError(f"Cobertura divergente: {count}, esperado {expected}.")
        boundary_utm = transform_geometry(
            shape(boundary["geometry"]), project.transform, interleaved=False
        )
        features = []
        for key, (n, sums, centres, classes) in sorted(merged.items()):
            tx, ty = divmod(key, 10000)
            square = box(
                tx * GRID_METRES,
                ty * GRID_METRES,
                (tx + 1) * GRID_METRES,
                (ty + 1) * GRID_METRES,
            )
            clipped = square.intersection(boundary_utm)
            # Não descartar pixels válidos que extrapolem ligeiramente o limite cartográfico.
            geometry = (
                clipped
                if not clipped.is_empty
                and clipped.geom_type in ("Polygon", "MultiPolygon")
                else square
            )
            properties = {
                "id": f"AC-5KM-E{tx:03d}N{ty:04d}",
                "centroid": (centres / n).tolist(),
                "n_source_pixels": n,
                "aggregation": "mean",
            }
            for model_index, model in enumerate(MODELS):
                properties[f"value_{model}"] = float(sums[model_index * 2] / n)
                properties[f"percentile_{model}"] = float(sums[model_index * 2 + 1] / n)
                if classes[model_index].sum() != n:
                    raise ValueError("Distribuição de classes incompleta.")
                for class_index, category in enumerate(CLASSES):
                    properties[f"share_{model}_{category[0]}"] = float(
                        classes[model_index, class_index] / n
                    )
            features.append(
                {
                    "type": "Feature",
                    "id": properties["id"],
                    "properties": properties,
                    "geometry": mapping(
                        transform_geometry(
                            geometry, inverse_project.transform, interleaved=False
                        )
                    ),
                }
            )
        audit_samples(sources, affine, project, merged)
        index = {
            "schema_version": "4.0",
            "year": year,
            "crs": "EPSG:4326",
            "width": reference.width,
            "height": reference.height,
            "transform": list(affine)[:6],
            "sector_size": SIZE,
            "bands": [
                "value_random_forest",
                "percentile_random_forest",
                "value_xgboost",
                "percentile_xgboost",
            ],
            "valid_pixels": count,
            "sectors": sectors,
        }
        manifest = {
            "schema_version": "4.0",
            "product": "wildfire_annual_risk",
            "label": f"Risco anual experimental — {year}",
            "year": year,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "default_model": "random_forest",
            "scenario": "AB30C_suave",
            "training": {
                "years": [2016, year - 1],
                "climate_year": year - 1,
                "fire_source": "MapBiomas Fogo 5.1",
                "predictors": reports[0]["colunas"],
                "climate_smoothing": True,
            },
            "models": [
                {
                    "id": model,
                    "label": label,
                    "value_property": f"value_{model}",
                    "percentile_property": f"percentile_{model}",
                    "value_unit": "percent",
                    "calibrated": model == "random_forest",
                    "value_label": (
                        "Estimativa calibrada do modelo"
                        if model == "random_forest"
                        else "Escore corrigido por amostragem, não calibrado"
                    ),
                    "calibration": report["calibracao"],
                    "sampling": report["amostragem"],
                }
                for model, label, report in zip(MODELS, LABELS, reports)
            ],
            "percentile": {
                "domain": [0, 100],
                "origin": "received_histogram_statewide",
                "aggregation": "mean_of_received_pixel_percentiles",
            },
            "representation": {
                "grid_size_m": GRID_METRES,
                "grid_crs": "EPSG:31979",
                "aggregation": "mean",
                "native_resolution_m": 30,
                "native_zoom": 8.5,
                "class_share_semantics": "fraction_of_valid_source_pixels",
            },
            "classes": [
                {"id": c[0], "label": c[1], "lower": c[2], "upper": c[3], "color": c[4]}
                for c in CLASSES
            ],
            "counts": {
                "source_pixels": count,
                "features": len(features),
                "sectors": len(sectors),
            },
            "bounds": list(reference.bounds),
            "files": {
                "grid": "grid.geojson",
                "boundary": "boundary.geojson",
                "index": "index.json",
            },
            "evaluation": {
                "origin": "received_professor",
                "level": "30m_fogo",
                "target_year_available": year == 2025,
                "historical": evaluation,
            },
            "provenance": {
                "identity": identity,
                "sources": provenance,
                "reports": report_files,
                "importer_sha256": digest(Path(__file__)),
                "contract": CONTRACT,
                "rasterio": rasterio.__version__,
                "pyproj": pyproj.__version__,
                "source_values_unchanged": True,
            },
        }
        dump(
            staging / "grid.geojson",
            {"type": "FeatureCollection", "features": features},
        )
        dump(staging / "boundary.geojson", boundary)
        dump(staging / "index.json", index)
        dump(staging / "manifest.json", manifest)
    finally:
        for source in sources:
            source.close()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    backup = CACHE / f"previous-product-{time.time_ns()}"
    if OUTPUT.exists():
        OUTPUT.replace(backup)
    try:
        staging.replace(OUTPUT)
    except BaseException:
        if backup.exists():
            backup.replace(OUTPUT)
        raise
    print(
        f"PUBLICADO: {len(features)} grupos de 5 km, {count:,} pixels, {len(sectors)} COGs ({reused} reutilizados por checkpoint). {OUTPUT}",
        flush=True,
    )


def audit_samples(sources, affine, project, merged):
    keys = sorted(merged)
    for key in (keys[len(keys) // 5], keys[len(keys) // 2], keys[4 * len(keys) // 5]):
        tx, ty = divmod(key, 10000)
        back = pyproj.Transformer.from_crs(31979, 4326, always_xy=True)
        corners = [
            back.transform(x, y)
            for x, y in (
                (tx * 5000, ty * 5000),
                ((tx + 1) * 5000, ty * 5000),
                ((tx + 1) * 5000, (ty + 1) * 5000),
                (tx * 5000, (ty + 1) * 5000),
            )
        ]
        lon, lat = zip(*corners)
        w = from_bounds(min(lon), min(lat), max(lon), max(lat), affine)
        c0, r0 = max(0, int(np.floor(w.col_off)) - 1), max(
            0, int(np.floor(w.row_off)) - 1
        )
        c1, r1 = min(sources[0].width, int(np.ceil(w.col_off + w.width)) + 1), min(
            sources[0].height, int(np.ceil(w.row_off + w.height)) + 1
        )
        window = Window(c0, r0, c1 - c0, r1 - r0)
        values, mask = read_sources(sources, window)
        stats = aggregate_block(values, mask, window, affine, project)
        index = np.flatnonzero(stats["keys"] == key)[0]
        expected = merged[key]
        if (
            stats["counts"][index] != expected[0]
            or not np.allclose(stats["sums"][index], expected[1], rtol=1e-10, atol=1e-7)
            or not np.array_equal(stats["classes"][index], expected[3])
        ):
            raise ValueError(f"Recálculo de grupo agregado divergente: {key}")
    print(
        "Auditoria: máscaras e domínios completos, COGs sem perda, cobertura e recálculo de três grupos aprovados.",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=REPO / "entrega_professor_v4/mapas_geotiff"
    )
    parser.add_argument(
        "--reports-root",
        type=Path,
        default=REPO / "entrega_professor_v4/2_resultados/treino_MapBiomas_Fogo",
    )
    parser.add_argument("--year", type=int, choices=(2025, 2026), default=2026)
    args = parser.parse_args()
    build(args.source_root, args.reports_root, args.year)
