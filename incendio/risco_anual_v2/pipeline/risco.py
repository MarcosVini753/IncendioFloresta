from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from . import historico, interpolacao, modelos

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


def sortear_ano(queimou_ano: np.ndarray, no_escopo: np.ndarray, semente: int, ano: int, escopo: str, negativos_por_positivo: int = 1) -> tuple[np.ndarray, np.ndarray]:
    queimou_ano = np.asarray(queimou_ano, dtype=bool)
    pos = np.flatnonzero(queimou_ano & no_escopo)
    neg = np.flatnonzero(~queimou_ano & no_escopo)
    if len(pos) == 0:
        print(f"AVISO {ano}/{escopo}: sem celulas com cicatriz; ano fora da tabela")
        return pos, pos.copy()
    razao = int(negativos_por_positivo)
    if razao < 1:
        raise SystemExit(f"ERRO amostragem {ano}/{escopo}: negativos_por_positivo deve ser >= 1; recebido {razao}")
    alvo = razao * len(pos)
    if len(neg) < alvo:
        sufixo = "" if razao == 1 else f" (razao 1:{razao})"
        print(f"AVISO {ano}/{escopo}: {len(neg)} negativos para {len(pos)} positivos{sufixo}; usando todos")
    rng = np.random.default_rng([semente, ano, CODIGO_ESCOPO[escopo]])
    return pos, np.sort(rng.choice(neg, size=min(alvo, len(neg)), replace=False))


def sortear_ou_todos(queimou_ano: np.ndarray, no_escopo: np.ndarray, semente: int, ano: int, escopo: str, negativos_por_positivo: int | None) -> np.ndarray:
    if negativos_por_positivo is None:
        return np.flatnonzero(no_escopo)
    pos, neg = sortear_ano(queimou_ano, no_escopo, semente, ano, escopo, negativos_por_positivo)
    return np.sort(np.concatenate([pos, neg]))


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


def tabela_treino(base: Base, regiao: np.ndarray, escopo: str, anos: Sequence[int], defasagem: int, semente: int, negativos_por_positivo: int | None = 1) -> pd.DataFrame:
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
        celulas = sortear_ou_todos(queimou, no_escopo, semente, ano, escopo, negativos_por_positivo)
        if celulas.size == 0:
            continue
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


COLUNAS_HISTORICO = historico.COLUNAS


def conferir_colunas_v2(colunas: Sequence[str]) -> None:
    fora = [c for c in colunas if c not in PREDITORES_PERMITIDOS and c not in COLUNAS_HISTORICO]
    if fora:
        raise SystemExit(f"ERRO preditores fora da lista permitida: {fora}")


class Atributos:
    def __init__(self, base: Base, defasagem: int, interpolacao_clima: str = "vizinho", historico_cfg: dict | None = None):
        if interpolacao_clima not in interpolacao.METODOS:
            raise SystemExit(f"ERRO interpolacao do clima {interpolacao_clima!r} desconhecida; validas: {', '.join(interpolacao.METODOS)}")
        self.base = base
        self.defasagem = int(defasagem)
        self.interpolacao_clima = interpolacao_clima
        self.historico_cfg = dict(historico_cfg) if historico_cfg else None
        self._pesos: interpolacao.PesosBilineares | None = None
        self._clima: dict[tuple[int, str], np.ndarray] = {}
        self._historico: dict[int, dict[str, np.ndarray]] = {}
        self._queimadas: dict[int, np.ndarray] | None = None

    def mascara_clima(self) -> np.ndarray:
        tabela = self.base.clima_anual
        primeiro = tabela[tabela["ano"] == tabela["ano"].min()].sort_values("cli_id")
        lin = primeiro["cli_lin"].to_numpy(dtype=np.int64)
        col = primeiro["cli_col"].to_numpy(dtype=np.int64)
        mascara = interpolacao.mascara_do_clima(self.base.perfil_clima["forma"], lin, col)
        if not np.array_equal(interpolacao.mapa_de_ids(mascara)[lin, col], primeiro["cli_id"].to_numpy(dtype=np.int64)):
            raise SystemExit("ERRO interpolacao: cli_id do clima fora da ordem da mascara")
        return mascara

    def pesos(self) -> interpolacao.PesosBilineares:
        if self._pesos is None:
            est = self.base.est
            self._pesos = interpolacao.pesos_bilineares(
                est["lon"].to_numpy(dtype=np.float64),
                est["lat"].to_numpy(dtype=np.float64),
                self.base.perfil_clima["transformacao"],
                self.mascara_clima(),
                est["cli_id"].to_numpy(dtype=np.int64),
            )
        return self._pesos

    def clima(self, ano_clima: int, coluna: str) -> np.ndarray:
        chave = (int(ano_clima), coluna)
        if chave not in self._clima:
            if int(ano_clima) not in set(self.base.anos_clima):
                lista = ", ".join(str(a) for a in self.base.anos_clima)
                raise SystemExit(f"ERRO sem clima completo em {ano_clima}; anos com clima: {lista}")
            valores = _serie_clima(self.base, int(ano_clima), CLIMA_DO_MODELO[coluna])
            if self.interpolacao_clima == "bilinear":
                self._clima[chave] = interpolacao.interpolar(self.pesos(), valores)
            else:
                self._clima[chave] = interpolacao.vizinho(self.base.est["cli_id"].to_numpy(dtype=np.int64), valores)
        return self._clima[chave]

    def historico_ano(self, ano: int) -> dict[str, np.ndarray]:
        if self.historico_cfg is None:
            raise SystemExit("ERRO colunas de historico de fogo sem a configuracao 'historico'")
        ano = int(ano)
        if ano not in self._historico:
            if self._queimadas is None:
                self._queimadas = historico.queimadas_da_base(self.base.est, tuple(self.base.anos_cicatriz))
            self._historico[ano] = historico.atributos(self._queimadas, ano, self.historico_cfg["teto_anos"], self.historico_cfg["tau_anos"])
        return self._historico[ano]

    def coluna(self, nome: str, ano: int) -> np.ndarray:
        if nome in CLIMA_DO_MODELO:
            return self.clima(int(ano) - self.defasagem, nome)
        if nome in COLUNAS_HISTORICO:
            return self.historico_ano(ano)[nome]
        if nome in PREDITORES_PERMITIDOS:
            return self.base.est[nome].to_numpy(dtype=np.float64)
        raise SystemExit(f"ERRO preditores fora da lista permitida: [{nome!r}]")

    def matriz(self, colunas: Sequence[str], ano: int, celulas: np.ndarray | None = None) -> np.ndarray:
        conferir_colunas_v2(colunas)
        n = len(self.base.est) if celulas is None else len(celulas)
        X = np.empty((n, len(colunas)), dtype=np.float64)
        for j, nome in enumerate(colunas):
            valores = self.coluna(nome, ano)
            X[:, j] = valores if celulas is None else valores[np.asarray(celulas)]
        return X


@dataclass
class TabelaCompleta:
    escopo: str
    colunas: tuple[str, ...]
    anos: tuple[int, ...]
    celulas: np.ndarray
    X: np.ndarray
    y: np.ndarray
    ano: np.ndarray

    def fim(self, ultimo_ano: int) -> int:
        return int(self.celulas.size) * sum(1 for a in self.anos if a <= int(ultimo_ano))

    def bloco(self, ano: int) -> slice:
        i = self.anos.index(int(ano))
        n = int(self.celulas.size)
        return slice(i * n, (i + 1) * n)


def celulas_do_escopo(regiao: np.ndarray, escopo: str, n_celulas: int) -> np.ndarray:
    if escopo == "acre":
        return np.arange(n_celulas, dtype=np.int64)
    return np.flatnonzero(np.asarray(regiao) == escopo).astype(np.int64)


def tabela_completa(atributos: Atributos, regiao: np.ndarray, escopo: str, anos: Sequence[int], colunas: Sequence[str]) -> TabelaCompleta:
    base = atributos.base
    rotulaveis = set(anos_rotulaveis(base, atributos.defasagem))
    anos = tuple(sorted(int(a) for a in anos))
    for ano in anos:
        if ano not in rotulaveis:
            raise SystemExit(f"ERRO ano {ano} nao rotulavel com defasagem {atributos.defasagem}")
    conferir_colunas_v2(colunas)
    celulas = celulas_do_escopo(regiao, escopo, len(base.est))
    n_c = int(celulas.size)
    X = np.empty((n_c * len(anos), len(colunas)), dtype=np.float64)
    y = np.empty(n_c * len(anos), dtype=np.int8)
    for i, ano in enumerate(anos):
        bloco = slice(i * n_c, (i + 1) * n_c)
        X[bloco] = atributos.matriz(colunas, ano, celulas)
        y[bloco] = base.est[f"queimou_{ano}"].to_numpy(dtype=bool)[celulas]
    ano_linha = np.repeat(np.asarray(anos, dtype=np.int16), n_c)
    return TabelaCompleta(escopo, tuple(colunas), anos, celulas, X, y, ano_linha)


def mascara_amostragem(tabela: TabelaCompleta, negativos_por_positivo: int | None, semente: int, n_celulas: int) -> np.ndarray:
    if negativos_por_positivo is None:
        return np.ones(tabela.y.size, dtype=bool)
    n_c = int(tabela.celulas.size)
    mascara = np.zeros(tabela.y.size, dtype=bool)
    no_escopo = np.zeros(n_celulas, dtype=bool)
    no_escopo[tabela.celulas] = True
    for i, ano in enumerate(tabela.anos):
        queimou = np.zeros(n_celulas, dtype=bool)
        queimou[tabela.celulas] = tabela.y[i * n_c:(i + 1) * n_c].astype(bool)
        escolhidas = sortear_ou_todos(queimou, no_escopo, semente, ano, tabela.escopo, negativos_por_positivo)
        mascara[i * n_c + np.searchsorted(tabela.celulas, escolhidas)] = True
    return mascara


def fracao_negativos_mantidos(y: np.ndarray, mascara: np.ndarray) -> float:
    negativos = np.asarray(y) == 0
    total = int(negativos.sum())
    return float((negativos & np.asarray(mascara, dtype=bool)).sum()) / total if total else float("nan")


def impressao_tabela_v2(X: np.ndarray, y: np.ndarray, anos: np.ndarray, mascara: np.ndarray) -> str:
    h = hashlib.sha256()
    for parte in (
        np.ascontiguousarray(X, dtype=np.float64),
        np.ascontiguousarray(y, dtype=np.int8),
        np.ascontiguousarray(anos, dtype=np.int16),
        np.ascontiguousarray(mascara, dtype=np.uint8),
    ):
        h.update(memoryview(parte).cast("B"))
    return h.hexdigest()


def descritor_preditores(colunas: Sequence[str], interpolacao_clima: str, veg_categorica: bool, historico_cfg: dict | None) -> str:
    nomes_historico = historico.descricao(historico_cfg["teto_anos"], historico_cfg["tau_anos"]) if historico_cfg else {}
    partes = []
    for coluna in colunas:
        if coluna in CLIMA_DO_MODELO:
            partes.append(f"{coluna}[{interpolacao_clima}]")
        elif coluna == "veg" and veg_categorica:
            partes.append("veg[categorica]")
        elif coluna in nomes_historico:
            partes.append(nomes_historico[coluna])
        else:
            partes.append(coluna)
    return ",".join(partes)
