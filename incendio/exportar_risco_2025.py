"""Reproduz risco anual 2025, com parâmetros auditados e checkpoints locais."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits
from risco_anual import geometria as web
from risco_anual.pipeline import ajuste, config, fontes, modelos, risco
from risco_anual.treino import chave_para

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "produtos/risco/v1/2025"
MODEL_NAMES = dict(zip(web.MODELS, ("GradBoost", "RandomForest", "RegLogistica", "FuzzyKNN", "XGBoost")))
LABELS = dict(zip(web.MODELS, ("GradBoost", "Random Forest", "Regressão logística", "Fuzzy k-NN", "XGBoost")))

def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()

def validate_scores(scores):
    if len(scores) != 307410 or scores[["X", "Y"]].duplicated().any():
        raise ValueError("Grade científica incompleta ou duplicada.")
    for column in web.SCORE_COLUMNS:
        values = scores[column].to_numpy(dtype=float)
        if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
            raise ValueError(f"Escore inválido: {column}")

def checkpoint_valid(path, metadata):
    meta = path.with_suffix(".json")
    if not path.exists() or not meta.exists():
        return False
    try:
        saved = json.loads(meta.read_text())
        values = np.load(path, allow_pickle=False)
    except (OSError, ValueError, EOFError):
        return False
    if saved != metadata:
        return False
    return values.shape == (metadata["cell_count"],) and np.isfinite(values).all() and ((values >= 0) & (values <= 1)).all()

def validate_product(root=OUTPUT, scores=None):
    manifest = json.loads((root / "aggregated/manifest.json").read_text())
    collection = json.loads((root / "aggregated/mapa.geojson").read_text())
    features = collection["features"]
    if len(features) != 212 or sum(f["properties"]["n_source_cells"] for f in features) != 307410:
        raise ValueError("Cobertura agregada incorreta.")
    if manifest["source_period"] != "2025" or manifest["training"]["climate_year"] != 2024:
        raise ValueError("Protocolo temporal incorreto.")
    bounds = web.geometry_bounds(web.carregar_limite()["geometry"])
    if scores is not None:
        rows, cols = web.sector_indices(scores.lon, scores.lat, bounds)
        ids = np.array([web.sector_id(int(r), int(c)) for r, c in zip(rows, cols)])
        for feature in features:
            subset = scores.loc[ids == feature["properties"]["id"]]
            for column in web.SCORE_COLUMNS:
                if not np.isclose(subset[column].astype(np.float64).mean(), feature["properties"][column], atol=6e-8, rtol=0):
                    raise ValueError("Média agregada divergente.")
    seen, total = set(), 0
    index = json.loads((root / "native_sharded_grid/index.json").read_text())
    aggregate_by_id = {f["properties"]["id"]: f for f in features}
    for entry in index["sectors"]:
        sector = json.loads((root / "native_sharded_grid" / entry["url"]).read_text())
        if len(sector["features"]) != entry["feature_count"]:
            raise ValueError("Setor incompleto.")
        for feature in sector["features"]:
            props = feature["properties"]
            if props["id"] in seen:
                raise ValueError("ID nativo duplicado.")
            seen.add(props["id"])
            for column in web.SCORE_COLUMNS:
                value = props[column]
                if not isinstance(value, (int, float)) or not np.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError("Escore nativo inválido.")
        for column in web.SCORE_COLUMNS:
            mean = np.mean([f["properties"][column] for f in sector["features"]])
            if not np.isclose(mean, aggregate_by_id[entry["id"]]["properties"][column], atol=1e-7, rtol=0):
                raise ValueError("Média nativa/agregada divergente.")
        total += entry["feature_count"]
    if total != 307410 or len(seen) != total or index["feature_count"] != total:
        raise ValueError("Cobertura nativa incorreta.")
    print("Auditoria aprovada: 212 setores, 307410 IDs únicos e dez médias/escores.", flush=True)

def export(cfg_path):
    cfg = config.carregar(cfg_path)
    if (cfg.semente != 42 or cfg.defasagem_principal != 1
            or cfg.preditores != ("veg", "dist_estrada", "dist_agua", "altitude", "ur_media_ano", "prec_acum_ano")
            or cfg.divisao != {"tipo": "corte_x_g", "valor_m": 337100}
            or cfg.agrupamento != "ano" or cfg.n_pastas != 10):
        raise ValueError("Configuração científica incompatível com o contrato anual de 2025.")
    base = fontes.carregar_base(cfg)
    regions = risco.regiao_de(base.est, cfg.divisao)
    winners = json.loads((BASE / "risco_anual/parametros_2025.json").read_text())
    paths = [cfg.centroides, *cfg.cicatriz, *cfg.precipitacao, *cfg.umidade, *cfg.conferir]
    sources = [{"file": p.name, "sha256": sha256(p)} for p in paths]
    source_hash = fingerprint(sources)
    cache = cfg.saida / "checkpoints"
    cache.mkdir(parents=True, exist_ok=True)
    scores = base.est[["X", "Y", "x_g", "y_g2", "lon", "lat"]].copy()
    score_parts, provenance = {}, {}
    # Fast models first; all five must finish before publication.
    for scope in ("acre", "oeste", "leste"):
        tab = risco.tabela_treino(base, regions, scope, list(range(2007, 2025)), 1, 42)
        X, y, years = risco.matriz_janela(tab, cfg.preditores, 2024)
        if set(years) != set(range(2007, 2025)) or years.max() >= 2025:
            raise ValueError("Janela de treino incompleta ou vazamento temporal.")
        cells = np.arange(len(base.est)) if scope == "acre" else np.flatnonzero(regions == scope)
        predict = risco.matriz_predicao(base, cfg.preditores, 2025, 1, cells)
        for model_id in ("random_forest", "gradboost", "logistic_regression", "xgboost", "fuzzy_knn"):
            name = MODEL_NAMES[model_id]
            candidates = modelos.candidatos(name, cfg.espacos)
            key = chave_para(cfg, name, scope, 2024, 1, X, y, years, candidates)
            received = winners["winners"][f"{name}/{scope}"]
            from dataclasses import asdict
            mismatches = [field for field, value in asdict(key).items()
                          if field != "fonte_cicatriz" and str(value) != str(received[field])]
            expected_sources = [Path(p).name for p in received["fonte_cicatriz"].split("+")]
            if [p.name for p in cfg.cicatriz] != expected_sources:
                mismatches.append("fonte_cicatriz")
            parameters = received["parametros"]
            selection = "received_verified"
            selection_cv_pr_auc = float(received["pr_auc_media"])
            if mismatches:
                print(f"Reajustando {name}/{scope}: divergências {mismatches}", flush=True)
                tuned = cache / f"{model_id}_{scope}_selection.json"
                tuning_key = fingerprint(asdict(key))
                saved = json.loads(tuned.read_text()) if tuned.exists() else {}
                if saved.get("key") == tuning_key:
                    parameters = saved["parameters"]
                    selection_cv_pr_auc = saved.get("pr_auc")
                else:
                    folds = ajuste.pastas(years, y, cfg.agrupamento, cfg.n_pastas, cfg.semente)
                    result = ajuste.buscar(name, X, y, years, 2024, candidates, 42, cfg.preditores, folds, 1, cfg.metrica, f"{name}/{scope}")
                    parameters = json.loads(result.candidatos.loc[result.candidatos["ordem"] == result.ordem_vencedor, "parametros"].iloc[0])
                    selection_cv_pr_auc = float(result.candidatos.loc[result.candidatos["ordem"] == result.ordem_vencedor, "pr_auc_media"].iloc[0])
                    web._json_dump(tuned, {"key": tuning_key, "parameters": parameters, "pr_auc": selection_cv_pr_auc})
                selection = "reselected_same_protocol"
            metadata = {"schema_version": "1.0", "model": model_id, "scope": scope,
                        "parameters": parameters, "predictors": list(cfg.preditores),
                        "seed": 42, "train_years": [2007, 2024], "climate_year": 2024,
                        "target_year": 2025, "table_hash": key.impressao_tabela,
                        "sources_hash": source_hash, "cell_order_hash": hashlib.sha256(cells.tobytes()).hexdigest(),
                        "cell_count": len(cells), "backend": "exact_euclidean" if model_id == "fuzzy_knn" else name,
                        "python": platform.python_version(), "sklearn": sklearn.__version__, "xgboost": "3.2.0",
                        "selection": selection}
            metadata["model_code_sha256"] = sha256(BASE / "risco_anual/pipeline/modelos.py")
            metadata["prediction_hash"] = hashlib.sha256(np.ascontiguousarray(predict, dtype=np.float64).tobytes()).hexdigest()
            checkpoint = cache / f"{model_id}_{scope}.npy"
            if not checkpoint_valid(checkpoint, metadata):
                print(f"Treinando/previsão {name}/{scope}: {len(X)} amostras; {len(cells)} células", flush=True)
                estimator = modelos.criar(name, parameters, 42, cfg.preditores)
                estimator.fit(X, y)
                # Bound exact fuzzy distance matrices to available RAM, without changing neighbours.
                if model_id == "fuzzy_knn":
                    estimator.steps[-1][1].bloco = 256
                values = estimator.predict_proba(predict)[:, 1]
                if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
                    raise ValueError("Previsões inválidas.")
                temporary = checkpoint.with_suffix(".tmp")
                with temporary.open("wb") as stream:
                    np.save(stream, values, allow_pickle=False)
                temporary.replace(checkpoint)
                web._json_dump(checkpoint.with_suffix(".json"), metadata)
            values = np.load(checkpoint, allow_pickle=False)
            score_parts[(model_id, scope)] = (cells, values)
            provenance[f"{model_id}/{scope}"] = metadata | {"balanced_cv_pr_auc_received": float(received["pr_auc_media"]),
                                                         "balanced_cv_pr_auc": selection_cv_pr_auc}
            print(f"Checkpoint concluído: {model_id}/{scope}", flush=True)
        del tab, X, y, predict
    for model in web.MODELS:
        scores[f"score_unico_{model}"] = score_parts[(model, "acre")][1]
        scores[f"score_regional_{model}"] = risco.juntar_regional(
            {s: score_parts[(model, s)] for s in ("oeste", "leste")}, len(scores), model)[0]
    validate_scores(scores)
    scores.to_parquet(cfg.saida / "scores_2025.parquet", index=False)
    target = base.est.queimou_2025.to_numpy(dtype=bool)
    evaluations = {scenario: {model: modelos.avaliar(target, scores[f"score_{scenario}_{model}"].to_numpy())
                              for model in web.MODELS} for scenario in web.SCENARIOS}
    received_evaluation = json.loads((BASE / "risco_anual/avaliacao_recebida.json").read_text())["metrics"]
    reproduction_audit = []
    for row in received_evaluation["avaliacao"]:
        if row["ano"] == 2025:
            model = next(key for key, name in MODEL_NAMES.items() if name == row["modelo"])
            for metric in ("roc_auc", "pr_auc"):
                matching_received = all(provenance[f"{model}/{scope}"]["selection"] == "received_verified"
                                        for scope in (("acre",) if row["cenario"] == "unico" else ("oeste", "leste")))
                difference = float(evaluations[row["cenario"]][model][metric] - row[metric])
                matched = bool(np.isclose(difference, 0, atol=5e-5, rtol=0))
                reproduction_audit.append({"model": model, "scenario": row["cenario"], "metric": metric,
                                           "received": row[metric], "recalculated": evaluations[row["cenario"]][model][metric],
                                           "difference": difference, "within_tolerance": matched,
                                           "parameters_verified": matching_received})
                if matching_received and not matched and model != "xgboost":
                    raise ValueError(f"Avaliação recebida divergente: {model}/{row['cenario']}/{metric}")
                if matching_received and not matched and model == "xgboost":
                    print(f"AVISO XGBoost retreinado: {row['cenario']}/{metric}, delta={difference}. Preservando métricas recebidas e recalculadas separadamente.", flush=True)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {
        "schema_version": "1.0", "product": "wildfire_annual_risk",
        "label": "Risco anual experimental — 2025", "generated_at": generated,
        "source_period": "2025", "crs": "EPSG:4326", "default_model": "random_forest",
        "default_scenario": "regional",
        "scenarios": [{"id": "unico", "label": "Acre inteiro"}, {"id": "regional", "label": "Oeste–Leste"}],
        "regional_division": {"crs": "EPSG:31979", "west_when_x_less_than_m": 337100, "administrative_boundary": False},
        "models": [{"id": m, "label": LABELS[m], "property": f"score_regional_{m}",
                    "properties": {s: f"score_{s}_{m}" for s in web.SCENARIOS},
                    "validation": {"protocol": "group_kfold_by_year_balanced", "folds": 10, "roc_auc": None, "pr_auc": None,
                                   "pr_auc_by_scope": {scope: provenance[f"{m}/{scope}"]["balanced_cv_pr_auc"] for scope in ("acre", "oeste", "leste")}}}
                   for m in web.MODELS],
        "value": {"semantics": "relative_score", "domain": [0, 1], "calibrated_probability": False},
        "training": {"target": "burned_in_2025", "sample": "balanced_per_year_1_to_1", "seed": 42,
                     "predictors": list(cfg.preditores), "train_years": [2007, 2024], "climate_year": 2024,
                     "evaluation": "target_year_held_out", "source_coverage": [2006, 2025]},
        "original_grid": {"crs": "EPSG:31979", "cell_width_m": web.WIDTH_M,
                          "cell_height_m": web.HEIGHT_M, "cell_count": len(scores)},
        "provenance": {"sources": sources, "models": provenance, "code_sha256": sha256(Path(__file__)),
                       "runtime": {"platform": platform.platform(), "python": platform.python_version(),
                                   "threadpool_limit": 4, "selection_environment": winners["selection_environment"]}},
        "evaluation": {"historical_test_2025": evaluations, "test_positive_cells": int(target.sum()),
                       "received_historical_2016": [r for r in received_evaluation["avaliacao"] if r["ano"] == 2016],
                       "received_rolling_2017_2024": received_evaluation["avaliacao_rolante"],
                       "received_test_2025": [r for r in received_evaluation["avaliacao"] if r["ano"] == 2025],
                       "reproduction_audit": reproduction_audit,
                       "reproduction_notice": "XGBoost retreinado no ambiente atual não é bit a bit idêntico ao relatório recebido; métricas atuais são recalculadas, nunca copiadas.",
                       "notice": "Métricas em território completo não são comparáveis diretamente à CV balanceada. Poucas células positivas em 2025; não são contagem de incêndios."},
        "limitations": ["Paisagem derivada de insumos 2003–2013.", "Possível descontinuidade na divisão Oeste–Leste.", "Escores não calibrados, não operacionais."]
    }
    staging = OUTPUT.with_name("2025-staging")
    if staging.exists():
        shutil.rmtree(staging)
    boundary = web.carregar_limite()
    web.exportar_agregado(scores, boundary, generated, staging / "aggregated", manifest)
    web.exportar_nativo(scores, boundary, generated, staging / "native_sharded_grid", manifest)
    validate_product(staging, scores)
    backup = OUTPUT.with_name("2025-previous")
    if OUTPUT.exists():
        if backup.exists():
            raise FileExistsError(f"Backup anterior precisa ser preservado/arquivado: {backup}")
        OUTPUT.rename(backup)
    staging.rename(OUTPUT)
    print(f"Produto publicado localmente: {OUTPUT}", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=BASE / "risco_anual/config_2025.json")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        validate_product() if args.validate_only else export(args.config)
