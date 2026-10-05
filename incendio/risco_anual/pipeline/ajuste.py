from __future__ import annotations

import json
import math
import time
import warnings
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold, StratifiedKFold

from . import modelos


@dataclass(frozen=True)
class ResultadoBusca:
    candidatos: pd.DataFrame
    ordem_vencedor: int
    n_pastas: int


def n_pastas_efetivo(anos: np.ndarray, agrupamento: str, n_pastas: int) -> int:
    if agrupamento == "ano":
        return min(int(n_pastas), int(len(np.unique(anos))))
    return int(n_pastas)


def pastas(anos: np.ndarray, y: np.ndarray, agrupamento: str, n_pastas: int, semente: int, blocos: np.ndarray | None = None) -> list[tuple[np.ndarray, np.ndarray]]:
    anos = np.asarray(anos)
    y = np.asarray(y)
    linhas = np.zeros((len(anos), 1))
    if agrupamento == "ano":
        n_anos = int(len(np.unique(anos)))
        if n_anos < 2:
            raise SystemExit(f"ERRO cv: {n_anos} ano(s) de treino; a validacao cruzada por ano precisa de pelo menos 2")
        n = n_pastas_efetivo(anos, agrupamento, n_pastas)
        if n_anos < n_pastas:
            print(f"AVISO janela <={int(anos.max())}: {n_anos} anos; {n} pastas (uma por ano)")
        dobras = [(np.asarray(tr), np.asarray(va)) for tr, va in GroupKFold(n).split(linhas, y, groups=anos)]
        for i, (treino, validacao) in enumerate(dobras, start=1):
            if not set(anos[treino].tolist()).isdisjoint(anos[validacao].tolist()):
                raise SystemExit(f"ERRO cv: pasta {i} tem o mesmo ano em treino e validacao")
        return dobras
    if agrupamento == "bloco_espacial":
        if blocos is None:
            raise SystemExit("ERRO cv: agrupamento bloco_espacial sem os blocos das linhas")
        n_blocos = int(len(np.unique(blocos)))
        if n_blocos < n_pastas:
            raise SystemExit(
                f"ERRO cv: {n_blocos} blocos espaciais na tabela, menos que cv.n_pastas = {n_pastas}; diminua cv.lado_bloco_m ou cv.n_pastas"
            )
        divisor = StratifiedGroupKFold(n_pastas, shuffle=True, random_state=semente)
        return [(np.asarray(tr), np.asarray(va)) for tr, va in divisor.split(linhas, y, groups=np.asarray(blocos))]
    if agrupamento == "aleatorio":
        menor = int(min(int(y.sum()), int((y == 0).sum())))
        if menor < n_pastas:
            raise SystemExit(f"ERRO cv: {menor} linhas na menor classe, menos que cv.n_pastas = {n_pastas}")
        divisor = StratifiedKFold(n_pastas, shuffle=True, random_state=semente)
        return [(np.asarray(tr), np.asarray(va)) for tr, va in divisor.split(linhas, y)]
    raise SystemExit(f"ERRO cv: agrupamento {agrupamento!r} desconhecido")


def _agrupar(avisos: list[str]) -> list[str]:
    contagem: dict[str, int] = {}
    for texto in avisos:
        contagem[texto] = contagem.get(texto, 0) + 1
    return [texto if n == 1 else f"{texto} (em {n} pastas)" for texto, n in contagem.items()]


def avaliar_candidato(nome: str, parametros: dict, semente: int, colunas: tuple[str, ...], X: np.ndarray, y: np.ndarray, dobras: list[tuple[np.ndarray, np.ndarray]]) -> dict:
    inicio = time.perf_counter()
    pr_auc, roc_auc, avisos = [], [], []
    for i, (treino, validacao) in enumerate(dobras, start=1):
        if np.unique(y[validacao]).size < 2:
            avisos.append(f"pasta {i}: validacao com uma classe; metricas NaN")
            pr_auc.append(math.nan)
            roc_auc.append(math.nan)
            continue
        with warnings.catch_warnings(record=True) as capturados:
            warnings.simplefilter("always")
            try:
                estimador = modelos.criar(nome, parametros, semente, colunas)
                estimador.fit(X[treino], y[treino])
                p = estimador.predict_proba(X[validacao])[:, 1]
                pr_i = float(average_precision_score(y[validacao], p))
                roc_i = float(roc_auc_score(y[validacao], p))
            except Exception as erro:
                avisos.append(f"excecao {type(erro).__name__}: {erro}; metricas NaN")
                pr_i = roc_i = math.nan
        avisos += [f"{w.category.__name__}: {w.message}" for w in capturados]
        pr_auc.append(pr_i)
        roc_auc.append(roc_i)
    return {
        "pr_auc_pastas": pr_auc,
        "roc_auc_pastas": roc_auc,
        "segundos": time.perf_counter() - inicio,
        "avisos": _agrupar(avisos),
    }


def _media_desvio(valores: list[float]) -> tuple[float, float]:
    arr = np.asarray(valores, dtype=np.float64)
    validos = arr[np.isfinite(arr)]
    if validos.size == 0:
        return math.nan, math.nan
    return float(validos.mean()), float(validos.std(ddof=0))


def _texto_parametros(parametros: dict) -> str:
    return json.dumps(parametros, sort_keys=True)


def buscar(nome: str, X: np.ndarray, y: np.ndarray, anos: np.ndarray, ultimo_ano: int, lista: list[dict], semente: int, colunas: tuple[str, ...], dobras: list[tuple[np.ndarray, np.ndarray]], n_jobs: int, metrica: str, rotulo: str) -> ResultadoBusca:
    anos = np.asarray(anos)
    if anos.size and int(anos.max()) > int(ultimo_ano):
        raise SystemExit(f"ERRO {rotulo}: ano {int(anos.max())} depois da janela <={ultimo_ano} nas linhas de treino")
    colunas = tuple(colunas)
    total = len(lista)
    inicio = time.perf_counter()
    if n_jobs == 1:
        resultados = (avaliar_candidato(nome, p, semente, colunas, X, y, dobras) for p in lista)
    else:
        tarefas = (joblib.delayed(avaliar_candidato)(nome, p, semente, colunas, X, y, dobras) for p in lista)
        resultados = joblib.Parallel(n_jobs=n_jobs, return_as="generator")(tarefas)
    linhas = []
    for ordem, (parametros, resultado) in enumerate(zip(lista, resultados), start=1):
        texto = _texto_parametros(parametros)
        for aviso in resultado["avisos"]:
            print(f"AVISO [{rotulo}] {ordem}/{total} {texto}: {aviso}")
        pr_media, pr_desvio = _media_desvio(resultado["pr_auc_pastas"])
        roc_media, roc_desvio = _media_desvio(resultado["roc_auc_pastas"])
        pastas_json = json.dumps([v if math.isfinite(v) else None for v in resultado["pr_auc_pastas"]], allow_nan=False)
        linhas.append({
            "ordem": ordem,
            "parametros": texto,
            "pr_auc_media": pr_media,
            "pr_auc_desvio": pr_desvio,
            "roc_auc_media": roc_media,
            "roc_auc_desvio": roc_desvio,
            "pr_auc_pastas": pastas_json,
            "segundos": float(resultado["segundos"]),
        })
        media, desvio = (pr_media, pr_desvio) if metrica == "pr_auc" else (roc_media, roc_desvio)
        print(f"[{rotulo}] {ordem}/{total} {texto} {metrica}={media:.4f}+-{desvio:.4f} ({resultado['segundos']:.1f} s)")
    candidatos = pd.DataFrame(linhas)
    valores = candidatos[f"{metrica}_media"].to_numpy(dtype=np.float64)
    if np.isnan(valores).all():
        raise SystemExit(f"ERRO {rotulo}: nenhum candidato com metrica valida")
    posicao = int(np.nanargmax(valores))
    vencedor = candidatos.iloc[posicao]
    print(
        f"[{rotulo}] vencedor {int(vencedor['ordem'])}/{total} {vencedor['parametros']} "
        f"{metrica}={valores[posicao]:.4f}; {total} candidatos em {time.perf_counter() - inicio:.1f} s"
    )
    return ResultadoBusca(candidatos, int(vencedor["ordem"]), len(dobras))


def anos_por_pasta(anos: np.ndarray, y: np.ndarray, dobras: list[tuple[np.ndarray, np.ndarray]]) -> pd.DataFrame:
    anos = np.asarray(anos)
    y = np.asarray(y)
    linhas = []
    for i, (_, validacao) in enumerate(dobras, start=1):
        linhas.append({
            "pasta": i,
            "anos": ",".join(str(int(a)) for a in sorted(set(anos[validacao].tolist()))),
            "n_linhas": int(len(validacao)),
            "n_positivos": int(y[validacao].sum()),
        })
    return pd.DataFrame(linhas)
