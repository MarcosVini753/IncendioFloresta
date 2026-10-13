"""Reproduz as 16 combinações de risco 2025 da entrega do professor v2.

Execução retomável; a publicação só acontece após a auditoria integral.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sklearn
import xgboost
import rasterio
from threadpoolctl import threadpool_limits

from risco_anual_v2 import geometria as web
from risco_anual_v2.pipeline import ajuste, avaliacao, config, fontes, modelos, rodada_v2

BASE = Path(__file__).resolve().parent
MODULE = BASE / "risco_anual_v2"
OUTPUT = BASE / "produtos/risco/v2/2025"
NAMES = dict(zip(web.MODELS, ("GradBoost", "RandomForest", "RegLogistica", "XGBoost")))
LABELS = dict(zip(web.MODELS, ("GradBoost", "Random Forest", "Regressão logística", "XGBoost")))
SCENARIOS = dict(zip(web.SCENARIOS, ("Todas as células", "Oeste–Leste", "Amostra 1:19", "Todas + histórico de queimadas")))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    web._json_dump(temporary, value)
    temporary.replace(path)


def checkpoint_valid(path, metadata):
    try:
        if json.loads(path.with_suffix(".json").read_text()) != metadata:
            return False
        values = np.load(path, allow_pickle=False)
        return values.shape == (metadata["cell_count"],) and np.isfinite(values).all() and ((values >= 0) & (values <= 1)).all()
    except (OSError, ValueError, EOFError):
        return False


def normalize_key(key):
    result = dict(key)
    result["fonte_cicatriz"] = "+".join(Path(p).name for p in result["fonte_cicatriz"].split("+"))
    options = json.loads(result["opcoes_modelo"])
    options.pop("dispositivo_xgboost", None)  # backend, não protocolo científico
    result["opcoes_modelo"] = json.dumps(options, sort_keys=True)
    return {k: str(v) for k, v in result.items()}


def parameters_for(dados, scenario, name, receipt, cache):
    source = dados.v2.fonte_parametros(scenario)
    candidates = modelos.candidatos(name, dados.cfg.espacos, incluir_padrao=False)
    key = asdict(rodada_v2.chave_v2(dados, name, source, "acre", 2024, candidates))
    received = next(r for r in receipt["winners"] if r["modelo"] == name and r["amostragem"] == source.amostragem.texto())
    expected = normalize_key({k: received[k] for k in key})
    current = normalize_key(key)
    mismatches = [k for k in current if current[k] != expected[k]]
    parameters = json.loads(received["parametros"])
    selection, cv = "received_verified", float(received["pr_auc_media"])
    if mismatches:
        print(f"Reajuste necessário: {name}/{source.nome}: {mismatches}", flush=True)
        selection_path = cache / f"selection_{source.nome}_{name}.json"
        selection_key = fingerprint(key)
        saved = json.loads(selection_path.read_text()) if selection_path.exists() else {}
        if saved.get("key") == selection_key:
            parameters, cv = saved["parameters"], saved["pr_auc"]
        else:
            table = dados.tabela("acre", source.historico)
            end = table.fim(2024)
            mask = dados.mascara("acre", source.amostragem)[:end]
            folds = ajuste.pastas_mapa_inteiro(table.ano[:end], table.y[:end], mask, 10, 42)
            result = ajuste.buscar(name, table.X[:end], table.y[:end], table.ano[:end], 2024, candidates, 42,
                                   dados.colunas(source), folds, 1, "pr_auc", f"{name}/{source.nome}", dados.v2.opcoes_modelo)
            row = result.candidatos.loc[result.candidatos.ordem == result.ordem_vencedor].iloc[0]
            parameters, cv = json.loads(row.parametros), float(row.pr_auc_media)
            if not np.isfinite(cv):
                raise ValueError("Seleção sem métricas finitas.")
            atomic_json(selection_path, {"key": selection_key, "parameters": parameters, "pr_auc": cv})
        selection = "reselected_same_protocol"
    return parameters, {"selection": selection, "parameter_source_scenario": source.nome,
                        "cv_pr_auc": cv, "cv_protocol": "group_kfold_by_year_full_map",
                        "key": key, "mismatches": mismatches, "received_backend": "cuda" if name == "XGBoost" else "cpu", "backend": "cpu"}


def verify_observations(sources):
    old = json.loads((BASE / "produtos/risco/v1/2025/aggregated/manifest.json").read_text())
    previous = {s["file"]: s["sha256"] for s in old["provenance"]["sources"]}
    names = ("Umidade_Relativa_Diaria_Acre_2016_2026.tif", "Precipitacao_13h_Diaria_Acre_2016_2026.tif", "Cicatrizes_Acre_2006_2025.tif")
    current = {s["file"]: s["sha256"] for s in sources}
    return {name: {"sha256": current[name], "matches_previous": current[name] == previous.get(name)} for name in names}


def validate_product(root, native_scores=None):
    manifest = json.loads((root / "aggregated/manifest.json").read_text())
    collection = json.loads((root / "aggregated/mapa.geojson").read_text())
    index = json.loads((root / "native_sharded_grid/index.json").read_text())
    aggregates = {f["properties"]["id"]: f["properties"] for f in collection["features"]}
    if manifest["schema_version"] != "2.0" or len(aggregates) != 212 or sum(p["n_source_cells"] for p in aggregates.values()) != 307410:
        raise ValueError("Cobertura ou contrato agregado incorreto.")
    if manifest["training"]["train_years"] != [2007, 2024] or manifest["training"]["climate_year"] != 2024:
        raise ValueError("Protocolo temporal incorreto.")
    if manifest["representation"].get("color_aggregation") != "max" or manifest["representation"].get("color_property_prefix") != "max_":
        raise ValueError("A cor agregada deve representar o maior percentil nativo.")
    seen = set()
    for entry in index["sectors"]:
        features = json.loads((root / "native_sharded_grid" / entry["url"]).read_text())["features"]
        if len(features) != entry["feature_count"] or len(features) != aggregates[entry["id"]]["n_source_cells"]:
            raise ValueError("Contagem do setor inválida.")
        for feature in features:
            props = feature["properties"]
            if props["id"] in seen:
                raise ValueError("ID científico repetido.")
            seen.add(props["id"])
        for column in web.SCORE_COLUMNS:
            values = np.asarray([f["properties"][column] for f in features], dtype=float)
            limit = 100 if column.startswith("percentile_") else 1
            if not np.isfinite(values).all() or ((values < 0) | (values > limit)).any():
                raise ValueError(f"Domínio inválido: {column}")
            if not np.isclose(values.mean(), aggregates[entry["id"]][column], atol=2e-8, rtol=0):
                raise ValueError(f"Média agregada divergente: {entry['id']}/{column}")
            if column in web.PERCENTILE_COLUMNS:
                maximum = aggregates[entry["id"]][f"max_{column}"]
                if not np.isfinite(maximum) or not np.isclose(values.max(), maximum, atol=2e-8, rtol=0):
                    raise ValueError(f"Máximo visual divergente: {entry['id']}/{column}")
    if len(seen) != 307410 or index["feature_count"] != 307410:
        raise ValueError("Grade científica incompleta.")
    if native_scores is not None:
        for scenario in web.SCENARIOS:
            for model in web.MODELS:
                expected = avaliacao.indice_percentil(native_scores[f"score_{scenario}_{model}"].to_numpy())
                if not np.allclose(expected, native_scores[f"percentile_{scenario}_{model}"], atol=1e-10, rtol=0):
                    raise ValueError("Percentil não corresponde ao ranking estadual.")
    print("Auditoria aprovada: 16 combinações, 212 médias e máximos visuais, 307410 IDs únicos, escores e percentis.", flush=True)


def export(cfg_path):
    cfg = config.carregar(cfg_path)
    if cfg.versao != 2 or cfg.semente != 42 or cfg.defasagem_principal != 1 or cfg.v2.interpolacao != "bilinear":
        raise ValueError("Configuração científica incompatível.")
    receipt = json.loads((MODULE / "recebido.json").read_text())
    cache = cfg.saida / "checkpoints"
    cache.mkdir(parents=True, exist_ok=True)
    sources = [{"file": p.name, "sha256": sha256(p)} for p in (cfg.centroides, *cfg.cicatriz, *cfg.precipitacao, *cfg.umidade, *cfg.conferir)]
    observations = verify_observations(sources)
    base = fontes.carregar_base(cfg)
    scores = base.est[["X", "Y", "x_g", "y_g2", "lon", "lat"]].copy()
    if len(scores) != 307410 or scores[["X", "Y"]].duplicated().any():
        raise ValueError("Grade científica incompleta.")
    y_test = base.est.queimou_2025.to_numpy(dtype=np.int8)
    provenance, metrics, audit = {}, {}, []
    science_hash = fingerprint({p.name: sha256(p) for p in sorted((MODULE / "pipeline").glob("*.py"))})
    runtime = {"python": platform.python_version(), "numpy": np.__version__, "sklearn": sklearn.__version__, "xgboost": xgboost.__version__, "rasterio": rasterio.__version__, "backend": "cpu", "threads": 2}
    modelos.THREADS_FLORESTA = 2
    for scenario in cfg.v2.cenarios:
        dados = rodada_v2.Dados(cfg, base, 2024)
        if dados.anos_treino != tuple(range(2007, 2025)):
            raise ValueError("Treino deve conter somente 2007–2024.")
        metrics[scenario.nome] = {}
        for model_id in web.MODELS:
            name = NAMES[model_id]
            parameters, selection = parameters_for(dados, scenario, name, receipt, cache)
            values = np.full(len(scores), np.nan)
            for scope in scenario.escopos:
                X, y, beta = dados.treino(scope, scenario, 2024)
                cells = np.arange(len(scores)) if scope == "acre" else np.flatnonzero(dados.regiao == scope)
                predict = dados.matriz_alvo(scope, scenario, 2025)
                metadata = {"schema_version": "2.0", "scenario": scenario.nome, "model": model_id, "scope": scope,
                            "seed": 42, "predictors": list(dados.colunas(scenario)), "train_years": [2007, 2024], "target_year": 2025,
                            "climate_year": 2024, "sampling": scenario.amostragem.texto(), "beta": beta,
                            "parameters": parameters, "selection": selection, "runtime": runtime,
                            "sources_hash": fingerprint(sources), "science_code_hash": science_hash,
                            "cell_count": len(cells), "cell_order_hash": hashlib.sha256(cells.tobytes()).hexdigest(),
                            "table_hash": dados.impressao(scope, scenario.historico, scenario.amostragem, 2024),
                            "prediction_hash": hashlib.sha256(np.ascontiguousarray(predict, dtype=np.float64).tobytes()).hexdigest()}
                path = cache / f"{scenario.nome}_{model_id}_{scope}.npy"
                if checkpoint_valid(path, metadata):
                    print(f"CHECKPOINT {scenario.nome}/{model_id}/{scope}", flush=True)
                    part = np.load(path, allow_pickle=False)
                else:
                    print(f"TREINO {scenario.nome}/{model_id}/{scope}: {len(y)} amostras, {len(cells)} células", flush=True)
                    started = time.monotonic()
                    estimator = modelos.criar(name, parameters, 42, dados.colunas(scenario), dados.v2.opcoes_modelo)
                    jobs = {k: 2 for k in estimator.get_params(deep=True) if k == "n_jobs" or k.endswith("__n_jobs")}
                    if jobs:
                        estimator.set_params(**jobs)
                    estimator.fit(X, y)
                    part = estimator.predict_proba(predict)[:, 1]
                    if scenario.amostragem.amostrada:
                        part = avaliacao.corrigir_prior(part, beta)
                    if not np.isfinite(part).all() or ((part < 0) | (part > 1)).any():
                        raise ValueError("Previsão inválida; checkpoint não será salvo.")
                    temporary = path.with_suffix(".tmp.npy")
                    np.save(temporary, part, allow_pickle=False)
                    temporary.replace(path)
                    atomic_json(path.with_suffix(".json"), metadata)
                    print(f"CONCLUÍDO {scenario.nome}/{model_id}/{scope}: {time.monotonic()-started:.1f}s", flush=True)
                    del estimator
                values[cells] = part
                provenance[f"{scenario.nome}/{model_id}/{scope}"] = metadata
                del X, y, predict, part
                gc.collect()
            if not np.isfinite(values).all():
                raise ValueError("Previsão estadual incompleta.")
            scores[f"score_{scenario.nome}_{model_id}"] = values
            scores[f"percentile_{scenario.nome}_{model_id}"] = avaliacao.indice_percentil(values)
            measured = modelos.avaliar(y_test, values)
            if not all(np.isfinite(v) for v in measured.values()):
                raise ValueError("Avaliação inválida.")
            metrics[scenario.nome][model_id] = measured
            received = next(r for r in receipt["test_2025"] if r["cenario"] == scenario.nome and r["modelo"] == name)
            audit.append({"scenario": scenario.nome, "model": model_id, "received_backend": "cuda" if name == "XGBoost" else "cpu", "runtime_backend": "cpu",
                          "metrics": {k: {"received": float(received[k]), "recalculated": v, "difference": v-float(received[k])} for k,v in measured.items()}})
            atomic_json(cache.parent / "progress.json", {"completed_combinations": sum(len(m) for m in metrics.values()), "total_combinations": 16, "latest": f"{scenario.nome}/{model_id}", "updated_at": datetime.now(timezone.utc).isoformat()})
        del dados
        gc.collect()
    del base
    gc.collect()
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {
        "schema_version": "2.0", "product": "wildfire_annual_risk", "label": "Risco anual experimental — 2025 · professor v2",
        "generated_at": generated, "source_period": "2025", "crs": "EPSG:4326", "default_model": "random_forest", "default_scenario": "todos_historico",
        "scenarios": [{"id": s.nome, "label": SCENARIOS[s.nome], "sampling": s.amostragem.texto(), "history": s.historico, "parameter_source_scenario": cfg.v2.fonte_parametros(s).nome} for s in cfg.v2.cenarios],
        "models": [{"id": m, "label": LABELS[m], "property": f"score_todos_historico_{m}", "properties": {s: f"score_{s}_{m}" for s in web.SCENARIOS}, "percentile_properties": {s: f"percentile_{s}_{m}" for s in web.SCENARIOS}, "validation": {"protocol": "group_kfold_by_year_full_map", "folds": 10}} for m in web.MODELS],
        "value": {"semantics": "relative_score", "domain": [0, 1], "calibrated_probability": False},
        "percentile": {"semantics": "statewide_rank_percentile", "domain": [0, 100], "ties": "average", "population": 307410, "aggregation": "mean_of_native_percentiles", "notice": "Posição relativa no ranking de risco; não é chance de incêndio."},
        "training": {"target": "burned_in_2025", "seed": 42, "predictors": list(cfg.preditores), "history_predictors": list(rodada_v2.risco.COLUNAS_HISTORICO), "history": dict(cfg.v2.historico), "train_years": [2007, 2024], "climate_year": 2024, "interpolation": "bilinear", "categorical_vegetation": True, "evaluation": "target_year_held_out", "source_coverage": [2006, 2025]},
        "regional_division": {"crs": "EPSG:31979", "west_when_x_less_than_m": 337100, "administrative_boundary": False},
        "original_grid": {"crs": "EPSG:31979", "cell_width_m": web.WIDTH_M, "cell_height_m": web.HEIGHT_M, "cell_count": 307410},
        "provenance": {"sources": sources, "models": provenance, "runtime": runtime, "exporter_sha256": sha256(Path(__file__)), "received_files": receipt["received_files"], "observation_sources": observations},
        "evaluation": {"historical_test_2025": metrics, "test_positive_cells": int(y_test.sum()), "received_rolling_2017_2024": [{**r, "model_id": next(m for m, name in NAMES.items() if name == r["modelo"])} for r in receipt["historical_2017_2024"]], "received_model_choices": receipt["choices"], "reproduction_audit": audit, "notice": "Teste recalculado no território completo. Relatórios históricos recebidos são identificados separadamente; poucas células positivas em 2025, não são contagem de incêndios."},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    staging = OUTPUT.with_name(f"2025-staging-{os.getpid()}")
    boundary = web.carregar_limite()
    web.exportar_agregado(scores, boundary, generated, staging / "aggregated", manifest)
    web.exportar_nativo(scores, boundary, generated, staging / "native_sharded_grid", manifest)
    validate_product(staging, scores)
    if not all(item["matches_previous"] for item in observations.values()):
        subprocess.run([sys.executable, str(BASE / "exportar_clima_2025.py"), "--sources-root", str(cfg.umidade[-1].parent), "--grid-source", str(staging / "aggregated/mapa.geojson")], check=True)
    backup = cache.parent / f"previous-product-{os.getpid()}"
    if OUTPUT.exists():
        OUTPUT.replace(backup)
    try:
        staging.replace(OUTPUT)
    except BaseException:
        if backup.exists():
            backup.replace(OUTPUT)
        raise
    print(f"PUBLICADO {OUTPUT}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=MODULE / "config_2025.json")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--validate-only", action="store_true")
    actions.add_argument("--refresh-display-maxima", action="store_true", help="Atualiza cores máximas a partir dos setores existentes, sem treinar modelos.")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        if args.refresh_display_maxima:
            web.atualizar_maximos_visuais(OUTPUT)
            validate_product(OUTPUT)
        elif args.validate_only:
            validate_product(OUTPUT)
        else:
            export(args.config)
