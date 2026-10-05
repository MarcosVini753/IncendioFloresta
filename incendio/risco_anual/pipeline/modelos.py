from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin
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
from sklearn.preprocessing import StandardScaler
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
    construir: Callable[[dict, int, tuple[str, ...]], object]
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


def _imputar() -> tuple[str, SimpleImputer]:
    return ("imputar", SimpleImputer(strategy="median"))


def _construir_fuzzy(parametros: dict, semente: int, colunas: tuple[str, ...]) -> object:
    return Pipeline([_imputar(), ("escalar", StandardScaler()), ("modelo", FuzzyKNN(bloco=512, **parametros))])


def _construir_floresta(parametros: dict, semente: int, colunas: tuple[str, ...]) -> object:
    estimador = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=semente,
        **parametros,
    )
    return Pipeline([_imputar(), ("modelo", estimador)])


def _construir_hgb(parametros: dict, semente: int, colunas: tuple[str, ...]) -> object:
    return HistGradientBoostingClassifier(
        max_iter=400,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=semente,
        **parametros,
    )


def _construir_xgboost(parametros: dict, semente: int, colunas: tuple[str, ...]) -> object:
    import xgboost

    desconhecidos = sorted(set(parametros) - set(xgboost.XGBClassifier().get_params()))
    if desconhecidos:
        raise TypeError(f"XGBoost: parametros desconhecidos {desconhecidos}")
    return xgboost.XGBClassifier(
        n_estimators=400,
        tree_method="hist",
        device="cpu",
        n_jobs=-1,
        random_state=semente,
        **parametros,
    )


def _construir_reglog(parametros: dict, semente: int, colunas: tuple[str, ...]) -> object:
    resto = dict(parametros)
    transformacao = resto.pop("transformacao_distancias", "nenhuma")
    if transformacao == "nenhuma":
        indices = ()
    elif transformacao == "log1p":
        indices = tuple(i for i, c in enumerate(colunas) if c in COLUNAS_DISTANCIA)
    else:
        raise ValueError(f"RegLogistica: transformacao_distancias deve ser 'nenhuma' ou 'log1p'; recebido {transformacao!r}")
    estimador = LogisticRegression(max_iter=2000, class_weight="balanced", **resto)
    return Pipeline([_imputar(), ("log1p", Log1pColunas(indices)), ("escalar", StandardScaler()), ("modelo", estimador)])


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


def criar(nome: str, parametros: dict, semente: int, colunas: Sequence[str]) -> object:
    return REGISTRO[nome].construir(dict(parametros), int(semente), tuple(colunas))


def candidatos(nome: str, espacos: dict) -> list[dict]:
    espec = REGISTRO[nome]
    espaco = espacos.get(nome, espec.espaco)
    lista = [dict(p) for p in ParameterGrid(list(espaco))]
    if espec.padrao not in lista:
        lista.append(dict(espec.padrao))
    return lista


def impressao_espaco(lista: list[dict]) -> str:
    return hashlib.sha256(json.dumps(lista, sort_keys=True).encode("utf-8")).hexdigest()
