from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import ParameterGrid
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler
from sklearn.utils.multiclass import unique_labels
from sklearn.utils.validation import check_array, check_is_fitted, check_X_y

_FINITO = (
    {"ensure_all_finite": True}
    if "ensure_all_finite" in __import__("inspect").signature(check_array).parameters
    else {"force_all_finite": True}
)


class FuzzyKNN(ClassifierMixin, BaseEstimator):
    def __init__(self, k: int = 21, m: float = 2.0, bloco: int = 2048):
        self.k = k
        self.m = m
        self.bloco = bloco

    def fit(self, X, y):
        X, y = check_X_y(X, y, dtype=np.float64, **_FINITO)
        if self.m <= 1:
            raise ValueError(f"m deve ser > 1, recebido {self.m}")
        if self.k < 1:
            raise ValueError(f"k deve ser >= 1, recebido {self.k}")
        self.classes_ = unique_labels(y)
        self.n_features_in_ = X.shape[1]
        self.X_ = X
        self.y_idx_ = np.searchsorted(self.classes_, y)
        self._k_efetivo = min(self.k, X.shape[0])
        return self

    def predict_proba(self, X):
        check_is_fitted(self, "X_")
        X = check_array(X, dtype=np.float64, **_FINITO)
        if X.shape[1] != self.n_features_in_:
            raise ValueError(
                f"esperava {self.n_features_in_} colunas, recebeu {X.shape[1]}"
            )
        n_cls = len(self.classes_)
        k = self._k_efetivo
        expoente = 2.0 / (self.m - 1.0)
        saida = np.empty((X.shape[0], n_cls), dtype=np.float64)

        norma_treino = np.einsum("ij,ij->i", self.X_, self.X_)

        for ini in range(0, X.shape[0], self.bloco):
            lote = X[ini : ini + self.bloco]
            d2 = (
                np.einsum("ij,ij->i", lote, lote)[:, None]
                - 2.0 * lote @ self.X_.T
                + norma_treino[None, :]
            )
            np.maximum(d2, 0.0, out=d2)
            viz = np.argpartition(d2, k - 1, axis=1)[:, :k]
            d_viz = np.sqrt(np.take_along_axis(d2, viz, axis=1))
            peso = 1.0 / (d_viz**expoente + 1e-12)
            classe_viz = self.y_idx_[viz]

            num = np.zeros((lote.shape[0], n_cls))
            for c in range(n_cls):
                num[:, c] = (peso * (classe_viz == c)).sum(axis=1)
            saida[ini : ini + self.bloco] = num / num.sum(axis=1, keepdims=True)
        return saida

    def predict(self, X):
        return self.classes_[self.predict_proba(X).argmax(axis=1)]


def zoo(semente: int = 42, k_fuzzy: int = 29) -> dict[str, object]:
    from sklearn.impute import SimpleImputer

    def com_preparo(estimador):
        return Pipeline(
            [
                ("imputar", SimpleImputer(strategy="median")),
                ("escalar", StandardScaler()),
                ("modelo", estimador),
            ]
        )

    return {
        "GradBoost": HistGradientBoostingClassifier(
            max_iter=400,
            learning_rate=0.06,
            max_leaf_nodes=63,
            min_samples_leaf=40,
            l2_regularization=1.0,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=semente,
        ),
        "RandomForest": Pipeline(
            [
                ("imputar", SimpleImputer(strategy="median")),
                (
                    "modelo",
                    RandomForestClassifier(
                        n_estimators=300,
                        min_samples_leaf=5,
                        n_jobs=-1,
                        class_weight="balanced_subsample",
                        random_state=semente,
                    ),
                ),
            ]
        ),
        "RegLogistica": com_preparo(
            LogisticRegression(max_iter=2000, class_weight="balanced")
        ),
        f"FuzzyKNN_k{k_fuzzy}": com_preparo(FuzzyKNN(k=k_fuzzy, m=2.0)),
    }


def taxa_deteccao_no_topo(y, p, fracao: float) -> float:
    y = np.asarray(y)
    n_topo = max(int(round(len(p) * fracao)), 1)
    corte = np.argsort(p)[::-1][:n_topo]
    total = y.sum()
    return float(y[corte].sum() / total) if total else float("nan")


def avaliar(y, p) -> dict[str, float]:
    y = np.asarray(y)
    return {
        "prevalencia": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "det@1%": taxa_deteccao_no_topo(y, p, 0.01),
        "det@5%": taxa_deteccao_no_topo(y, p, 0.05),
        "det@10%": taxa_deteccao_no_topo(y, p, 0.10),
        "det@20%": taxa_deteccao_no_topo(y, p, 0.20),
    }


def tabela_resultados(resultados: dict[str, dict[str, float]]) -> pd.DataFrame:
    df = pd.DataFrame(resultados).T
    return df.sort_values("pr_auc", ascending=False)


@dataclass(frozen=True)
class EspecModelo:
    nome: str
    construir: Callable[..., object]
    padrao: dict
    espaco: tuple[dict, ...]
    n_jobs_busca: int
    pacote: str | None = None


class Log1pColunas(TransformerMixin, BaseEstimator):
    def __init__(self, indices: tuple[int, ...] = ()):
        self.indices = indices

    def fit(self, X, y=None):
        self.n_features_in_ = np.asarray(X).shape[1]
        return self

    def transform(self, X):
        X = np.array(X, dtype=np.float64, copy=True)
        if len(self.indices):
            colunas = list(self.indices)
            X[:, colunas] = np.log1p(X[:, colunas])
        return X


COLUNAS_DISTANCIA = ("dist_estrada", "dist_agua")
COLUNA_VEG = "veg"
MONOTONIA = "monotonia_distancias"
PESOS_CLASSE = ("balanceado", "nenhum")
DISPOSITIVOS_XGBOOST = ("cpu", "cuda")
OPCOES_PADRAO = {"veg_categorica": False, "peso_classe": "balanceado", "dispositivo_xgboost": "cpu"}
THREADS_FLORESTA = 8


def opcoes_completas(opcoes: dict | None) -> dict:
    saida = dict(OPCOES_PADRAO)
    saida.update(opcoes or {})
    if saida["peso_classe"] not in PESOS_CLASSE:
        raise ValueError(f"peso_classe deve ser 'balanceado' ou 'nenhum'; recebido {saida['peso_classe']!r}")
    if saida["dispositivo_xgboost"] not in DISPOSITIVOS_XGBOOST:
        raise ValueError(f"dispositivo_xgboost deve ser 'cpu' ou 'cuda'; recebido {saida['dispositivo_xgboost']!r}")
    return saida


def restricoes_monotonicas(colunas: Sequence[str], ligada: bool) -> list[int]:
    return [-1 if ligada and c in COLUNAS_DISTANCIA else 0 for c in colunas]


def _veg_categorica(colunas: tuple[str, ...], opcoes: dict) -> bool:
    return bool(opcoes["veg_categorica"]) and COLUNA_VEG in colunas


def _tirar_monotonia(parametros: dict, nome: str) -> tuple[dict, bool]:
    resto = dict(parametros)
    valor = resto.pop(MONOTONIA, False)
    if not isinstance(valor, bool):
        raise ValueError(f"{nome}: {MONOTONIA} deve ser booleano; recebido {valor!r}")
    return resto, valor


def _imputar() -> tuple[str, SimpleImputer]:
    return ("imputar", SimpleImputer(strategy="median"))


def para_float32(X):
    return np.asarray(X, dtype=np.float32)


def _codificar_veg(colunas: tuple[str, ...], numerico: object, dtype=np.float64) -> ColumnTransformer:
    i_veg = colunas.index(COLUNA_VEG)
    outras = [i for i in range(len(colunas)) if i != i_veg]
    categorico = Pipeline([
        ("imputar", SimpleImputer(strategy="most_frequent")),
        ("codificar", OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=dtype)),
    ])
    return ColumnTransformer([("veg", categorico, [i_veg]), ("numericas", numerico, outras)])


def _construir_fuzzy(parametros: dict, semente: int, colunas: tuple[str, ...], opcoes: dict | None = None) -> object:
    return Pipeline([_imputar(), ("escalar", StandardScaler()), ("modelo", FuzzyKNN(bloco=512, **parametros))])


def _construir_floresta(parametros: dict, semente: int, colunas: tuple[str, ...], opcoes: dict | None = None) -> object:
    if opcoes is None:
        estimador = RandomForestClassifier(
            n_estimators=300,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=semente,
            **parametros,
        )
        return Pipeline([_imputar(), ("modelo", estimador)])
    opcoes = opcoes_completas(opcoes)
    ajustes = {
        "n_estimators": 300,
        "class_weight": "balanced_subsample" if opcoes["peso_classe"] == "balanceado" else None,
        "n_jobs": THREADS_FLORESTA,
        "random_state": semente,
    }
    ajustes.update(parametros)
    estimador = RandomForestClassifier(**ajustes)
    reduzir = ("float32", FunctionTransformer(para_float32))
    if _veg_categorica(colunas, opcoes):
        preparo = _codificar_veg(colunas, SimpleImputer(strategy="median"), np.float32)
        return Pipeline([reduzir, ("preparar", preparo), ("modelo", estimador)])
    return Pipeline([reduzir, _imputar(), ("modelo", estimador)])


def _construir_hgb(parametros: dict, semente: int, colunas: tuple[str, ...], opcoes: dict | None = None) -> object:
    if opcoes is None:
        return HistGradientBoostingClassifier(
            max_iter=400,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=semente,
            **parametros,
        )
    opcoes = opcoes_completas(opcoes)
    resto, monotonia = _tirar_monotonia(parametros, "GradBoost")
    ajustes = {"max_iter": 400, "early_stopping": True, "validation_fraction": 0.15, "random_state": semente}
    if _veg_categorica(colunas, opcoes):
        ajustes["categorical_features"] = [colunas.index(COLUNA_VEG)]
    if monotonia:
        ajustes["monotonic_cst"] = restricoes_monotonicas(colunas, True)
    ajustes.update(resto)
    return HistGradientBoostingClassifier(**ajustes)


def _construir_xgboost(parametros: dict, semente: int, colunas: tuple[str, ...], opcoes: dict | None = None) -> object:
    import xgboost

    resto, monotonia = (dict(parametros), False) if opcoes is None else _tirar_monotonia(parametros, "XGBoost")
    desconhecidos = sorted(set(resto) - set(xgboost.XGBClassifier().get_params()))
    if desconhecidos:
        raise TypeError(f"XGBoost: parametros desconhecidos {desconhecidos}")
    if opcoes is None:
        return xgboost.XGBClassifier(
            n_estimators=400,
            tree_method="hist",
            device="cpu",
            n_jobs=-1,
            random_state=semente,
            **parametros,
        )
    opcoes = opcoes_completas(opcoes)
    ajustes = {"n_estimators": 400, "tree_method": "hist", "device": opcoes["dispositivo_xgboost"], "n_jobs": -1, "random_state": semente}
    if _veg_categorica(colunas, opcoes):
        ajustes["feature_types"] = ["c" if c == COLUNA_VEG else "q" for c in colunas]
        ajustes["enable_categorical"] = True
    if monotonia:
        ajustes["monotone_constraints"] = tuple(restricoes_monotonicas(colunas, True))
    if opcoes["dispositivo_xgboost"] != "cpu":
        from .xgb_dispositivo import PreverNaCpu

        ajustes["callbacks"] = [PreverNaCpu()]
    ajustes.update(resto)
    return xgboost.XGBClassifier(**ajustes)


def _construir_reglog(parametros: dict, semente: int, colunas: tuple[str, ...], opcoes: dict | None = None) -> object:
    resto = dict(parametros)
    transformacao = resto.pop("transformacao_distancias", "nenhuma")
    if transformacao not in ("nenhuma", "log1p"):
        raise ValueError(f"RegLogistica: transformacao_distancias deve ser 'nenhuma' ou 'log1p'; recebido {transformacao!r}")
    indices = () if transformacao == "nenhuma" else tuple(i for i, c in enumerate(colunas) if c in COLUNAS_DISTANCIA)
    if opcoes is None:
        estimador = LogisticRegression(max_iter=2000, class_weight="balanced", **resto)
        return Pipeline([_imputar(), ("log1p", Log1pColunas(indices)), ("escalar", StandardScaler()), ("modelo", estimador)])
    opcoes = opcoes_completas(opcoes)
    peso = "balanced" if opcoes["peso_classe"] == "balanceado" else None
    estimador = LogisticRegression(**{"max_iter": 2000, "class_weight": peso, **resto})
    if not _veg_categorica(colunas, opcoes):
        return Pipeline([_imputar(), ("log1p", Log1pColunas(indices)), ("escalar", StandardScaler()), ("modelo", estimador)])
    outras = [c for c in colunas if c != COLUNA_VEG]
    indices_outras = () if transformacao == "nenhuma" else tuple(i for i, c in enumerate(outras) if c in COLUNAS_DISTANCIA)
    numerico = Pipeline([_imputar(), ("log1p", Log1pColunas(indices_outras)), ("escalar", StandardScaler())])
    return Pipeline([("preparar", _codificar_veg(colunas, numerico)), ("modelo", estimador)])


REGISTRO: dict[str, EspecModelo] = {
    "FuzzyKNN": EspecModelo(
        "FuzzyKNN",
        _construir_fuzzy,
        {"k": 29, "m": 2.0},
        ({"k": list(range(3, 102, 2)), "m": [2.0]},),
        4,
    ),
    "RandomForest": EspecModelo(
        "RandomForest",
        _construir_floresta,
        {"max_depth": None, "min_samples_leaf": 5, "max_features": "sqrt"},
        ({"max_depth": [None, 8, 16], "min_samples_leaf": [1, 5, 20], "max_features": ["sqrt", 0.5, 1.0]},),
        1,
    ),
    "GradBoost": EspecModelo(
        "GradBoost",
        _construir_hgb,
        {"learning_rate": 0.06, "max_leaf_nodes": 63, "min_samples_leaf": 40, "l2_regularization": 1.0},
        ({"learning_rate": [0.03, 0.1], "max_leaf_nodes": [15, 31, 63], "min_samples_leaf": [20, 80], "l2_regularization": [0.0, 1.0]},),
        1,
    ),
    "XGBoost": EspecModelo(
        "XGBoost",
        _construir_xgboost,
        {"max_depth": 6, "learning_rate": 0.1, "min_child_weight": 1, "subsample": 1.0},
        ({"max_depth": [3, 6, 9], "learning_rate": [0.03, 0.1], "min_child_weight": [1, 10], "subsample": [0.8, 1.0]},),
        1,
        "xgboost",
    ),
    "RegLogistica": EspecModelo(
        "RegLogistica",
        _construir_reglog,
        {"C": 1.0, "transformacao_distancias": "nenhuma"},
        ({"C": [0.001, 0.01, 0.1, 1.0, 10.0, 100.0], "transformacao_distancias": ["nenhuma", "log1p"]},),
        4,
    ),
}


def nome_canonico(nome: str) -> str:
    for valido in REGISTRO:
        if valido.lower() == str(nome).lower():
            return valido
    raise SystemExit(f"ERRO modelo {nome!r} desconhecido; validos: {', '.join(REGISTRO)}")


def disponivel(nome: str) -> bool:
    pacote = REGISTRO[nome].pacote
    return pacote is None or importlib.util.find_spec(pacote) is not None


def criar(nome: str, parametros: dict, semente: int, colunas: Sequence[str], opcoes: dict | None = None) -> object:
    if opcoes is None:
        return REGISTRO[nome].construir(dict(parametros), int(semente), tuple(colunas))
    return REGISTRO[nome].construir(dict(parametros), int(semente), tuple(colunas), dict(opcoes))


def candidatos(nome: str, espacos: dict, incluir_padrao: bool = True) -> list[dict]:
    espec = REGISTRO[nome]
    espaco = espacos.get(nome, espec.espaco)
    lista = [dict(p) for p in ParameterGrid(list(espaco))]
    if incluir_padrao and espec.padrao not in lista:
        lista.append(dict(espec.padrao))
    return lista


def impressao_espaco(lista: list[dict]) -> str:
    return hashlib.sha256(json.dumps(lista, sort_keys=True).encode("utf-8")).hexdigest()
