from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.metrics import average_precision_score, brier_score_loss, classification_report, confusion_matrix, precision_recall_curve, roc_auc_score

CHAVES_RELATORIO = ("precision", "recall", "f1-score", "support")
NOMES_RELATORIO = {"precision": "precisao", "recall": "revocacao", "f1-score": "f1", "support": "suporte"}


def indice_percentil(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64)
    if p.ndim != 1 or p.size == 0:
        raise SystemExit("ERRO indice de risco: vetor de probabilidades vazio ou com mais de uma dimensao")
    if np.isnan(p).any():
        raise SystemExit(f"ERRO indice de risco: {int(np.isnan(p).sum())} probabilidades NaN")
    if p.size == 1:
        return np.array([100.0])
    return 100.0 * (rankdata(p, method="average") - 1.0) / (p.size - 1.0)


def corrigir_prior(p_amostrada: np.ndarray, beta: float) -> np.ndarray:
    beta = float(beta)
    if not 0 < beta <= 1:
        raise SystemExit(f"ERRO correcao de prior: beta deve estar em (0, 1]; recebido {beta}")
    p = np.asarray(p_amostrada, dtype=np.float64)
    return np.clip(beta * p / (beta * p - p + 1.0), 0.0, 1.0)


def limiar_maior_f1(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    y = np.asarray(y).astype(np.int64)
    if y.sum() == 0 or y.sum() == y.size:
        raise SystemExit("ERRO limiar: o ano usado para escolher o limiar precisa das duas classes")
    precisao, revocacao, limiares = precision_recall_curve(y, np.asarray(p, dtype=np.float64))
    precisao, revocacao = precisao[:-1], revocacao[:-1]
    soma = precisao + revocacao
    f1 = np.divide(2 * precisao * revocacao, soma, out=np.zeros_like(soma), where=soma > 0)
    melhor = int(np.argmax(f1))
    return float(limiares[melhor]), float(f1[melhor])


def topo(p: np.ndarray, fracao: float) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64)
    n_topo = max(int(round(p.size * float(fracao))), 1)
    marcado = np.zeros(p.size, dtype=bool)
    marcado[np.argsort(p)[::-1][:n_topo]] = True
    return marcado


def relatorio_classificacao(y: np.ndarray, previsto: np.ndarray) -> dict:
    y = np.asarray(y).astype(np.int64)
    previsto = np.asarray(previsto).astype(np.int64)
    bruto = classification_report(y, previsto, labels=[0, 1], output_dict=True, zero_division=0)
    linha = {}
    for classe in ("0", "1"):
        for chave in CHAVES_RELATORIO:
            linha[f"{NOMES_RELATORIO[chave]}_{classe}"] = float(bruto[classe][chave])
    linha["acuracia"] = float(bruto["accuracy"]) if "accuracy" in bruto else float((y == previsto).mean())
    for media, nome in (("macro avg", "macro"), ("weighted avg", "ponderada")):
        for chave in ("precision", "recall", "f1-score"):
            linha[f"{NOMES_RELATORIO[chave]}_{nome}"] = float(bruto[media][chave])
    vn, fp, fn, vp = confusion_matrix(y, previsto, labels=[0, 1]).ravel()
    linha.update({"VP": int(vp), "FN": int(fn), "FP": int(fp), "VN": int(vn), "n_previstos_1": int(previsto.sum())})
    return linha


def amostra_teste(y: np.ndarray, negativos_por_positivo: int, semente: int, ano: int) -> np.ndarray:
    y = np.asarray(y).astype(bool)
    pos = np.flatnonzero(y)
    neg = np.flatnonzero(~y)
    rng = np.random.default_rng([int(semente), int(ano), 99])
    escolhidos = rng.choice(neg, size=min(int(negativos_por_positivo) * pos.size, neg.size), replace=False)
    return np.sort(np.concatenate([pos, escolhidos]))


def calibracao(y: np.ndarray, p_bruta: np.ndarray, p_corrigida: np.ndarray | None) -> dict:
    y = np.asarray(y).astype(np.int64)
    p_bruta = np.asarray(p_bruta, dtype=np.float64)
    linha = {
        "n_celulas": int(y.size),
        "queimadas_observadas": int(y.sum()),
        "queimadas_esperadas_bruta": float(p_bruta.sum()),
        "brier_bruto": float(brier_score_loss(y, p_bruta)),
        "p_media_bruta": float(p_bruta.mean()),
    }
    if p_corrigida is not None:
        p_corrigida = np.asarray(p_corrigida, dtype=np.float64)
        linha.update({
            "queimadas_esperadas_corrigida": float(p_corrigida.sum()),
            "brier_corrigido": float(brier_score_loss(y, p_corrigida)),
            "p_media_corrigida": float(p_corrigida.mean()),
        })
    else:
        linha.update({"queimadas_esperadas_corrigida": float(p_bruta.sum()), "brier_corrigido": linha["brier_bruto"], "p_media_corrigida": linha["p_media_bruta"]})
    return linha


def confiabilidade(y: np.ndarray, p_bruta: np.ndarray, p_corrigida: np.ndarray | None, indice: np.ndarray, cortes: Sequence[float]) -> pd.DataFrame:
    y = np.asarray(y).astype(np.int64)
    p_bruta = np.asarray(p_bruta, dtype=np.float64)
    p_corrigida = p_bruta if p_corrigida is None else np.asarray(p_corrigida, dtype=np.float64)
    indice = np.asarray(indice, dtype=np.float64)
    cortes = [float(c) for c in cortes]
    linhas = []
    for i, (inferior, superior) in enumerate(zip(cortes, cortes[1:])):
        ultima = i == len(cortes) - 2
        sel = (indice >= inferior) & ((indice <= superior) if ultima else (indice < superior))
        n = int(sel.sum())
        linhas.append({
            "classe": f"{inferior:g}-{superior:g}",
            "indice_min": inferior,
            "indice_max": superior,
            "n_celulas": n,
            "queimadas": int(y[sel].sum()),
            "taxa_observada": float(y[sel].mean()) if n else float("nan"),
            "p_media_bruta": float(p_bruta[sel].mean()) if n else float("nan"),
            "p_media_corrigida": float(p_corrigida[sel].mean()) if n else float("nan"),
            "queimadas_esperadas_corrigida": float(p_corrigida[sel].sum()),
        })
    return pd.DataFrame(linhas)


def metricas_ranking(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    y = np.asarray(y).astype(np.int64)
    if y.min() == y.max():
        return float("nan"), float("nan")
    return float(average_precision_score(y, p)), float(roc_auc_score(y, p))


def importancia_permutacao(estimador: object, X: np.ndarray, y: np.ndarray, colunas: Sequence[str], repeticoes: int, semente: int) -> pd.DataFrame:
    X = np.asarray(X, dtype=np.float64)
    base_pr, base_roc = metricas_ranking(y, estimador.predict_proba(X)[:, 1])
    rng = np.random.default_rng(int(semente))
    linhas = []
    for j, coluna in enumerate(colunas):
        quedas_pr, quedas_roc = [], []
        original = X[:, j].copy()
        try:
            for _ in range(int(repeticoes)):
                X[:, j] = original[rng.permutation(original.size)]
                pr, roc = metricas_ranking(y, estimador.predict_proba(X)[:, 1])
                quedas_pr.append(base_pr - pr)
                quedas_roc.append(base_roc - roc)
        finally:
            X[:, j] = original
        linhas.append({
            "variavel": coluna,
            "pr_auc_base": base_pr,
            "queda_pr_auc_media": float(np.mean(quedas_pr)),
            "queda_pr_auc_desvio": float(np.std(quedas_pr)),
            "queda_relativa_pr_auc": float(np.mean(quedas_pr) / base_pr) if base_pr else float("nan"),
            "roc_auc_base": base_roc,
            "queda_roc_auc_media": float(np.mean(quedas_roc)),
            "repeticoes": int(repeticoes),
        })
    tabela = pd.DataFrame(linhas)
    tabela["posto"] = tabela["queda_pr_auc_media"].rank(ascending=False, method="min").astype(int)
    return tabela


def dependencia_parcial(estimador: object, X: np.ndarray, j: int, pontos: int, beta: float | None = None) -> pd.DataFrame:
    X = np.array(X, dtype=np.float64, copy=True)
    valores = X[:, j]
    grade = np.unique(np.nanquantile(valores, np.linspace(0.01, 0.99, int(pontos))))
    linhas = []
    for valor in grade:
        X[:, j] = valor
        p = estimador.predict_proba(X)[:, 1]
        if beta is not None:
            p = corrigir_prior(p, beta)
        linhas.append({"valor": float(valor), "p_media": float(p.mean()), "p_mediana": float(np.median(p))})
    return pd.DataFrame(linhas)
