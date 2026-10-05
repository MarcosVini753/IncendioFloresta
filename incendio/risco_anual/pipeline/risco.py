from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from . import modelos

if TYPE_CHECKING:
    from .config import Config
    from .fontes import Base

PREDITORES_PERMITIDOS = ("veg", "dist_estrada", "dist_agua", "altitude", "ur_media_ano", "prec_acum_ano")
CODIGO_ESCOPO = {"acre": 0, "oeste": 1, "leste": 2}
REGIOES = ("oeste", "leste")
CLIMA_DO_MODELO = {"ur_media_ano": "ur_media", "prec_acum_ano": "prec_acum"}
METRICAS = ("roc_auc", "pr_auc", "brier", "det@1%", "det@5%", "det@10%", "det@20%")


def texto_divisao(divisao: dict) -> str:
    return f"x_g<{float(divisao['valor_m'])!r}"


def regiao_de(est: pd.DataFrame, divisao: dict) -> np.ndarray:
    x = est["x_g"].to_numpy(dtype=np.float64)
    texto = texto_divisao(divisao)
    faltando = int(np.isnan(x).sum())
    if faltando:
        raise SystemExit(f"ERRO divisao {texto}: x_g com NaN em {faltando} celulas")
    regiao = np.where(x < float(divisao["valor_m"]), "oeste", "leste")
    for nome in REGIOES:
        if not (regiao == nome).any():
            raise SystemExit(f"ERRO divisao {texto} deixa a regiao {nome} vazia")
    return regiao


def anos_rotulaveis(base: Base, defasagem: int) -> tuple[int, ...]:
    completos = set(base.anos_clima)
    return tuple(a for a in base.anos_cicatriz if a in completos and a - defasagem in completos)


def ano_previsivel(base: Base, ano: int, defasagem: int) -> bool:
    return ano - defasagem in set(base.anos_clima)


def ano_avaliavel(base: Base, ano: int) -> bool:
    return ano in set(base.anos_cicatriz) and ano in set(base.anos_clima)


def anos_treino(base: Base, cfg: Config) -> tuple[int, ...]:
    comuns = set(anos_rotulaveis(base, cfg.defasagem_principal))
    for defasagem in cfg.defasagens_comparacao:
        comuns &= set(anos_rotulaveis(base, defasagem))
    return tuple(sorted(comuns))


def janelas(cfg: Config) -> tuple[int, ...]:
    return tuple(sorted({a - 1 for a in cfg.anos_previsao}))


def janela_para(ano: int, anos_previsao: Sequence[int]) -> int:
    candidatas = [a - 1 for a in anos_previsao if a - 1 <= ano - 1]
    if not candidatas:
        raise SystemExit(f"ERRO ano {ano}: nenhuma janela configurada termina antes dele")
    return max(candidatas)


def sortear_ano(queimou_ano: np.ndarray, no_escopo: np.ndarray, semente: int, ano: int, escopo: str) -> tuple[np.ndarray, np.ndarray]:
    queimou_ano = np.asarray(queimou_ano, dtype=bool)
    pos = np.flatnonzero(queimou_ano & no_escopo)
    neg = np.flatnonzero(~queimou_ano & no_escopo)
    if len(pos) == 0:
        print(f"AVISO {ano}/{escopo}: sem celulas com cicatriz; ano fora da tabela")
        return pos, pos.copy()
    if len(neg) < len(pos):
        print(f"AVISO {ano}/{escopo}: {len(neg)} negativos para {len(pos)} positivos; usando todos")
    rng = np.random.default_rng([semente, ano, CODIGO_ESCOPO[escopo]])
    return pos, np.sort(rng.choice(neg, size=min(len(pos), len(neg)), replace=False))


def _serie_clima(base: Base, ano: int, coluna: str) -> np.ndarray:
    tabela = base.clima_anual
    sub = tabela[tabela["ano"] == ano]
    valores = np.full(int(tabela["cli_id"].max()) + 1, np.nan)
    valores[sub["cli_id"].to_numpy(dtype=np.int64)] = sub[coluna].to_numpy(dtype=np.float64)
    return valores


def _conferir_colunas(colunas: Sequence[str]) -> None:
    fora = [c for c in colunas if c not in PREDITORES_PERMITIDOS]
    if fora:
        raise SystemExit(f"ERRO preditores fora da lista permitida: {fora}")


def tabela_treino(base: Base, regiao: np.ndarray, escopo: str, anos: Sequence[int], defasagem: int, semente: int) -> pd.DataFrame:
    rotulaveis = set(anos_rotulaveis(base, defasagem))
    for ano in anos:
        if ano not in rotulaveis:
            raise SystemExit(f"ERRO ano {ano} nao rotulavel com defasagem {defasagem}")
    est = base.est
    no_escopo = np.ones(len(est), dtype=bool) if escopo == "acre" else np.asarray(regiao) == escopo
    cli = est["cli_id"].to_numpy(dtype=np.int64)
    paisagem = {c: est[c].to_numpy(dtype=np.float64) for c in PREDITORES_PERMITIDOS if c not in CLIMA_DO_MODELO}
    blocos = []
    for ano in sorted(int(a) for a in anos):
        queimou = est[f"queimou_{ano}"].to_numpy(dtype=bool)
        pos, neg = sortear_ano(queimou, no_escopo, semente, ano, escopo)
        if len(pos) == 0:
            continue
        celulas = np.sort(np.concatenate([pos, neg]))
        ano_clima = ano - defasagem
        bloco = {
            "celula": celulas.astype(np.int64),
            "ano": np.full(celulas.size, ano, dtype=np.int16),
            "ano_clima": np.full(celulas.size, ano_clima, dtype=np.int16),
            "y": queimou[celulas].astype(np.int8),
            "regiao": np.asarray(regiao)[celulas],
        }
        for coluna in PREDITORES_PERMITIDOS:
            if coluna in CLIMA_DO_MODELO:
                bloco[coluna] = _serie_clima(base, ano_clima, CLIMA_DO_MODELO[coluna])[cli[celulas]]
            else:
                bloco[coluna] = paisagem[coluna][celulas]
        blocos.append(pd.DataFrame(bloco))
    if not blocos:
        vazia = {"celula": np.int64, "ano": np.int16, "ano_clima": np.int16, "y": np.int8, "regiao": object}
        vazia.update({c: np.float64 for c in PREDITORES_PERMITIDOS})
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in vazia.items()})
    return pd.concat(blocos, ignore_index=True)


def matriz_janela(tab: pd.DataFrame, colunas: Sequence[str], ultimo_ano: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    _conferir_colunas(colunas)
    sub = tab[tab["ano"] <= ultimo_ano]
    return sub[list(colunas)].to_numpy(dtype=np.float64), sub["y"].to_numpy(), sub["ano"].to_numpy()


def impressao_tabela(X: np.ndarray, y: np.ndarray, anos: np.ndarray) -> str:
    h = hashlib.sha256()
    for parte in (
        np.ascontiguousarray(X, dtype=np.float64),
        np.ascontiguousarray(y, dtype=np.int8),
        np.ascontiguousarray(anos, dtype=np.int16),
    ):
        h.update(parte.tobytes())
    return h.hexdigest()


def matriz_predicao(base: Base, colunas: Sequence[str], ano: int, defasagem: int, celulas: np.ndarray | None = None) -> np.ndarray:
    _conferir_colunas(colunas)
    if not ano_previsivel(base, ano, defasagem):
        lista = ", ".join(str(a) for a in base.anos_clima)
        raise SystemExit(f"ERRO ano {ano}: sem clima completo em {ano - defasagem} (defasagem {defasagem}); anos com clima: {lista}")
    est = base.est if celulas is None else base.est.iloc[np.asarray(celulas)]
    cli = est["cli_id"].to_numpy(dtype=np.int64)
    partes = []
    for coluna in colunas:
        if coluna in CLIMA_DO_MODELO:
            partes.append(_serie_clima(base, ano - defasagem, CLIMA_DO_MODELO[coluna])[cli])
        else:
            partes.append(est[coluna].to_numpy(dtype=np.float64))
    return np.column_stack(partes).astype(np.float64)


def avaliar_subconjunto(y: np.ndarray, p: np.ndarray, rotulo: str) -> dict[str, float]:
    y = np.asarray(y)
    if y.size == 0 or y.min() == y.max():
        print(f"AVISO {rotulo}: {y.size} celulas e uma classe so; metricas NaN")
        return {"prevalencia": float(y.mean()) if y.size else float("nan")} | dict.fromkeys(METRICAS, float("nan"))
    return modelos.avaliar(y, p)


def _nome_limiar(limiar: float) -> str:
    return f"pct_ge_{float(limiar):g}"


def estatisticas_risco(risco_pct: np.ndarray, cicatriz: np.ndarray, regiao: np.ndarray, limiares: Sequence[float]) -> pd.DataFrame:
    risco_pct = np.asarray(risco_pct, dtype=np.float64)
    cicatriz = np.asarray(cicatriz)
    regiao = np.asarray(regiao)
    linhas = []
    for recorte in ("acre", *REGIOES):
        no_recorte = np.ones(risco_pct.size, dtype=bool) if recorte == "acre" else regiao == recorte
        for grupo in ("com_cicatriz", "sem_cicatriz", "todas"):
            if grupo == "com_cicatriz":
                sel = no_recorte & (cicatriz == 1)
            elif grupo == "sem_cicatriz":
                sel = no_recorte & (cicatriz == 0)
            else:
                sel = no_recorte
            valores = risco_pct[sel]
            linha = {"recorte": recorte, "grupo": grupo, "n": int(valores.size)}
            if valores.size == 0:
                print(f"AVISO estatisticas {recorte}/{grupo}: grupo vazio; valores NaN")
                linha.update(dict.fromkeys(["media", "mediana", "minimo", "p10", "p25", "p75", "p90", "maximo"], float("nan")))
                linha.update({_nome_limiar(l): float("nan") for l in limiares})
            else:
                p10, p25, mediana, p75, p90 = np.percentile(valores, [10, 25, 50, 75, 90])
                linha.update({
                    "media": float(valores.mean()),
                    "mediana": float(mediana),
                    "minimo": float(valores.min()),
                    "p10": float(p10),
                    "p25": float(p25),
                    "p75": float(p75),
                    "p90": float(p90),
                    "maximo": float(valores.max()),
                })
                linha.update({_nome_limiar(l): float(100.0 * (valores >= l).mean()) for l in limiares})
            linhas.append(linha)
    return pd.DataFrame(linhas)


def coeficientes(estimador: object, colunas: Sequence[str]) -> dict[str, float]:
    passos = estimador.named_steps
    indices = set(passos["log1p"].indices) if "log1p" in passos else set()
    nomes = [f"log1p({c})" if i in indices else c for i, c in enumerate(colunas)]
    return dict(zip(nomes, (float(v) for v in passos["modelo"].coef_[0])))


def fora_da_faixa(X_regiao: np.ndarray, X_treino: np.ndarray, y_treino: np.ndarray, colunas: Sequence[str]) -> pd.DataFrame:
    X_regiao = np.asarray(X_regiao, dtype=np.float64)
    X_treino = np.asarray(X_treino, dtype=np.float64)
    positivos = X_treino[np.asarray(y_treino) == 1]
    linhas = []
    for j, coluna in enumerate(colunas):
        valores = X_regiao[:, j]
        valores = valores[~np.isnan(valores)]
        minimo, maximo = np.nanmin(X_treino[:, j]), np.nanmax(X_treino[:, j])
        p1, p99 = np.nanpercentile(positivos[:, j], [1, 99]) if len(positivos) else (np.nan, np.nan)
        n = valores.size
        linhas.append({
            "variavel": coluna,
            "n_celulas": int(n),
            "min_treino": float(minimo),
            "max_treino": float(maximo),
            "pct_fora_min_max": float(100.0 * ((valores < minimo) | (valores > maximo)).mean()) if n else float("nan"),
            "p1_positivos": float(p1),
            "p99_positivos": float(p99),
            "pct_fora_p1_p99_positivos": float(100.0 * ((valores < p1) | (valores > p99)).mean()) if n else float("nan"),
        })
    return pd.DataFrame(linhas)


def juntar_regional(partes: dict[str, tuple[np.ndarray, np.ndarray]], n_celulas: int, rotulo: str) -> tuple[np.ndarray, np.ndarray]:
    celulas = np.concatenate([np.asarray(c, dtype=np.int64) for c, _ in partes.values()])
    p = np.concatenate([np.asarray(v, dtype=np.float64) for _, v in partes.values()])
    escopo = np.concatenate([np.full(len(c), nome, dtype=object) for nome, (c, _) in partes.items()])
    ordem = np.argsort(celulas, kind="stable")
    celulas, p, escopo = celulas[ordem], p[ordem], escopo[ordem]
    problema = None
    unicas = np.unique(celulas).size
    if unicas != celulas.size:
        problema = f"{celulas.size - unicas} celulas repetidas"
    elif celulas.size != n_celulas:
        problema = f"{celulas.size} celulas preditas, esperado {n_celulas}"
    elif not np.array_equal(celulas, np.arange(n_celulas)):
        problema = "indices de celula fora de 0..n-1"
    elif np.isnan(p).any():
        problema = f"{int(np.isnan(p).sum())} predicoes NaN"
    if problema:
        raise SystemExit(f"ERRO juncao regional {rotulo}: {problema}")
    return p, escopo
