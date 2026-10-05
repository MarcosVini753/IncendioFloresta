from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psutil
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedKFold

from .pipeline import ajuste, banco, config, execucao, fontes, mapas, modelos, risco

PREDITORES = ["veg", "dist_estrada", "dist_agua", "altitude"]
LADO_BLOCO_M = 25_000
INSTALACAO = {"xgboost": "xgboost==3.2.0"}
ESCOPOS_DO_CENARIO = {"unico": ("acre",), "regional": ("oeste", "leste")}
MEMORIA_MINIMA_GIB = 3.0


def bloco_espacial(est: pd.DataFrame, lado_m: float = LADO_BLOCO_M) -> np.ndarray:
    bx = np.floor(est["x_g"].values / lado_m).astype(np.int64)
    by = np.floor(est["y_g2"].values / lado_m).astype(np.int64)
    return bx * 100_000 + by


def equilibrar(y: np.ndarray, rng, razao: int = 1) -> np.ndarray:
    pos = np.nonzero(y == 1)[0]
    neg = np.nonzero(y == 0)[0]
    n = min(len(pos) * razao, len(neg))
    return np.concatenate([pos, rng.choice(neg, size=n, replace=False)])


@dataclass
class Contexto:
    cfg: config.Config
    args: argparse.Namespace
    comando: list[str]
    rodada: str
    impressao_config: str
    tempos: list[dict] = field(default_factory=list)


def script() -> str:
    return Path(__file__).name


def comuns(ctx: Contexto) -> dict:
    return {"rodada": ctx.rodada, "impressao_config": ctx.impressao_config, "comando": " ".join(ctx.comando)}


def avisar_memoria() -> None:
    livre = psutil.virtual_memory().available / 2**30
    if livre < MEMORIA_MINIMA_GIB:
        print(f"AVISO memoria livre {livre:.1f} GiB")


def carregar(ctx: Contexto) -> fontes.Base:
    base = fontes.carregar_base(ctx.cfg, reconstruir=bool(getattr(ctx.args, "reconstruir_cache", False)))
    fontes.imprimir_resumo(base.relatorio)
    return base


def sem_repeticao(valores):
    return None if valores is None else list(dict.fromkeys(valores))


def normalizar(args: argparse.Namespace) -> None:
    if getattr(args, "modelo", None):
        args.modelo = [modelos.nome_canonico(nome) for nome in args.modelo]
    for nome in ("modelo", "escopo", "janela", "cenario", "ano"):
        if hasattr(args, nome):
            setattr(args, nome, sem_repeticao(getattr(args, nome)))


def instalar(pacote: str) -> str:
    return f"python -m pip install {INSTALACAO.get(pacote, pacote)}"


def modelos_pedidos(cfg: config.Config, pedidos: list[str] | None) -> list[str]:
    if pedidos:
        for nome in pedidos:
            if not modelos.disponivel(nome):
                pacote = modelos.REGISTRO[nome].pacote
                raise SystemExit(f"ERRO {nome} requer o pacote {pacote}; instale com: {instalar(pacote)}")
        return list(pedidos)
    nomes = []
    for nome in cfg.modelos:
        if modelos.disponivel(nome):
            nomes.append(nome)
        else:
            pacote = modelos.REGISTRO[nome].pacote
            print(f"AVISO {nome} pulado: pacote {pacote} nao instalado ({instalar(pacote)})")
    return nomes


def escopos_pedidos(cfg: config.Config, pedidos: list[str] | None) -> list[str]:
    if pedidos:
        return list(pedidos)
    escopos = []
    for cenario in ("unico", "regional"):
        if cenario in cfg.cenarios:
            escopos += list(ESCOPOS_DO_CENARIO[cenario])
    return escopos


def janelas_pedidas(cfg: config.Config, pedidos: list[int] | None) -> list[int]:
    validas = risco.janelas(cfg)
    if not pedidos:
        return list(validas)
    for janela in pedidos:
        if janela not in validas:
            raise SystemExit(f"ERRO janela {janela} nao configurada; validas: {', '.join(str(j) for j in validas)}")
    return list(pedidos)


def analisador() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=script(), description="Risco anual de incendio no Acre: fontes, validacao, predicao e protocolos")
    ap.add_argument("--config", type=Path, default=Path(__file__).resolve().parent / "config_risco.json")
    ap.add_argument("--reconstruir-cache", action="store_true", help="reconstroi o cache das fontes mesmo que esteja valido")
    sub = ap.add_subparsers(dest="subcomando", required=True)
    sub.add_parser("fontes", help="confere as fontes, grava o relatorio, as camadas de cicatriz e clima e o indice")
    validar = sub.add_parser("validar", help="ajusta os hiperparametros por validacao cruzada e grava no banco")
    validar.add_argument("--modelo", action="append")
    validar.add_argument("--escopo", action="append", choices=["acre", "oeste", "leste"])
    validar.add_argument("--janela", action="append", type=int)
    validar.add_argument("--refazer", action="store_true")
    prever = sub.add_parser("prever", help="treina com os parametros do banco, preve, avalia e grava mapas e tabelas")
    prever.add_argument("--modelo", action="append")
    prever.add_argument("--cenario", action="append", choices=["atual", "unico", "regional"])
    prever.add_argument("--ano", action="append", type=int)
    prever.add_argument("--parametros-padrao", action="store_true")
    prever.add_argument("--rolante", action="store_true")
    sub.add_parser("protocolos", help="compara a validacao aleatoria com a espacial (so relatorio)")
    tudo = sub.add_parser("tudo", help="fontes, validar, prever e protocolos com a mesma base")
    tudo.add_argument("--rolante", action="store_true")
    tudo.set_defaults(modelo=None, escopo=None, janela=None, refazer=False, ano=None, cenario=None, parametros_padrao=False)
    return ap


def cmd_fontes(ctx: Contexto, base: fontes.Base | None = None) -> fontes.Base:
    cfg = ctx.cfg
    with execucao.etapa("fontes", ctx.tempos):
        base = base if base is not None else carregar(ctx)
        fontes.gravar_json(config.destino(cfg, "relatorio_fontes.json"), base.relatorio)
        config.limpar(cfg, "camadas", ["*.tif"])
        grade = mapas.grade_saida(base.est)
        for ano in base.anos_cicatriz:
            mapas.gravar_cicatriz(config.destino(cfg, "camadas", f"cicatriz_{ano}.tif"), grade, base.est[f"queimou_{ano}"].to_numpy(), ano)
        for ano in base.anos_clima:
            clima_ano = base.clima_anual[base.clima_anual["ano"] == ano]
            mapas.gravar_clima(config.destino(cfg, "camadas", f"clima_{ano}.tif"), base.perfil_clima, clima_ano, ano)
        mapas.gravar_indice(cfg.saida, config.destino(cfg, "tabelas", "indice_rasters.csv"), comuns(ctx))
        print(f"[fontes] {len(base.anos_cicatriz)} camadas de cicatriz e {len(base.anos_clima)} de clima em {config.pasta_destino(cfg, 'camadas')}")
    return base


def chave_para(cfg: config.Config, nome: str, escopo: str, ultimo_ano: int, defasagem: int, X: np.ndarray, y: np.ndarray, anos: np.ndarray, lista: list[dict]) -> banco.Chave:
    return banco.Chave(
        modelo=nome,
        escopo=escopo,
        ultimo_ano_treino=int(ultimo_ano),
        fonte_cicatriz=config.fonte_cicatriz(cfg),
        preditores=",".join(cfg.preditores),
        agrupamento_cv=config.texto_agrupamento(cfg),
        n_pastas=ajuste.n_pastas_efetivo(anos, cfg.agrupamento, cfg.n_pastas),
        semente=int(cfg.semente),
        divisao="nenhuma" if escopo == "acre" else risco.texto_divisao(cfg.divisao),
        defasagem_clima=int(defasagem),
        metrica=cfg.metrica,
        impressao_espaco=modelos.impressao_espaco(lista),
        impressao_tabela=risco.impressao_tabela(X, y, anos),
    )


def tabela_janela(base: fontes.Base, cfg: config.Config, regiao: np.ndarray, escopo: str, janela: int, defasagem: int) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    anos = [a for a in risco.anos_treino(base, cfg) if a <= janela]
    tab = risco.tabela_treino(base, regiao, escopo, anos, defasagem, cfg.semente)
    X, y, anos_tab = risco.matriz_janela(tab, cfg.preditores, janela)
    return tab, X, y, anos_tab


def conferir_tabela(cfg: config.Config, escopo: str, janela: int, y: np.ndarray, anos_tab: np.ndarray) -> None:
    positivos = int(np.asarray(y).sum())
    if positivos < cfg.min_positivos:
        raise SystemExit(f"ERRO escopo {escopo} janela <={janela}: {positivos} positivos; minimo {cfg.min_positivos} (min_positivos)")
    n = ajuste.n_pastas_efetivo(anos_tab, cfg.agrupamento, cfg.n_pastas)
    if cfg.agrupamento == "ano" and n < 2:
        raise SystemExit(f"ERRO escopo {escopo} janela <={janela}: {n} ano(s) de treino; a validacao cruzada por ano precisa de pelo menos 2")


def dobras_de(cfg: config.Config, base: fontes.Base, tab: pd.DataFrame, janela: int, anos_tab: np.ndarray, y: np.ndarray) -> list:
    blocos = None
    if cfg.agrupamento == "bloco_espacial":
        celulas = tab.loc[tab["ano"] <= janela, "celula"].to_numpy()
        blocos = bloco_espacial(base.est.iloc[celulas], cfg.lado_bloco_m)
    return ajuste.pastas(anos_tab, y, cfg.agrupamento, cfg.n_pastas, cfg.semente, blocos)


def cmd_validar(ctx: Contexto, base: fontes.Base | None = None) -> None:
    cfg, args = ctx.cfg, ctx.args
    with execucao.etapa("validar", ctx.tempos) as linha_tempo:
        base = base if base is not None else carregar(ctx)
        avisar_memoria()
        nomes = modelos_pedidos(cfg, args.modelo)
        escopos = escopos_pedidos(cfg, args.escopo)
        lista_janelas = janelas_pedidas(cfg, args.janela)
        regiao = risco.regiao_de(base.est, cfg.divisao)
        defasagens = [cfg.defasagem_principal] + (list(cfg.defasagens_comparacao) if cfg.ajustar_comparacao else [])
        planos = []
        for janela in lista_janelas:
            for escopo in escopos:
                for defasagem in defasagens:
                    tab, X, y, anos_tab = tabela_janela(base, cfg, regiao, escopo, janela, defasagem)
                    conferir_tabela(cfg, escopo, janela, y, anos_tab)
                    planos.append((janela, escopo, defasagem, X, y, anos_tab, dobras_de(cfg, base, tab, janela, anos_tab, y)))
        con = banco.conectar(cfg.banco)
        try:
            execucao_id = banco.iniciar_execucao(con, " ".join(ctx.comando), ctx.impressao_config, base.impressao_fontes)
            linha_tempo["execucao"] = execucao_id
            situacao = "interrompida"
            try:
                pastas_cv = []
                for janela, escopo, defasagem, X, y, anos_tab, dobras in planos:
                    tabela = ajuste.anos_por_pasta(anos_tab, y, dobras)
                    for p in tabela.itertuples(index=False):
                        print(f"[pastas {escopo} <={janela} d{defasagem}] pasta {p.pasta}: anos {p.anos}; {p.n_linhas} linhas, {p.n_positivos} positivos")
                    pastas_cv.append(tabela.assign(escopo=escopo, janela=janela, defasagem_clima=defasagem))
                    for nome in nomes:
                        lista = modelos.candidatos(nome, cfg.espacos)
                        chave = chave_para(cfg, nome, escopo, janela, defasagem, X, y, anos_tab, lista)
                        if not args.refazer and banco.vencedor(con, chave) is not None:
                            print(f"PULADO {nome} {escopo} <={janela} d{defasagem}: ja existe no banco (use --refazer)")
                            continue
                        rotulo = f"{nome} {escopo} <={janela} d{defasagem}"
                        resultado = ajuste.buscar(
                            nome, X, y, anos_tab, janela, lista, cfg.semente, cfg.preditores, dobras,
                            modelos.REGISTRO[nome].n_jobs_busca, cfg.metrica, rotulo,
                        )
                        banco.gravar_chave(con, execucao_id, chave, resultado, len(y), int(np.asarray(y).sum()))
                colunas = ["escopo", "janela", "defasagem_clima", "pasta", "anos", "n_linhas", "n_positivos"]
                tabela_pastas = pd.concat(pastas_cv, ignore_index=True)[colunas] if pastas_cv else pd.DataFrame(columns=colunas)
                execucao.gravar_tabela(tabela_pastas, config.destino(cfg, "tabelas", "pastas_cv.csv"), comuns(ctx))
                banco.exportar_csv(con, config.pasta_destino(cfg, "tabelas"), comuns(ctx))
                situacao = "concluida"
            finally:
                banco.finalizar_execucao(con, execucao_id, situacao)
        finally:
            con.close()


@dataclass
class Consulta:
    parametros: dict
    origem: str
    janela: int
    defasagem: int
    chave_id: int | None = None
    execucao_id: int | None = None


@dataclass
class Variante:
    ano: int
    variante: str
    cenario: str
    modelo: str
    defasagem_clima: int | None
    defasagem_parametros: int | None
    reaproveitou: bool
    consultas: dict[str, Consulta]
    avaliar: bool


@dataclass
class Predicao:
    ano: int
    cenario: str
    modelo: str
    defasagem_clima: int | None
    defasagem_parametros: int | None
    reaproveitou_parametros: bool
    origem_parametros: str
    janela_parametros: int | None
    p: np.ndarray
    escopo_modelo: np.ndarray
    ajustados: dict[str, tuple[object, np.ndarray, np.ndarray]]
    variante: str = "principal"
    consultas: dict[str, Consulta] = field(default_factory=dict)


@dataclass
class Plano:
    principais: list[Variante]
    rolantes: list[Variante]
    nomes: list[str]
    janelas: list[int]


def motivo_nao_avaliavel(base: fontes.Base, ano: int) -> str:
    if ano not in base.anos_cicatriz:
        return "sem banda de cicatriz"
    return f"clima de {ano} incompleto"


def cenarios_pedidos(cfg: config.Config, pedidos: list[str] | None) -> list[str]:
    if not pedidos:
        return list(cfg.cenarios)
    for cenario in pedidos:
        if cenario not in cfg.cenarios:
            raise SystemExit(f"ERRO cenario {cenario} nao configurado; validos: {', '.join(cfg.cenarios)}")
    return list(pedidos)


class Consultor:
    def __init__(self, ctx: Contexto, base: fontes.Base, regiao: np.ndarray, con):
        self.ctx, self.cfg, self.base, self.regiao, self.con = ctx, ctx.cfg, base, regiao, con
        self.tabelas: dict[tuple, tuple] = {}

    def tabela(self, escopo: str, janela: int, defasagem: int) -> tuple:
        chave = (escopo, janela, defasagem)
        if chave not in self.tabelas:
            tab, X, y, anos = tabela_janela(self.base, self.cfg, self.regiao, escopo, janela, defasagem)
            conferir_tabela(self.cfg, escopo, janela, y, anos)
            self.tabelas[chave] = (tab, X, y, anos)
        return self.tabelas[chave]

    def consultar(self, nome: str, escopo: str, janela: int, defasagem: int, propria: bool) -> Consulta:
        _, X, y, anos = self.tabela(escopo, janela, defasagem)
        if self.ctx.args.parametros_padrao:
            return Consulta(dict(modelos.REGISTRO[nome].padrao), "padrao", janela, defasagem)
        lista = modelos.candidatos(nome, self.cfg.espacos)
        chave = chave_para(self.cfg, nome, escopo, janela, defasagem, X, y, anos, lista)
        achado = banco.vencedor(self.con, chave) if self.con is not None else None
        if achado is None:
            mensagem = (
                f"ERRO sem parametros no banco para {nome}/{escopo}/janela<={janela}/defasagem {defasagem}; "
                f"rode: python {script()} validar --modelo {nome} --escopo {escopo} --janela {janela}"
            )
            if propria:
                mensagem += " com clima.ajustar_comparacao = true na configuracao"
            outras = banco.outras_chaves(self.con, chave) if self.con is not None else 0
            if outras:
                mensagem += f" (ha {outras} entradas com outros dados, corte, defasagem, fonte ou espaco de busca)"
            raise SystemExit(mensagem)
        return Consulta(achado["parametros"], "banco", janela, defasagem, achado["chave_id"], achado["execucao_id"])

    def variante(self, ano: int, codigo: str, cenario: str, nome: str, defasagem: int, defasagem_parametros: int, avaliar: bool) -> Variante:
        janela = risco.janela_para(ano, self.cfg.anos_previsao)
        propria = codigo == "comparacao_propria"
        consultas = {e: self.consultar(nome, e, janela, defasagem_parametros, propria) for e in ESCOPOS_DO_CENARIO[cenario]}
        treino = [a for a in risco.anos_treino(self.base, self.cfg) if a <= ano - 1]
        for escopo in ESCOPOS_DO_CENARIO[cenario]:
            self.tabela_treino_previsao(escopo, ano, defasagem, treino)
        return Variante(ano, codigo, cenario, nome, defasagem, defasagem_parametros, codigo == "comparacao_reaproveitada", consultas, avaliar)

    def tabela_treino_previsao(self, escopo: str, ano: int, defasagem: int, treino: list[int]) -> None:
        chave = ("previsao", escopo, ano, defasagem)
        if chave in self.tabelas:
            return
        tab = risco.tabela_treino(self.base, self.regiao, escopo, treino, defasagem, self.cfg.semente)
        X, y, anos = risco.matriz_janela(tab, self.cfg.preditores, ano - 1)
        conferir_tabela(self.cfg, escopo, ano - 1, y, anos)
        self.tabelas[chave] = (tab, X, y, anos)

    def treino(self, escopo: str, ano: int, defasagem: int) -> tuple:
        return self.tabelas[("previsao", escopo, ano, defasagem)]


def planejar_prever(ctx: Contexto, base: fontes.Base, consultor: Consultor) -> Plano:
    cfg, args = ctx.cfg, ctx.args
    dp = cfg.defasagem_principal
    if args.ano:
        fora = [a for a in args.ano if a not in cfg.anos_previsao and a not in cfg.anos_rolantes]
        if fora:
            raise SystemExit(f"ERRO ano {fora[0]} fora de anos_previsao e anos_rolantes")
        principais = [a for a in args.ano if a in cfg.anos_previsao]
        rolantes = [a for a in args.ano if a in cfg.anos_rolantes]
    else:
        principais = list(cfg.anos_previsao)
        rolantes = list(cfg.anos_rolantes) if args.rolante else []
        if args.rolante and not cfg.anos_rolantes:
            print("AVISO --rolante: anos_rolantes vazio; avaliacao rolante pulada")
    nomes = modelos_pedidos(cfg, args.modelo)
    cenarios = cenarios_pedidos(cfg, args.cenario)
    com_modelo = [c for c in ("unico", "regional") if c in cenarios]
    lista_principal: list[Variante] = []
    lista_rolante: list[Variante] = []
    janelas_usadas = []
    anos_clima = ", ".join(str(a) for a in base.anos_clima)
    for ano in principais:
        janelas_usadas.append(risco.janela_para(ano, cfg.anos_previsao))
        if not risco.ano_previsivel(base, ano, dp):
            raise SystemExit(f"ERRO ano {ano}: sem clima completo em {ano - dp} (defasagem {dp}); anos com clima: {anos_clima}")
        avaliavel = risco.ano_avaliavel(base, ano)
        if not avaliavel:
            print(f"AVISO ano {ano}: {motivo_nao_avaliavel(base, ano)}; avaliacao e analise puladas")
        comparacoes = []
        for d in cfg.defasagens_comparacao:
            if not risco.ano_previsivel(base, ano, d):
                print(f"AVISO ano {ano}: sem comparacao com a defasagem {d} (sem clima completo em {ano - d})")
            elif not avaliavel:
                print(f"AVISO ano {ano}: sem comparacao com a defasagem {d} ({motivo_nao_avaliavel(base, ano)})")
            else:
                comparacoes.append(d)
        if "atual" in cenarios and avaliavel:
            for nome in nomes_do_atual(nomes):
                lista_principal.append(Variante(ano, "atual", "atual", nome, None, None, False, {}, True))
        for cenario in com_modelo:
            for nome in nomes:
                lista_principal.append(consultor.variante(ano, "principal", cenario, nome, dp, dp, avaliavel))
                for d in comparacoes:
                    lista_principal.append(consultor.variante(ano, "comparacao_reaproveitada", cenario, nome, d, dp, True))
                    if cfg.ajustar_comparacao:
                        lista_principal.append(consultor.variante(ano, "comparacao_propria", cenario, nome, d, d, True))
    for ano in rolantes:
        janela = risco.janela_para(ano, cfg.anos_previsao)
        if not risco.ano_previsivel(base, ano, dp):
            print(f"AVISO ano {ano}: sem clima completo em {ano - dp} (defasagem {dp}); fora da avaliacao rolante")
            continue
        if not risco.ano_avaliavel(base, ano):
            print(f"AVISO ano {ano}: {motivo_nao_avaliavel(base, ano)}; fora da avaliacao rolante")
            continue
        janelas_usadas.append(janela)
        for cenario in com_modelo:
            for nome in nomes:
                lista_rolante.append(consultor.variante(ano, "rolante", cenario, nome, dp, dp, True))
    return Plano(lista_principal, lista_rolante, nomes, sorted(set(janelas_usadas)))


def nomes_do_atual(nomes: list[str]) -> list[str]:
    zoo = [nome_zoo(n) for n in modelos.zoo()]
    return [n for n in zoo if n in nomes]


def nome_zoo(nome: str) -> str:
    return "FuzzyKNN" if nome.startswith("FuzzyKNN") else nome


def prever_variante(base: fontes.Base, cfg: config.Config, consultor: Consultor, regiao: np.ndarray, variante: Variante) -> Predicao:
    n = len(base.est)
    partes, ajustados = {}, {}
    for escopo, consulta in variante.consultas.items():
        _, X, y, anos = consultor.treino(escopo, variante.ano, variante.defasagem_clima)
        if variante.ano <= int(anos.max()):
            raise SystemExit(f"ERRO ano {variante.ano}: nao e maior que o ultimo ano de treino {int(anos.max())}")
        estimador = modelos.criar(variante.modelo, consulta.parametros, cfg.semente, cfg.preditores)
        estimador.fit(X, y)
        celulas = np.arange(n) if escopo == "acre" else np.flatnonzero(regiao == escopo)
        X_previsao = risco.matriz_predicao(base, cfg.preditores, variante.ano, variante.defasagem_clima, celulas)
        partes[escopo] = (celulas, estimador.predict_proba(X_previsao)[:, 1])
        ajustados[escopo] = (estimador, X, y)
    if variante.cenario == "unico":
        p, escopo_modelo = partes["acre"][1], np.full(n, "acre", dtype=object)
    else:
        p, escopo_modelo = risco.juntar_regional(partes, n, f"{variante.ano}/{variante.modelo}")
    consulta = next(iter(variante.consultas.values()))
    return Predicao(
        variante.ano, variante.cenario, variante.modelo, variante.defasagem_clima, variante.defasagem_parametros,
        variante.reaproveitou, consulta.origem, consulta.janela, np.asarray(p, dtype=np.float64), escopo_modelo,
        ajustados, variante.variante, variante.consultas,
    )


METRICAS_AVALIACAO = ["prevalencia", "roc_auc", "pr_auc", "razao_pr_auc_prevalencia", "brier", "det@1%", "det@5%", "det@10%", "det@20%"]
ORDEM_RECORTE = {"acre": 0, "oeste": 1, "leste": 2}
COLUNAS_IDENTIFICACAO = ["ano", "cenario", "variante", "defasagem_clima", "defasagem_parametros", "reaproveitou_parametros", "modelo", "origem_parametros", "janela_parametros"]
COLUNAS_AVALIACAO = ["ano", "recorte", "cenario", "variante", "defasagem_clima", "defasagem_parametros", "reaproveitou_parametros", "modelo", "origem_parametros", "janela_parametros", "n_celulas", "n_positivos", *METRICAS_AVALIACAO]
COLUNAS_PARAMETROS = ["ano", "variante", "cenario", "escopo", "modelo", "defasagem_parametros", "janela_parametros", "origem_parametros", "chave_id", "execucao_id", "parametros"]


def identificacao(pred: Predicao) -> dict:
    return {
        "ano": pred.ano,
        "cenario": pred.cenario,
        "variante": pred.variante,
        "defasagem_clima": pred.defasagem_clima,
        "defasagem_parametros": pred.defasagem_parametros,
        "reaproveitou_parametros": pred.reaproveitou_parametros,
        "modelo": pred.modelo,
        "origem_parametros": pred.origem_parametros,
        "janela_parametros": pred.janela_parametros,
    }


def avaliar_predicao(base: fontes.Base, regiao: np.ndarray, pred: Predicao) -> list[dict]:
    y = base.est[f"queimou_{pred.ano}"].to_numpy().astype(np.int64)
    linhas = []
    for recorte in ORDEM_RECORTE:
        sel = np.ones(len(y), dtype=bool) if recorte == "acre" else regiao == recorte
        metricas = risco.avaliar_subconjunto(y[sel], pred.p[sel], f"{pred.ano}/{recorte}/{pred.cenario}/{pred.variante}/{pred.modelo}")
        prevalencia = metricas["prevalencia"]
        razao = metricas["pr_auc"] / prevalencia if prevalencia and np.isfinite(prevalencia) else float("nan")
        linha = {**identificacao(pred), "recorte": recorte, "n_celulas": int(sel.sum()), "n_positivos": int(y[sel].sum())}
        linha.update({m: metricas[m] for m in metricas})
        linha["razao_pr_auc_prevalencia"] = razao
        linhas.append(linha)
    return linhas


def tabela_avaliacao(linhas: list[dict]) -> pd.DataFrame:
    tabela = pd.DataFrame(linhas, columns=COLUNAS_AVALIACAO)
    if tabela.empty:
        return tabela
    tabela["_ordem"] = tabela["recorte"].map(ORDEM_RECORTE)
    tabela = tabela.sort_values(["ano", "_ordem", "pr_auc"], ascending=[True, True, False], na_position="last", kind="mergesort")
    return tabela.drop(columns="_ordem").reset_index(drop=True)


def coluna_resumo(linha: dict, dp: int) -> str:
    if linha["variante"] == "atual":
        return "atual"
    if linha["variante"] == "principal":
        return f"{linha['cenario']}_d{dp}"
    sufixo = "reap" if linha["variante"] == "comparacao_reaproveitada" else "proprio"
    return f"{linha['cenario']}_d{int(linha['defasagem_clima'])}_{sufixo}"


def resumo_cenarios(tabela: pd.DataFrame, cfg: config.Config) -> pd.DataFrame:
    dp, dc = cfg.defasagem_principal, cfg.defasagens_comparacao
    ordem = ["atual"] + [f"{c}_d{dp}" for c in ("unico", "regional")]
    ordem += [f"{c}_d{d}_{s}" for s in ("reap", "proprio") for d in dc for c in ("unico", "regional")]
    if tabela.empty:
        return pd.DataFrame(columns=["ano", "recorte", "modelo"])
    base = tabela.assign(coluna=[coluna_resumo(r, dp) for r in tabela.to_dict("records")])
    pivo = base.pivot(index=["ano", "recorte", "modelo"], columns="coluna", values="pr_auc")
    pivo = pivo[[c for c in ordem if c in pivo.columns]].reset_index()
    pivo.columns.name = None
    pivo["_ordem"] = pivo["recorte"].map(ORDEM_RECORTE)
    pivo = pivo.sort_values(["ano", "_ordem", "modelo"], kind="mergesort").drop(columns="_ordem")
    return pivo.reset_index(drop=True)


def parametros_usados(variantes: list[Variante]) -> pd.DataFrame:
    linhas = []
    for v in variantes:
        for escopo, consulta in v.consultas.items():
            linhas.append({
                "ano": v.ano,
                "variante": v.variante,
                "cenario": v.cenario,
                "escopo": escopo,
                "modelo": v.modelo,
                "defasagem_parametros": consulta.defasagem,
                "janela_parametros": consulta.janela,
                "origem_parametros": consulta.origem,
                "chave_id": consulta.chave_id,
                "execucao_id": consulta.execucao_id,
                "parametros": json.dumps(consulta.parametros, sort_keys=True),
            })
    return pd.DataFrame(linhas, columns=COLUNAS_PARAMETROS)


def gravar_parquet(tabela: pd.DataFrame, caminho: Path) -> None:
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        tabela.to_parquet(temporario, index=False, compression="zstd")
        temporario.replace(caminho)
    except OSError as erro:
        raise SystemExit(f"ERRO ao gravar {caminho}: {erro}") from None


def figura_caixas(grupos: dict[str, np.ndarray], ano: int):
    fig, ax = plt.subplots(figsize=(max(6.0, 0.9 * len(grupos) + 2), 5.5))
    ax.boxplot(list(grupos.values()), showfliers=False)
    ax.set_xticks(range(1, len(grupos) + 1), list(grupos), rotation=60, ha="right")
    ax.set_ylim(0, 100)
    ax.set_ylabel("Risco (%)")
    ax.set_title(f"Risco nas células com cicatriz em {ano} (cenário | modelo)")
    fig.tight_layout()
    return fig


class Coletor:
    def __init__(self, ctx: Contexto, base: fontes.Base, regiao: np.ndarray):
        self.ctx, self.cfg, self.base, self.regiao = ctx, ctx.cfg, base, regiao
        self.grade = mapas.grade_saida(base.est)
        self.avaliacao: list[dict] = []
        self.rolante: list[dict] = []
        self.estatisticas: list[pd.DataFrame] = []
        self.coeficientes: list[dict] = []
        self.fora: list[pd.DataFrame] = []
        self.pendentes: dict[tuple[int, str], dict[str, Predicao]] = {}
        self.caixas: dict[int, dict[str, np.ndarray]] = {}

    def cicatriz(self, ano: int) -> np.ndarray | None:
        if not risco.ano_avaliavel(self.base, ano):
            return None
        return self.base.est[f"queimou_{ano}"].to_numpy().astype(np.int8)

    def registrar(self, pred: Predicao, avaliar: bool) -> None:
        if avaliar:
            linhas = avaliar_predicao(self.base, self.regiao, pred)
            (self.rolante if pred.variante == "rolante" else self.avaliacao).extend(linhas)
            if pred.variante != "rolante":
                cicatriz = self.cicatriz(pred.ano)
                risco_pct = (100 * pred.p).astype(np.float32)
                tabela = risco.estatisticas_risco(risco_pct, cicatriz, self.regiao, self.cfg.limiares)
                ident = identificacao(pred)
                for coluna in reversed(COLUNAS_IDENTIFICACAO):
                    tabela.insert(0, coluna, ident[coluna])
                self.estatisticas.append(tabela)
                if pred.variante in ("atual", "principal") and (cicatriz == 1).any():
                    self.caixas.setdefault(pred.ano, {})[f"{pred.cenario} | {pred.modelo}"] = risco_pct[cicatriz == 1]
        if pred.modelo == "RegLogistica" and pred.variante in ("atual", "principal"):
            self.analisar_reglog(pred)
        if pred.variante == "principal" and pred.cenario in self.cfg.mapas_cenarios:
            self.gravar_modelo_e_mapa(pred)
            pred.ajustados = {}
            self.pendentes.setdefault((pred.ano, pred.cenario), {})[pred.modelo] = pred
        pred.ajustados = {}

    def analisar_reglog(self, pred: Predicao) -> None:
        colunas = list(PREDITORES) if pred.variante == "atual" else list(self.cfg.preditores)
        for escopo, (estimador, _, _) in pred.ajustados.items():
            passos = estimador.named_steps
            transformacao = "log1p" if "log1p" in passos and len(passos["log1p"].indices) else "nenhuma"
            for variavel, valor in risco.coeficientes(estimador, colunas).items():
                self.coeficientes.append({
                    "ano": pred.ano, "cenario": pred.cenario, "variante": pred.variante, "escopo_modelo": escopo,
                    "variavel": variavel, "coeficiente": valor, "C": float(passos["modelo"].C), "transformacao": transformacao,
                })
        oeste = np.flatnonzero(self.regiao == "oeste")
        escopo = "oeste" if "oeste" in pred.ajustados else "acre"
        _, X_treino, y_treino = pred.ajustados[escopo]
        if pred.variante == "atual":
            X_oeste = self.base.est.iloc[oeste][PREDITORES].to_numpy(dtype=np.float64)
        else:
            X_oeste = risco.matriz_predicao(self.base, self.cfg.preditores, pred.ano, pred.defasagem_clima, oeste)
        tabela = risco.fora_da_faixa(X_oeste, X_treino, y_treino, colunas)
        for coluna, valor in reversed((("ano", pred.ano), ("cenario", pred.cenario), ("variante", pred.variante), ("escopo_modelo", escopo))):
            tabela.insert(0, coluna, valor)
        self.fora.append(tabela)

    def gravar_modelo_e_mapa(self, pred: Predicao) -> None:
        cfg, ctx = self.cfg, self.ctx
        risco_pct = (100 * pred.p).astype(np.float32)
        etiquetas = {
            "ano": pred.ano, "cenario": pred.cenario, "modelo": pred.modelo, "defasagem_clima": pred.defasagem_clima,
            "origem_parametros": pred.origem_parametros, "janela_parametros": pred.janela_parametros,
            "rodada": ctx.rodada, "impressao_config": ctx.impressao_config,
        }
        nome = f"risco_{pred.ano}_{pred.cenario}_{pred.modelo}"
        mapas.gravar_risco(config.destino(cfg, "mapas", f"{nome}.tif"), self.grade, risco_pct, etiquetas)
        figura = mapas.figura_risco(self.grade, risco_pct, self.cicatriz(pred.ano), mapas.titulo_risco(pred.ano, pred.cenario, pred.modelo), pred.ano)
        mapas.gravar_png(figura, config.destino(cfg, "mapas", f"{nome}.png"))
        if not cfg.gravar_modelos:
            return
        treino = [a for a in risco.anos_treino(self.base, cfg) if a <= pred.ano - 1]
        for escopo, (estimador, _, _) in pred.ajustados.items():
            conteudo = {
                "modelo": estimador, "colunas": list(cfg.preditores), "parametros": pred.consultas[escopo].parametros,
                "janela": pred.janela_parametros, "anos_treino": treino, "defasagem_clima": pred.defasagem_clima,
                "origem_parametros": pred.origem_parametros, "escopo": escopo, "semente": cfg.semente,
                "rodada": ctx.rodada, "impressao_config": ctx.impressao_config,
            }
            caminho = config.destino(cfg, "modelos", f"risco_{pred.ano}_{pred.cenario}_{escopo}_{pred.modelo}.joblib")
            try:
                joblib.dump(conteudo, caminho, compress=3)
            except OSError as erro:
                raise SystemExit(f"ERRO ao gravar {caminho}: {erro}") from None

    def tabela_celulas(self, ano: int, cenario: str, predicoes: dict[str, Predicao]) -> pd.DataFrame:
        est, n, ctx = self.base.est, len(self.base.est), self.ctx
        cicatriz = self.cicatriz(ano)
        partes = []
        for modelo in sorted(predicoes):
            pred = predicoes[modelo]
            partes.append(pd.DataFrame({
                "celula": np.arange(n, dtype=np.int32),
                "Y": est["Y"].to_numpy().astype(np.int16),
                "X": est["X"].to_numpy().astype(np.int16),
                "lin": self.grade.lin.astype(np.int16),
                "col": self.grade.col.astype(np.int16),
                "x_g": est["x_g"].to_numpy(dtype=np.float64),
                "y_g2": est["y_g2"].to_numpy(dtype=np.float64),
                "lon": est["lon"].to_numpy(dtype=np.float64),
                "lat": est["lat"].to_numpy(dtype=np.float64),
                "regiao": self.regiao,
                "escopo_modelo": pred.escopo_modelo.astype(str),
                "cenario": cenario,
                "modelo": modelo,
                "origem_parametros": pred.origem_parametros,
                "ano": np.full(n, ano, dtype=np.int16),
                "janela_parametros": np.full(n, pred.janela_parametros, dtype=np.int16),
                "defasagem_clima": np.full(n, pred.defasagem_clima, dtype=np.int8),
                "risco_pct": (100 * pred.p).astype(np.float32),
                "cicatriz": pd.array(cicatriz if cicatriz is not None else [pd.NA] * n, dtype="Int8"),
                "rodada": ctx.rodada,
                "impressao_config": ctx.impressao_config,
            }))
        tabela = pd.concat(partes, ignore_index=True)
        for coluna in ("regiao", "escopo_modelo", "cenario", "modelo", "origem_parametros", "rodada", "impressao_config"):
            tabela[coluna] = tabela[coluna].astype("category")
        return tabela

    def finalizar_mapas(self) -> None:
        cfg = self.cfg
        for (ano, cenario), predicoes in sorted(self.pendentes.items()):
            gravar_parquet(self.tabela_celulas(ano, cenario, predicoes), config.destino(cfg, "predicoes", f"risco_celulas_{ano}_{cenario}.parquet"))
            riscos = {m: (100 * predicoes[m].p).astype(np.float32) for m in predicoes}
            figura = mapas.figura_painel(self.grade, riscos, self.cicatriz(ano), f"Risco de incêndio {ano} | {cenario}", ano)
            mapas.gravar_png(figura, config.destino(cfg, "mapas", f"painel_risco_{ano}_{cenario}.png"))
        self.pendentes = {}
        for ano, grupos in sorted(self.caixas.items()):
            mapas.gravar_png(figura_caixas(grupos, ano), config.destino(cfg, "figuras", f"caixas_risco_{ano}.png"))
        self.caixas = {}

    def gravar_principais(self, nomes: list[str]) -> None:
        cfg, comum = self.cfg, comuns(self.ctx)
        tabela = tabela_avaliacao(self.avaliacao)
        execucao.gravar_tabela(tabela, config.destino(cfg, "tabelas", "avaliacao.csv"), comum)
        execucao.gravar_tabela(resumo_cenarios(tabela, cfg), config.destino(cfg, "tabelas", "resumo_cenarios.csv"), comum)
        estatisticas = pd.concat(self.estatisticas, ignore_index=True) if self.estatisticas else pd.DataFrame(columns=COLUNAS_IDENTIFICACAO + ["recorte", "grupo", "n"])
        execucao.gravar_tabela(estatisticas, config.destino(cfg, "tabelas", "risco_nas_cicatrizes.csv"), comum)
        if "RegLogistica" in nomes:
            colunas = ["ano", "cenario", "variante", "escopo_modelo", "variavel", "coeficiente", "C", "transformacao"]
            execucao.gravar_tabela(pd.DataFrame(self.coeficientes, columns=colunas), config.destino(cfg, "tabelas", "reglog_coeficientes.csv"), comum)
            fora = pd.concat(self.fora, ignore_index=True) if self.fora else pd.DataFrame(columns=["ano", "cenario", "variante", "escopo_modelo", "variavel"])
            execucao.gravar_tabela(fora, config.destino(cfg, "tabelas", "reglog_fora_da_faixa.csv"), comum)

    def gravar_rolante(self) -> None:
        execucao.gravar_tabela(tabela_avaliacao(self.rolante), config.destino(self.cfg, "tabelas", "avaliacao_rolante.csv"), comuns(self.ctx))


LIMPEZA_PREVER = {
    "mapas": ["*.tif", "*.png"],
    "predicoes": ["*.parquet"],
    "modelos": ["*.joblib"],
    "figuras": ["*.png"],
    "tabelas": ["avaliacao.csv", "avaliacao_rolante.csv", "resumo_cenarios.csv", "risco_nas_cicatrizes.csv", "reglog_*.csv", "parametros_usados.csv"],
}


def processar(ctx: Contexto, base: fontes.Base, consultor: Consultor, regiao: np.ndarray, variantes: list[Variante], coletor: Coletor) -> None:
    atuais: dict[int, list[str]] = {}
    for v in variantes:
        if v.variante == "atual":
            atuais.setdefault(v.ano, []).append(v.modelo)
    feitos = set()
    total = len(variantes)
    i = 0
    for v in variantes:
        if v.variante == "atual":
            if v.ano in feitos:
                continue
            feitos.add(v.ano)
            predicoes = prever_atual(base, ctx.cfg, v.ano, atuais[v.ano])
        else:
            predicoes = [prever_variante(base, ctx.cfg, consultor, regiao, v)]
        for pred in predicoes:
            i += 1
            print(f"[prever] {i}/{total} {pred.ano} {pred.variante} {pred.cenario} {pred.modelo} d{pred.defasagem_clima if pred.defasagem_clima is not None else '-'}")
            coletor.registrar(pred, v.avaliar)


def cmd_prever(ctx: Contexto, base: fontes.Base | None = None) -> None:
    cfg, args = ctx.cfg, ctx.args
    with execucao.etapa("prever", ctx.tempos):
        base = base if base is not None else carregar(ctx)
        avisar_memoria()
        regiao = risco.regiao_de(base.est, cfg.divisao)
        con = None if args.parametros_padrao else banco.conectar(cfg.banco, criar=False)
        try:
            consultor = Consultor(ctx, base, regiao, con)
            plano = planejar_prever(ctx, base, consultor)
        finally:
            if con is not None:
                con.close()
        if args.ano or args.modelo or args.cenario:
            print("AVISO saida parcial (filtros); rode sem filtros para a rodada final")
        else:
            for pasta, padroes in LIMPEZA_PREVER.items():
                config.limpar(cfg, pasta, padroes)
        coletor = Coletor(ctx, base, regiao)
        if plano.principais:
            processar(ctx, base, consultor, regiao, plano.principais, coletor)
            coletor.finalizar_mapas()
            coletor.gravar_principais(plano.nomes)
        if "RegLogistica" in plano.nomes and plano.janelas:
            tabelas_cv = [cv_reglog_oeste(base, cfg, regiao, janela) for janela in plano.janelas]
            execucao.gravar_tabela(pd.concat(tabelas_cv, ignore_index=True), config.destino(cfg, "tabelas", "reglog_cv_oeste.csv"), comuns(ctx))
    if plano.rolantes:
        with execucao.etapa("rolante", ctx.tempos):
            processar(ctx, base, consultor, regiao, plano.rolantes, coletor)
            coletor.gravar_rolante()
    execucao.gravar_tabela(parametros_usados(plano.principais + plano.rolantes), config.destino(cfg, "tabelas", "parametros_usados.csv"), comuns(ctx))
    mapas.gravar_indice(cfg.saida, config.destino(cfg, "tabelas", "indice_rasters.csv"), comuns(ctx))


def media_desvio(valores: list[float]) -> tuple[float, float]:
    arr = np.asarray(valores, dtype=np.float64)
    validos = arr[np.isfinite(arr)]
    if validos.size == 0:
        return float("nan"), float("nan")
    return float(validos.mean()), float(validos.std(ddof=0))


def cv_reglog_oeste(base: fontes.Base, cfg: config.Config, regiao: np.ndarray, ultimo_ano: int) -> pd.DataFrame:
    dp = cfg.defasagem_principal
    _, X_oeste, y_oeste, anos_oeste = tabela_janela(base, cfg, regiao, "oeste", ultimo_ano, dp)
    _, X_acre, y_acre, anos_acre = tabela_janela(base, cfg, regiao, "acre", ultimo_ano, dp)
    dobras = ajuste.pastas(anos_oeste, y_oeste, "ano", cfg.n_pastas, cfg.semente)
    valores_c = sorted({float(c["C"]) for c in modelos.candidatos("RegLogistica", cfg.espacos) if "C" in c})
    linhas = []
    for cenario, (X_t, y_t, anos_t) in (("unico", (X_acre, y_acre, anos_acre)), ("regional", (X_oeste, y_oeste, anos_oeste))):
        for transformacao in ("nenhuma", "log1p"):
            for valor_c in valores_c:
                pr_auc, roc_auc = [], []
                for _, validacao in dobras:
                    y_val = y_oeste[validacao]
                    if np.unique(y_val).size < 2:
                        print(f"AVISO reglog_cv_oeste <={ultimo_ano}: pasta com uma classe; metricas NaN")
                        pr_auc.append(float("nan"))
                        roc_auc.append(float("nan"))
                        continue
                    treino = ~np.isin(anos_t, np.unique(anos_oeste[validacao]))
                    estimador = modelos.criar("RegLogistica", {"C": valor_c, "transformacao_distancias": transformacao}, cfg.semente, cfg.preditores)
                    estimador.fit(X_t[treino], y_t[treino])
                    p = estimador.predict_proba(X_oeste[validacao])[:, 1]
                    pr_auc.append(float(average_precision_score(y_val, p)))
                    roc_auc.append(float(roc_auc_score(y_val, p)))
                pr_media, pr_desvio = media_desvio(pr_auc)
                roc_media, roc_desvio = media_desvio(roc_auc)
                linhas.append({
                    "janela": ultimo_ano, "variante": f"{cenario}_{transformacao}", "cenario": cenario, "transformacao": transformacao,
                    "C": valor_c, "n_pastas": len(dobras), "pr_auc_media": pr_media, "pr_auc_desvio": pr_desvio,
                    "roc_auc_media": roc_media, "roc_auc_desvio": roc_desvio,
                })
    tabela = pd.DataFrame(linhas)
    tabela["melhor"] = False
    for _, grupo in tabela.groupby("variante", sort=False):
        valores = grupo[f"{cfg.metrica}_media"]
        if valores.notna().any():
            tabela.loc[valores.idxmax(), "melhor"] = True
    print(f"[reglog_cv_oeste <={ultimo_ano}] {len(tabela)} linhas; melhores: " + "; ".join(
        f"{r.variante} C={r.C:g} {cfg.metrica}={getattr(r, cfg.metrica + '_media'):.4f}" for r in tabela[tabela["melhor"]].itertuples()
    ))
    return tabela


def prever_atual(base: fontes.Base, cfg: config.Config, ano: int, nomes: list[str]) -> list[Predicao]:
    n = len(base.est)
    y = np.zeros(n, dtype=np.int8)
    for a in risco.anos_rotulaveis(base, 0):
        if a <= ano - 1:
            y |= base.est[f"queimou_{a}"].to_numpy().astype(np.int8)
    indices = equilibrar(y, np.random.default_rng(cfg.semente))
    X = base.est[PREDITORES].to_numpy(dtype=np.float64)
    saida = []
    for nome, estimador in modelos.zoo(cfg.semente).items():
        if nome_zoo(nome) not in nomes:
            continue
        estimador.fit(X[indices], y[indices])
        p = estimador.predict_proba(X)[:, 1]
        saida.append(Predicao(
            ano, "atual", nome_zoo(nome), None, None, False, "zoo", None, np.asarray(p, dtype=np.float64),
            np.full(n, "acre", dtype=object), {"acre": (estimador, X[indices], y[indices])}, "atual",
        ))
    return saida


USO_PROTOCOLOS = "so relatorio; janela <=2024 inclui 2016"


def comparar_protocolos(tab: pd.DataFrame, est: pd.DataFrame, colunas, nomes, semente: int, lado_bloco_m: float, uso: str = USO_PROTOCOLOS) -> pd.DataFrame:
    X = tab[list(colunas)].to_numpy(dtype=np.float64)
    y = tab["y"].to_numpy().astype(np.int64)
    grupos = bloco_espacial(est.iloc[tab["celula"].to_numpy()], lado_bloco_m)
    protocolos = {}
    menor = int(min(y.sum(), (y == 0).sum()))
    if menor < 5:
        print(f"AVISO protocolos: {menor} linhas na menor classe; protocolo aleatorio pulado")
    else:
        protocolos["aleatorio"] = list(StratifiedKFold(5, shuffle=True, random_state=1).split(X, y))
    n_blocos = int(len(np.unique(grupos)))
    if n_blocos < 5:
        print(f"AVISO protocolos: {n_blocos} blocos de {lado_bloco_m:g} m, menos que 5 pastas; protocolo espacial pulado")
    else:
        protocolos[f"espacial {lado_bloco_m / 1000:g} km"] = list(GroupKFold(5).split(X, y, groups=grupos))
    colunas_saida = ["modelo_protocolo", "modelo", "protocolo", "prevalencia", "roc_auc", "pr_auc", "brier", "det@1%", "det@5%", "det@10%", "det@20%", "uso"]
    if not protocolos:
        print("AVISO protocolos: nenhum protocolo possivel; risco_protocolos.csv nao gravado")
        return pd.DataFrame(columns=colunas_saida)
    print(f"[protocolos] {len(y)} linhas, {int(y.sum())} positivos, {n_blocos} blocos de {lado_bloco_m:g} m")
    linhas = []
    for nome in nomes:
        for protocolo, dobras in protocolos.items():
            pontos = []
            try:
                for treino, teste in dobras:
                    estimador = modelos.criar(nome, modelos.REGISTRO[nome].padrao, semente, colunas)
                    estimador.fit(X[treino], y[treino])
                    pontos.append(modelos.avaliar(y[teste], estimador.predict_proba(X[teste])[:, 1]))
            except Exception as erro:
                print(f"AVISO protocolos {nome}/{protocolo}: {type(erro).__name__}: {erro}; modelo fora da tabela")
                continue
            medias = pd.DataFrame(pontos).mean().to_dict()
            linhas.append({"modelo_protocolo": f"{nome} | {protocolo}", "modelo": nome, "protocolo": protocolo, **medias, "uso": uso})
            print(f"  {nome:14s} {protocolo:16s} roc_auc={medias['roc_auc']:.4f} pr_auc={medias['pr_auc']:.4f}")
    return pd.DataFrame(linhas, columns=colunas_saida)


def cmd_protocolos(ctx: Contexto, base: fontes.Base | None = None) -> None:
    cfg = ctx.cfg
    with execucao.etapa("protocolos", ctx.tempos):
        base = base if base is not None else carregar(ctx)
        regiao = risco.regiao_de(base.est, cfg.divisao)
        janela = max(risco.janelas(cfg))
        anos = [a for a in risco.anos_treino(base, cfg) if a <= janela]
        tab = risco.tabela_treino(base, regiao, "acre", anos, cfg.defasagem_principal, cfg.semente)
        nomes = modelos_pedidos(cfg, None)
        incluidos = [str(a) for a in cfg.anos_previsao if a <= janela]
        uso = f"so relatorio; janela <={janela} inclui {', '.join(incluidos)}" if incluidos else f"so relatorio; janela <={janela}"
        tabela = comparar_protocolos(tab, base.est, cfg.preditores, nomes, cfg.semente, cfg.lado_bloco_m, uso)
        if not tabela.empty:
            execucao.gravar_tabela(tabela, config.destino(cfg, "tabelas", "risco_protocolos.csv"), comuns(ctx))


def cmd_tudo(ctx: Contexto) -> None:
    base = cmd_fontes(ctx)
    cmd_validar(ctx, base)
    cmd_prever(ctx, base)
    cmd_protocolos(ctx, base)


def despachar(cfg: config.Config, args: argparse.Namespace, comando: list[str], log: Path) -> int:
    ctx = Contexto(cfg, args, list(comando), log.stem.removeprefix("log_"), config.impressao(cfg))
    print(f"[execucao] {' '.join(ctx.comando)} | rodada {ctx.rodada} | log {log}")
    try:
        normalizar(args)
        subcomandos = {"fontes": cmd_fontes, "validar": cmd_validar, "prever": cmd_prever, "protocolos": cmd_protocolos, "tudo": cmd_tudo}
        subcomandos[args.subcomando](ctx)
    finally:
        execucao.gravar_tempos(ctx.tempos, config.destino(cfg, "execucao", "tempos.csv"), comuns(ctx))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = analisador().parse_args(argv)
    cfg = config.carregar(args.config)
    with execucao.registrar_log(config.pasta_destino(cfg, "execucao")) as log:
        try:
            return despachar(cfg, args, [script(), *argv], log)
        except SystemExit as erro:
            if isinstance(erro.code, str):
                print(erro.code, file=sys.stderr)
                return 1
            raise
        except KeyboardInterrupt:
            print("interrompido pelo usuario", file=sys.stderr)
            return 130
        except Exception:
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(main())
