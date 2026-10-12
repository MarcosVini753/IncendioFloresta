from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import ajuste, avaliacao, banco, config, execucao, fontes, mapas, modelos, risco
from .config_v2 import Amostragem, CenarioV2

AVALIACAO_CV = "mapa_inteiro"
RAZAO_ANTERIOR = Amostragem("razao", 1)
ROTULO_ANTERIOR = {"unico": "unico_1x1_anterior", "regional": "regional_1x1_anterior"}


def comuns(ctx) -> dict:
    return {"rodada": ctx.rodada, "impressao_config": ctx.impressao_config, "comando": " ".join(ctx.comando)}


def script() -> str:
    return Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "treinar_suscetibilidade.py"


def modelos_pedidos(cfg: config.Config, pedidos: list[str] | None) -> list[str]:
    nomes = list(pedidos) if pedidos else list(cfg.modelos)
    for nome in nomes:
        if nome not in cfg.modelos:
            raise SystemExit(f"ERRO modelo {nome} fora de 'modelos' da configuracao v2; validos: {', '.join(cfg.modelos)}")
    saida = []
    for nome in nomes:
        if modelos.disponivel(nome):
            saida.append(nome)
        elif pedidos:
            raise SystemExit(f"ERRO {nome} requer o pacote {modelos.REGISTRO[nome].pacote}")
        else:
            print(f"AVISO {nome} pulado: pacote {modelos.REGISTRO[nome].pacote} nao instalado")
    return saida


def cenarios_pedidos(cfg: config.Config, pedidos: list[str] | None) -> list[CenarioV2]:
    if not pedidos:
        return list(cfg.v2.cenarios)
    return [cfg.v2.cenario(nome) for nome in pedidos]


def janelas_pedidas(cfg: config.Config, pedidos: list[int] | None) -> list[int]:
    validas = risco.janelas(cfg)
    if not pedidos:
        return list(validas)
    for janela in pedidos:
        if janela not in validas:
            raise SystemExit(f"ERRO janela {janela} nao configurada; validas: {', '.join(str(j) for j in validas)}")
    return list(pedidos)


def primeiro_candidato(cfg: config.Config, nome: str) -> dict:
    return dict(modelos.candidatos(nome, cfg.espacos, incluir_padrao=False)[0])


class Dados:
    def __init__(self, cfg: config.Config, base: fontes.Base, ultimo_ano: int):
        self.cfg = cfg
        self.v2 = cfg.v2
        self.base = base
        self.n = len(base.est)
        self.regiao = risco.regiao_de(base.est, cfg.divisao)
        self.atributos = risco.Atributos(base, cfg.defasagem_principal, self.v2.interpolacao, self.v2.historico)
        self.anos_treino = tuple(a for a in risco.anos_treino(base, cfg) if a <= int(ultimo_ano))
        if not self.anos_treino:
            raise SystemExit(f"ERRO nenhum ano de treino ate {ultimo_ano}")
        self._tabelas: dict[tuple[str, bool], risco.TabelaCompleta] = {}
        self._mascaras: dict[tuple[str, str], np.ndarray] = {}
        self._impressoes: dict[tuple, str] = {}

    def colunas(self, cenario: CenarioV2) -> tuple[str, ...]:
        return self.v2.colunas(cenario, self.cfg.preditores)

    def tabela(self, escopo: str, com_historico: bool) -> risco.TabelaCompleta:
        chave = (escopo, bool(com_historico))
        if chave not in self._tabelas:
            colunas = tuple(self.cfg.preditores) + (risco.COLUNAS_HISTORICO if com_historico else ())
            tab = risco.tabela_completa(self.atributos, self.regiao, escopo, self.anos_treino, colunas)
            print(f"[tabela {escopo}{' +historico' if com_historico else ''}] {tab.X.shape[0]} linhas x {tab.X.shape[1]} colunas, anos {tab.anos[0]}-{tab.anos[-1]}")
            self._tabelas[chave] = tab
        return self._tabelas[chave]

    def mascara(self, escopo: str, amostragem: Amostragem) -> np.ndarray:
        chave = (escopo, amostragem.texto())
        if chave not in self._mascaras:
            tab = self._tabelas.get((escopo, False)) or self._tabelas.get((escopo, True)) or self.tabela(escopo, False)
            self._mascaras[chave] = risco.mascara_amostragem(tab, amostragem.negativos_por_positivo, self.cfg.semente, self.n)
        return self._mascaras[chave]

    def impressao(self, escopo: str, com_historico: bool, amostragem: Amostragem, janela: int) -> str:
        chave = (escopo, bool(com_historico), amostragem.texto(), int(janela))
        if chave not in self._impressoes:
            tab = self.tabela(escopo, com_historico)
            fim = tab.fim(janela)
            self._impressoes[chave] = risco.impressao_tabela_v2(tab.X[:fim], tab.y[:fim], tab.ano[:fim], self.mascara(escopo, amostragem)[:fim])
        return self._impressoes[chave]

    def treino(self, escopo: str, cenario: CenarioV2, ultimo_ano: int) -> tuple[np.ndarray, np.ndarray, float]:
        tab = self.tabela(escopo, cenario.historico)
        fim = tab.fim(ultimo_ano)
        if fim == 0:
            raise SystemExit(f"ERRO {cenario.nome}/{escopo}: nenhum ano de treino ate {ultimo_ano}")
        mascara = self.mascara(escopo, cenario.amostragem)[:fim]
        beta = risco.fracao_negativos_mantidos(tab.y[:fim], mascara)
        if mascara.all():
            return tab.X[:fim], tab.y[:fim], beta
        linhas = np.flatnonzero(mascara)
        return tab.X[linhas], tab.y[linhas], beta

    def matriz_alvo(self, escopo: str, cenario: CenarioV2, ano: int) -> np.ndarray:
        celulas = risco.celulas_do_escopo(self.regiao, escopo, self.n)
        return self.atributos.matriz(self.colunas(cenario), ano, celulas)

    def cicatriz(self, ano: int) -> np.ndarray | None:
        if not risco.ano_avaliavel(self.base, ano):
            return None
        return self.base.est[f"queimou_{ano}"].to_numpy().astype(np.int8)


def chave_v2(dados: Dados, nome: str, cenario: CenarioV2, escopo: str, janela: int, lista: list[dict]) -> banco.ChaveV2:
    cfg, v2 = dados.cfg, dados.v2
    tab = dados.tabela(escopo, cenario.historico)
    anos = tab.ano[:tab.fim(janela)]
    return banco.ChaveV2(
        modelo=nome,
        escopo=escopo,
        ultimo_ano_treino=int(janela),
        fonte_cicatriz=config.fonte_cicatriz(cfg),
        preditores=risco.descritor_preditores(dados.colunas(cenario), v2.interpolacao, bool(v2.opcoes_modelo["veg_categorica"]), v2.historico if cenario.historico else None),
        agrupamento_cv=config.texto_agrupamento(cfg),
        n_pastas=ajuste.n_pastas_efetivo(anos, cfg.agrupamento, cfg.n_pastas),
        semente=int(cfg.semente),
        divisao="nenhuma" if escopo == "acre" else risco.texto_divisao(cfg.divisao),
        defasagem_clima=int(cfg.defasagem_principal),
        metrica=cfg.metrica,
        impressao_espaco=modelos.impressao_espaco(lista),
        impressao_tabela=dados.impressao(escopo, cenario.historico, cenario.amostragem, janela),
        amostragem=cenario.amostragem.texto(),
        avaliacao_cv=AVALIACAO_CV,
        opcoes_modelo=json.dumps(v2.opcoes_modelo, sort_keys=True),
    )


def conferir_treino(cfg: config.Config, rotulo: str, y: np.ndarray, anos: np.ndarray) -> None:
    positivos = int(np.asarray(y).sum())
    if positivos < cfg.min_positivos:
        raise SystemExit(f"ERRO {rotulo}: {positivos} positivos; minimo {cfg.min_positivos} (min_positivos)")
    if int(np.unique(anos).size) < 2:
        raise SystemExit(f"ERRO {rotulo}: {int(np.unique(anos).size)} ano(s) de treino; a validacao cruzada por ano precisa de pelo menos 2")


def tabela_pastas(rotulo: dict, anos: np.ndarray, y: np.ndarray, dobras: list) -> pd.DataFrame:
    linhas = []
    for i, (treino, validacao) in enumerate(dobras, start=1):
        linhas.append({
            **rotulo,
            "pasta": i,
            "anos_validacao": ",".join(str(int(a)) for a in sorted(set(anos[validacao].tolist()))),
            "n_linhas_treino": int(treino.size),
            "n_positivos_treino": int(y[treino].sum()),
            "n_linhas_validacao": int(validacao.size),
            "n_positivos_validacao": int(y[validacao].sum()),
            "prevalencia_validacao": float(y[validacao].mean()),
        })
    return pd.DataFrame(linhas)


def cmd_validar(ctx, base: fontes.Base) -> None:
    cfg, args = ctx.cfg, ctx.args
    nomes = modelos_pedidos(cfg, getattr(args, "modelo", None))
    pedidos = cenarios_pedidos(cfg, getattr(args, "cenario", None))
    for cenario in pedidos:
        if not cenario.proprio and getattr(args, "cenario", None):
            raise SystemExit(f"ERRO cenario {cenario.nome} reaproveita os parametros de {cenario.parametros}; valide {cenario.parametros}")
    cenarios = [c for c in pedidos if c.proprio]
    escopos = getattr(args, "escopo", None)
    lista_janelas = janelas_pedidas(cfg, getattr(args, "janela", None))
    dados = Dados(cfg, base, max(lista_janelas))
    opcoes = dict(cfg.v2.opcoes_modelo)
    planos = []
    for janela in lista_janelas:
        for cenario in cenarios:
            for escopo in cenario.escopos:
                if escopos and escopo not in escopos:
                    continue
                tab = dados.tabela(escopo, cenario.historico)
                fim = tab.fim(janela)
                mascara = dados.mascara(escopo, cenario.amostragem)[:fim]
                rotulo = f"{cenario.nome} {escopo} <={janela}"
                conferir_treino(cfg, rotulo, tab.y[:fim][mascara], tab.ano[:fim])
                planos.append((janela, cenario, escopo, fim, mascara))
    if not planos:
        raise SystemExit("ERRO validar: nenhuma combinacao de cenario, escopo e janela com parametros proprios")
    con = banco.conectar(cfg.banco, esquema=banco.VERSAO_ESQUEMA_V2)
    try:
        execucao_id = banco.iniciar_execucao(con, " ".join(ctx.comando), ctx.impressao_config, base.impressao_fontes)
        situacao = "interrompida"
        try:
            pastas_cv = []
            for janela, cenario, escopo, fim, mascara in planos:
                tab = dados.tabela(escopo, cenario.historico)
                X, y, anos = tab.X[:fim], tab.y[:fim], tab.ano[:fim]
                dobras = ajuste.pastas_mapa_inteiro(anos, y, mascara, cfg.n_pastas, cfg.semente)
                rotulo_pastas = {"cenario": cenario.nome, "amostragem": cenario.amostragem.texto(), "escopo": escopo, "janela": janela}
                pastas = tabela_pastas(rotulo_pastas, anos, y, dobras)
                for p in pastas.itertuples(index=False):
                    print(f"[pastas {cenario.nome} {escopo} <={janela}] pasta {p.pasta}: valida {p.anos_validacao} no mapa inteiro ({p.n_linhas_validacao} linhas, {p.n_positivos_validacao} positivos); treino {p.n_linhas_treino} linhas")
                pastas_cv.append(pastas)
                colunas = dados.colunas(cenario)
                for nome in nomes:
                    lista = modelos.candidatos(nome, cfg.espacos, incluir_padrao=False)
                    chave = chave_v2(dados, nome, cenario, escopo, janela, lista)
                    rotulo = f"{nome} {cenario.nome} {escopo} <={janela}"
                    if not args.refazer and banco.vencedor(con, chave) is not None:
                        print(f"PULADO {rotulo}: ja existe no banco (use --refazer)")
                        continue
                    n_jobs = modelos.REGISTRO[nome].n_jobs_busca if cenario.amostragem.amostrada else 1
                    resultado = ajuste.buscar(nome, X, y, anos, janela, lista, cfg.semente, colunas, dobras, n_jobs, cfg.metrica, rotulo, opcoes)
                    banco.gravar_chave(con, execucao_id, chave, resultado, int(mascara.sum()), int(y[mascara].sum()))
            execucao.gravar_tabela(pd.concat(pastas_cv, ignore_index=True), config.destino(cfg, "tabelas", "pastas_cv.csv"), comuns(ctx))
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
    cenario_fonte: str
    escopo_fonte: str
    reaproveitou: bool
    chave_id: int | None = None
    execucao_id: int | None = None


@dataclass
class Predicao:
    ano: int
    cenario: CenarioV2
    modelo: str
    ultimo_ano_treino: int
    p_bruta: np.ndarray
    p: np.ndarray
    escopo_modelo: np.ndarray
    betas: dict[str, float]
    consultas: dict[str, Consulta]
    estimadores: dict[str, object] = field(default_factory=dict)

    @property
    def janela(self) -> int:
        return next(iter(self.consultas.values())).janela

    @property
    def origem(self) -> str:
        return next(iter(self.consultas.values())).origem

    @property
    def reaproveitou(self) -> bool:
        return next(iter(self.consultas.values())).reaproveitou

    def correcao(self) -> str:
        if not self.cenario.amostragem.amostrada:
            return "nenhuma"
        return ";".join(f"{e}:beta={b:.6g}" for e, b in self.betas.items())


class Consultor:
    def __init__(self, ctx, dados: Dados, con):
        self.ctx, self.cfg, self.dados, self.con = ctx, ctx.cfg, dados, con
        self.cache: dict[tuple, Consulta] = {}

    def consultar(self, cenario: CenarioV2, nome: str, escopo: str, janela: int) -> Consulta:
        fonte = self.dados.v2.fonte_parametros(cenario)
        escopo_fonte = escopo if escopo in fonte.escopos else "acre"
        chave_cache = (fonte.nome, nome, escopo_fonte, janela)
        reaproveitou = not cenario.proprio
        if chave_cache in self.cache:
            achado = self.cache[chave_cache]
            return Consulta(dict(achado.parametros), achado.origem if not reaproveitou else f"{achado.origem}:{fonte.nome}", janela, fonte.nome, escopo_fonte, reaproveitou, achado.chave_id, achado.execucao_id)
        if self.ctx.args.parametros_padrao:
            consulta = Consulta(primeiro_candidato(self.cfg, nome), "padrao", janela, fonte.nome, escopo_fonte, False)
        else:
            lista = modelos.candidatos(nome, self.cfg.espacos, incluir_padrao=False)
            chave = chave_v2(self.dados, nome, fonte, escopo_fonte, janela, lista)
            achado = banco.vencedor(self.con, chave) if self.con is not None else None
            if achado is None:
                outras = banco.outras_chaves(self.con, chave) if self.con is not None else 0
                extra = f" (ha {outras} entradas com outros dados, amostragem, preditores ou grade)" if outras else ""
                raise SystemExit(
                    f"ERRO sem parametros no banco para {nome}/{fonte.nome}/{escopo_fonte}/janela<={janela}; "
                    f"rode: python {script()} validar --modelo {nome} --cenario {fonte.nome} --janela {janela}{extra}"
                )
            consulta = Consulta(achado["parametros"], "banco", janela, fonte.nome, escopo_fonte, False, achado["chave_id"], achado["execucao_id"])
        self.cache[chave_cache] = consulta
        return self.consultar(cenario, nome, escopo, janela)


def ajustar_e_prever(dados: Dados, cenario: CenarioV2, nome: str, consultas: dict[str, Consulta], ultimo_ano_treino: int, ano_alvo: int, guardar: bool) -> Predicao:
    cfg = dados.cfg
    partes, partes_corrigidas, betas, estimadores = {}, {}, {}, {}
    for escopo in cenario.escopos:
        X, y, beta = dados.treino(escopo, cenario, ultimo_ano_treino)
        if int(y.sum()) < cfg.min_positivos:
            raise SystemExit(f"ERRO {cenario.nome}/{escopo} <={ultimo_ano_treino}: {int(y.sum())} positivos; minimo {cfg.min_positivos}")
        estimador = modelos.criar(nome, consultas[escopo].parametros, cfg.semente, dados.colunas(cenario), dados.v2.opcoes_modelo)
        with warnings.catch_warnings(record=True) as avisos:
            warnings.simplefilter("always")
            estimador.fit(X, y)
            p = estimador.predict_proba(dados.matriz_alvo(escopo, cenario, ano_alvo))[:, 1]
        for texto in sorted({f"{w.category.__name__}: {w.message}" for w in avisos}):
            print(f"AVISO [{nome} {cenario.nome} {escopo} treino <={ultimo_ano_treino} -> {ano_alvo}] {texto}")
        celulas = risco.celulas_do_escopo(dados.regiao, escopo, dados.n)
        betas[escopo] = beta
        partes[escopo] = (celulas, p)
        partes_corrigidas[escopo] = (celulas, avaliacao.corrigir_prior(p, beta) if cenario.amostragem.amostrada else p)
        if guardar:
            estimadores[escopo] = estimador
        del X, y
    rotulo = f"{ano_alvo}/{cenario.nome}/{nome}"
    if cenario.regional:
        p_bruta, escopo_modelo = risco.juntar_regional(partes, dados.n, rotulo)
        p, _ = risco.juntar_regional(partes_corrigidas, dados.n, rotulo)
    else:
        p_bruta, p = partes["acre"][1], partes_corrigidas["acre"][1]
        escopo_modelo = np.full(dados.n, "acre", dtype=object)
    return Predicao(ano_alvo, cenario, nome, ultimo_ano_treino, np.asarray(p_bruta, dtype=np.float64), np.asarray(p, dtype=np.float64), escopo_modelo, betas, consultas, estimadores)


ORDEM_RECORTE = {"acre": 0, "oeste": 1, "leste": 2}
METRICAS_AVALIACAO = ["prevalencia", "roc_auc", "pr_auc", "razao_pr_auc_prevalencia", "brier", "brier_bruto", "det@1%", "det@5%", "det@10%", "det@20%"]


def identificacao(pred: Predicao) -> dict:
    return {
        "ano": pred.ano,
        "cenario": pred.cenario.nome,
        "modelo": pred.modelo,
        "amostragem": pred.cenario.amostragem.texto(),
        "historico": pred.cenario.historico,
        "ultimo_ano_treino": pred.ultimo_ano_treino,
        "janela_parametros": pred.janela,
        "origem_parametros": pred.origem,
        "reaproveitou_parametros": pred.reaproveitou,
        "correcao_prior": pred.correcao(),
    }


def recortes(regiao: np.ndarray) -> dict[str, np.ndarray]:
    return {"acre": np.ones(regiao.size, dtype=bool), "oeste": regiao == "oeste", "leste": regiao == "leste"}


def avaliar_predicao(dados: Dados, pred: Predicao) -> list[dict]:
    y = dados.base.est[f"queimou_{pred.ano}"].to_numpy().astype(np.int64)
    linhas = []
    for recorte, sel in recortes(dados.regiao).items():
        rotulo = f"{pred.ano}/{recorte}/{pred.cenario.nome}/{pred.modelo}"
        metricas = risco.avaliar_subconjunto(y[sel], pred.p[sel], rotulo)
        prevalencia = metricas["prevalencia"]
        bruto = risco.avaliar_subconjunto(y[sel], pred.p_bruta[sel], rotulo) if pred.cenario.amostragem.amostrada else metricas
        linha = {**identificacao(pred), "recorte": recorte, "n_celulas": int(sel.sum()), "n_positivos": int(y[sel].sum())}
        linha.update({m: metricas[m] for m in metricas})
        linha["brier_bruto"] = bruto["brier"]
        linha["razao_pr_auc_prevalencia"] = metricas["pr_auc"] / prevalencia if prevalencia and np.isfinite(prevalencia) else float("nan")
        linhas.append(linha)
    return linhas


def tabela_avaliacao(linhas: list[dict]) -> pd.DataFrame:
    if not linhas:
        return pd.DataFrame(columns=["ano", "recorte", "cenario", "modelo", *METRICAS_AVALIACAO])
    tabela = pd.DataFrame(linhas)
    tabela["_ordem"] = tabela["recorte"].map(ORDEM_RECORTE)
    tabela = tabela.sort_values(["ano", "_ordem", "cenario", "pr_auc"], ascending=[True, True, True, False], na_position="last", kind="mergesort")
    return tabela.drop(columns="_ordem").reset_index(drop=True)


def estatisticas_cicatrizes(dados: Dados, ident: dict, p: np.ndarray, indice: np.ndarray, cicatriz: np.ndarray) -> list[pd.DataFrame]:
    saida = []
    for escala, valores, limiares in (("probabilidade_pct", 100.0 * np.asarray(p), ()), ("indice_percentil", np.asarray(indice), dados.cfg.limiares)):
        tabela = risco.estatisticas_risco(valores, cicatriz, dados.regiao, limiares)
        tabela.insert(0, "escala", escala)
        for coluna in reversed(list(ident)):
            tabela.insert(0, coluna, ident[coluna])
        saida.append(tabela)
    return saida


def calibrar(dados: Dados, ident: dict, y: np.ndarray, p_bruta: np.ndarray, p: np.ndarray, indice: np.ndarray, amostrada: bool, betas: dict) -> tuple[list[dict], list[pd.DataFrame]]:
    linhas, tabelas = [], []
    cortes = dados.v2.mapas["cortes_percentil"]
    for recorte, sel in recortes(dados.regiao).items():
        corrigida = p[sel] if amostrada else None
        linha = {**ident, "recorte": recorte, "betas": ";".join(f"{e}:{b:.6g}" for e, b in betas.items()) if amostrada else "1"}
        linha.update(avaliacao.calibracao(y[sel], p_bruta[sel], corrigida))
        linhas.append(linha)
        if recorte == "acre":
            tabela = avaliacao.confiabilidade(y, p_bruta, p if amostrada else None, indice, cortes)
            for coluna in reversed(list(ident)):
                tabela.insert(0, coluna, ident[coluna])
            tabelas.append(tabela)
    return linhas, tabelas


def linhas_classificacao(ident: dict, y: np.ndarray, p: np.ndarray, p_bruta: np.ndarray, limiar: float | None, areas: list[float], amostra: np.ndarray | None, limiar_professor: float, negativos: int) -> list[dict]:
    linhas = []
    marcados = {f"top_{a:g}%": avaliacao.topo(p, a / 100.0) for a in areas}

    def adicionar(conjunto: str, criterio: str, valor_limiar: float | None, previsto: np.ndarray, y_conj: np.ndarray, nota: str) -> None:
        linhas.append({**ident, "conjunto": conjunto, "criterio": criterio, "limiar": valor_limiar, "nota": nota, **avaliacao.relatorio_classificacao(y_conj, previsto)})

    if limiar is not None:
        adicionar("mapa_inteiro", "limiar_sem_ano_teste", limiar, p >= limiar, y, "limiar de maior F1 da classe 1 no ano anterior, com modelo treinado ate dois anos antes")
    for criterio, marcado in marcados.items():
        corte = float(p[marcado].min())
        adicionar("mapa_inteiro", criterio, corte, marcado, y, "area de alerta fixa: celulas de maior probabilidade no ano")
    if amostra is not None:
        conjunto = f"amostra_1x{negativos}"
        y_a, p_a = y[amostra], p[amostra]
        nota = f"todos os positivos do ano + {negativos}x negativos sorteados; comparavel ao F1 do professor (0,96 classe 0; 0,63 classe 1; limiar 0,75)"
        if limiar is not None:
            adicionar(conjunto, "limiar_sem_ano_teste", limiar, p_a >= limiar, y_a, nota)
        for criterio, marcado in marcados.items():
            adicionar(conjunto, criterio, float(p[marcado].min()), marcado[amostra], y_a, nota)
        adicionar(conjunto, "limiar_professor", limiar_professor, p_bruta[amostra] >= limiar_professor, y_a, nota + "; limiar aplicado na saida bruta do modelo, como no teste do professor")
        if 0 < int(y_a.sum()) < y_a.size:
            otimo, _ = avaliacao.limiar_maior_f1(y_a, p_a)
            adicionar(conjunto, "limiar_otimo_no_teste", otimo, p_a >= otimo, y_a, nota + "; otimista: usa o proprio ano de teste, so para comparar")
    return linhas


def rotulo_amostragem(amostragem: Amostragem) -> str:
    return f"1:{amostragem.negativos_por_positivo}" if amostragem.amostrada else "todos"


def com_identificacao(tabela: pd.DataFrame, ident: dict) -> pd.DataFrame:
    for coluna in reversed(list(ident)):
        tabela.insert(0, coluna, ident[coluna])
    return tabela


class Coletor:
    def __init__(self, ctx, dados: Dados):
        self.ctx, self.cfg, self.dados, self.v2 = ctx, ctx.cfg, dados, dados.v2
        self.avaliacao: list[dict] = []
        self.rolante: list[dict] = []
        self.classificacao: list[dict] = []
        self.limiares: list[dict] = []
        self.calibracao: list[dict] = []
        self.confiabilidade: list[pd.DataFrame] = []
        self.cicatrizes: list[pd.DataFrame] = []
        self.importancias: list[pd.DataFrame] = []
        self.dependencias: list[pd.DataFrame] = []
        self.parametros: list[dict] = []
        self.predicoes: dict[tuple[int, str], dict[str, tuple[Predicao, np.ndarray]]] = {}
        self.anteriores: dict[tuple[int, str, str], np.ndarray] = {}

    def registrar_parametros(self, pred: Predicao, variante: str) -> None:
        for escopo, consulta in pred.consultas.items():
            self.parametros.append({
                "ano": pred.ano, "variante": variante, "cenario": pred.cenario.nome, "escopo": escopo, "modelo": pred.modelo,
                "ultimo_ano_treino": pred.ultimo_ano_treino, "janela_parametros": consulta.janela, "origem_parametros": consulta.origem,
                "cenario_fonte": consulta.cenario_fonte, "escopo_fonte": consulta.escopo_fonte, "reaproveitou_parametros": consulta.reaproveitou,
                "chave_id": consulta.chave_id, "execucao_id": consulta.execucao_id, "parametros": json.dumps(consulta.parametros, sort_keys=True),
                "beta": pred.betas.get(escopo, float("nan")),
            })

    def limiar(self, cenario: CenarioV2, nome: str, consultas: dict[str, Consulta], ano: int) -> float | None:
        dados = self.dados
        if not any(a <= ano - 2 for a in dados.anos_treino) or not risco.ano_avaliavel(dados.base, ano - 1):
            print(f"AVISO {ano}/{cenario.nome}/{nome}: sem ano anterior para escolher o limiar; classificacao so com areas fixas")
            return None
        anterior = ajustar_e_prever(dados, cenario, nome, consultas, ano - 2, ano - 1, False)
        y = dados.base.est[f"queimou_{ano - 1}"].to_numpy().astype(np.int64)
        limiar, f1 = avaliacao.limiar_maior_f1(y, anterior.p)
        self.limiares.append({
            "ano": ano, "cenario": cenario.nome, "modelo": nome, "ano_do_limiar": ano - 1, "ultimo_ano_treino_do_limiar": ano - 2,
            "janela_parametros": anterior.janela, "limiar": limiar, "f1_classe_1_no_ano_do_limiar": f1,
            "n_celulas_acima": int((anterior.p >= limiar).sum()), "positivos_ano_do_limiar": int(y.sum()),
        })
        print(f"[limiar] {ano} {cenario.nome} {nome}: treino <={ano - 2}, escolhido em {ano - 1}: {limiar:.6g} (F1 classe 1 = {f1:.3f})")
        return limiar

    def registrar_principal(self, pred: Predicao, limiar: float | None, avaliavel: bool) -> None:
        indice = avaliacao.indice_percentil(pred.p)
        self.predicoes.setdefault((pred.ano, pred.cenario.nome), {})[pred.modelo] = (pred, indice)
        self.registrar_parametros(pred, "principal")
        if not avaliavel:
            return
        dados, aval = self.dados, self.v2.avaliacao
        cicatriz = dados.cicatriz(pred.ano)
        y = cicatriz.astype(np.int64)
        ident = {**identificacao(pred), "origem": "v2"}
        self.avaliacao.extend(avaliar_predicao(dados, pred))
        self.cicatrizes.extend(estatisticas_cicatrizes(dados, ident, pred.p, indice, cicatriz))
        linhas, tabelas = calibrar(dados, ident, y, pred.p_bruta, pred.p, indice, pred.cenario.amostragem.amostrada, pred.betas)
        self.calibracao.extend(linhas)
        self.confiabilidade.extend(tabelas)
        if pred.cenario.nome in aval["cenarios_classificacao"]:
            negativos = aval["negativos_amostra_teste"]
            amostra = avaliacao.amostra_teste(y, negativos, self.cfg.semente, pred.ano)
            self.classificacao.extend(linhas_classificacao(ident, y, pred.p, pred.p_bruta, limiar, aval["areas_alerta_pct"], amostra, aval["limiar_professor"], negativos))

    def importancia(self, pred: Predicao) -> None:
        if "acre" not in pred.estimadores:
            print(f"AVISO importancia {pred.ano}/{pred.cenario.nome}/{pred.modelo}: so para cenarios do Acre inteiro; pulada")
            return
        dados = self.dados
        X = dados.matriz_alvo("acre", pred.cenario, pred.ano)
        y = dados.base.est[f"queimou_{pred.ano}"].to_numpy().astype(np.int64)
        repeticoes = self.v2.avaliacao["importancia"]["repeticoes"]
        tabela = avaliacao.importancia_permutacao(pred.estimadores["acre"], X, y, dados.colunas(pred.cenario), repeticoes, self.cfg.semente + pred.ano)
        self.importancias.append(com_identificacao(tabela, {"ano": pred.ano, "cenario": pred.cenario.nome, "modelo": pred.modelo}))
        veg = tabela[tabela["variavel"] == "veg"]
        if not veg.empty:
            print(f"[importancia] {pred.ano} {pred.cenario.nome} {pred.modelo}: veg queda de PR-AUC {float(veg['queda_pr_auc_media'].iloc[0]):.5f} (posto {int(veg['posto'].iloc[0])} de {len(tabela)})")

    def dependencia(self, pred: Predicao) -> None:
        if "acre" not in pred.estimadores:
            return
        dados, dep = self.dados, self.v2.avaliacao["dependencia"]
        X = dados.matriz_alvo("acre", pred.cenario, pred.ano)
        rng = np.random.default_rng([int(self.cfg.semente), int(pred.ano), 7])
        amostra = np.sort(rng.choice(X.shape[0], size=min(int(dep["amostra"]), X.shape[0]), replace=False))
        colunas = dados.colunas(pred.cenario)
        beta = pred.betas["acre"] if pred.cenario.amostragem.amostrada else None
        for variavel in dep["variaveis"]:
            tabela = avaliacao.dependencia_parcial(pred.estimadores["acre"], X[amostra], colunas.index(variavel), dep["pontos"], beta)
            self.dependencias.append(com_identificacao(tabela, {"ano": pred.ano, "cenario": pred.cenario.nome, "modelo": pred.modelo, "variavel": variavel, "n_amostra": int(amostra.size)}))

    def gravar_modelo(self, pred: Predicao) -> None:
        ctx, cfg = self.ctx, self.cfg
        for escopo, estimador in pred.estimadores.items():
            conteudo = {
                "modelo": estimador, "colunas": list(self.dados.colunas(pred.cenario)), "parametros": pred.consultas[escopo].parametros,
                "opcoes": dict(self.v2.opcoes_modelo), "cenario": pred.cenario.nome, "amostragem": pred.cenario.amostragem.texto(),
                "beta": pred.betas[escopo], "janela": pred.janela, "ultimo_ano_treino": pred.ultimo_ano_treino,
                "defasagem_clima": cfg.defasagem_principal, "interpolacao_clima": self.v2.interpolacao, "historico": dict(self.v2.historico) if pred.cenario.historico else None,
                "origem_parametros": pred.origem, "escopo": escopo, "semente": cfg.semente, "rodada": ctx.rodada, "impressao_config": ctx.impressao_config,
            }
            caminho = config.destino(cfg, "modelos", f"risco_{pred.ano}_{pred.cenario.nome}_{escopo}_{pred.modelo}.joblib")
            try:
                joblib.dump(conteudo, caminho, compress=3)
            except OSError as erro:
                raise SystemExit(f"ERRO ao gravar {caminho}: {erro}") from None


    def ler_anteriores(self, anos: list[int]) -> None:
        dados, pasta = self.dados, self.v2.anterior_saida
        if pasta is None:
            return
        for ano in anos:
            if not risco.ano_avaliavel(dados.base, ano):
                continue
            cicatriz = dados.cicatriz(ano)
            y = cicatriz.astype(np.int64)
            for cenario_antigo, rotulo in ROTULO_ANTERIOR.items():
                arquivo = pasta / "predicoes" / f"risco_celulas_{ano}_{cenario_antigo}.parquet"
                if not arquivo.is_file():
                    print(f"AVISO anterior: {arquivo} nao encontrado; 1:1 de {ano}/{cenario_antigo} fora da comparacao")
                    continue
                tabela = pd.read_parquet(arquivo, columns=["celula", "modelo", "escopo_modelo", "risco_pct"])
                for modelo, grupo in tabela.groupby("modelo", observed=True, sort=True):
                    grupo = grupo.sort_values("celula")
                    if not np.array_equal(grupo["celula"].to_numpy(), np.arange(dados.n)):
                        print(f"AVISO anterior: {arquivo.name}/{modelo} sem as {dados.n} celulas; fora da comparacao")
                        continue
                    p_s = np.clip(grupo["risco_pct"].to_numpy(dtype=np.float64) / 100.0, 0.0, 1.0)
                    escopos = grupo["escopo_modelo"].astype(str).to_numpy()
                    p = np.empty_like(p_s)
                    betas = {}
                    for escopo in sorted(set(escopos)):
                        tab = dados.tabela(escopo, False)
                        fim = tab.fim(ano - 1)
                        betas[escopo] = risco.fracao_negativos_mantidos(tab.y[:fim], dados.mascara(escopo, RAZAO_ANTERIOR)[:fim])
                        sel = escopos == escopo
                        p[sel] = avaliacao.corrigir_prior(p_s[sel], betas[escopo])
                    indice = avaliacao.indice_percentil(p_s)
                    self.anteriores[(ano, cenario_antigo, str(modelo))] = indice
                    ident = {
                        "ano": ano, "cenario": rotulo, "modelo": str(modelo), "amostragem": "razao:1", "historico": False,
                        "ultimo_ano_treino": ano - 1, "janela_parametros": None, "origem_parametros": "rodada anterior",
                        "reaproveitou_parametros": False, "correcao_prior": ";".join(f"{e}:beta={b:.6g}" for e, b in betas.items()), "origem": "anterior",
                    }
                    self.cicatrizes.extend(estatisticas_cicatrizes(dados, ident, p_s, indice, cicatriz))
                    linhas, tabelas = calibrar(dados, ident, y, p_s, p, indice, True, betas)
                    self.calibracao.extend(linhas)
                    self.confiabilidade.extend(tabelas)
            print(f"[anterior] {ano}: predicoes 1:1 lidas de {pasta / 'predicoes'}")

    def antes_depois(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        metricas = ["prevalencia", "pr_auc", "roc_auc", "brier", "det@1%", "det@5%", "det@10%", "det@20%"]
        partes = []
        pasta = self.v2.anterior_saida
        if pasta is not None and (pasta / "tabelas" / "avaliacao.csv").is_file():
            antiga = pd.read_csv(pasta / "tabelas" / "avaliacao.csv")
            antiga = antiga[antiga["variante"].isin(["atual", "principal"])].copy()
            antiga["cenario"] = antiga["cenario"].map(lambda c: c if c == "atual" else ROTULO_ANTERIOR.get(c, c))
            antiga["origem"] = "anterior"
            antiga["amostragem"] = "razao:1"
            partes.append(antiga[["ano", "recorte", "modelo", "origem", "cenario", "amostragem", *metricas]])
        else:
            print("AVISO antes_depois: avaliacao.csv da rodada anterior nao encontrado; so o v2")
        if self.avaliacao:
            nova = tabela_avaliacao(self.avaliacao)
            partes.append(nova.assign(origem="v2")[["ano", "recorte", "modelo", "origem", "cenario", "amostragem", *metricas]])
        if not partes:
            return pd.DataFrame(), pd.DataFrame()
        longa = pd.concat(partes, ignore_index=True)
        cicatrizes = pd.concat(self.cicatrizes, ignore_index=True) if self.cicatrizes else pd.DataFrame()
        if not cicatrizes.empty:
            com = cicatrizes[cicatrizes["grupo"] == "com_cicatriz"]
            for escala, prefixo in (("probabilidade_pct", "cicatriz_prob_pct"), ("indice_percentil", "cicatriz_indice")):
                sub = com[com["escala"] == escala]
                colunas = ["mediana", "p10", "p90"] + ([c for c in sub.columns if c.startswith("pct_ge_")] if escala == "indice_percentil" else [])
                sub = sub[["ano", "recorte", "cenario", "modelo", *colunas]].rename(columns={c: f"{prefixo}_{c}" for c in colunas})
                sub = sub.dropna(axis=1, how="all")
                longa = longa.merge(sub, on=["ano", "recorte", "cenario", "modelo"], how="left")
        pasta_cic = None if pasta is None else pasta / "tabelas" / "risco_nas_cicatrizes.csv"
        if pasta_cic is not None and pasta_cic.is_file():
            antiga = pd.read_csv(pasta_cic)
            antiga = antiga[antiga["variante"].isin(["atual", "principal"]) & (antiga["grupo"] == "com_cicatriz")].copy()
            antiga["cenario"] = antiga["cenario"].map(lambda c: c if c == "atual" else ROTULO_ANTERIOR.get(c, c))
            antiga = antiga[["ano", "recorte", "cenario", "modelo", "mediana", "p10", "p90"]].rename(columns={"mediana": "cicatriz_risco_1x1_mediana", "p10": "cicatriz_risco_1x1_p10", "p90": "cicatriz_risco_1x1_p90"})
            longa = longa.merge(antiga, on=["ano", "recorte", "cenario", "modelo"], how="left")
        longa["_ordem"] = longa["recorte"].map(ORDEM_RECORTE)
        longa = longa.sort_values(["ano", "_ordem", "modelo", "origem", "cenario"], kind="mergesort").drop(columns="_ordem").reset_index(drop=True)
        larga = longa.pivot_table(index=["ano", "recorte", "modelo"], columns="cenario", values="pr_auc", aggfunc="first").reset_index()
        larga.columns.name = None
        ordem = ["ano", "recorte", "modelo", "atual", *ROTULO_ANTERIOR.values(), *[c.nome for c in self.v2.cenarios]]
        larga = larga[[c for c in ordem if c in larga.columns]]
        larga["_ordem"] = larga["recorte"].map(ORDEM_RECORTE)
        larga = larga.sort_values(["ano", "_ordem", "modelo"], kind="mergesort").drop(columns="_ordem").reset_index(drop=True)
        return longa, larga

    def melhores(self) -> tuple[dict[str, str], pd.DataFrame]:
        escolhas, linhas = {}, []
        for nome in self.v2.mapas["melhor_de"]:
            rolante = [l for l in self.rolante if l["cenario"] == nome and l["recorte"] == "acre"]
            fonte = rolante if rolante else [l for l in self.avaliacao if l["cenario"] == nome and l["recorte"] == "acre"]
            criterio = "media da PR-AUC no Acre na avaliacao rolante" if rolante else "media da PR-AUC no Acre nos anos de previsao"
            if not fonte:
                print(f"AVISO melhor modelo de {nome}: sem avaliacao; mapas desse cenario pulados")
                continue
            tabela = pd.DataFrame(fonte).groupby("modelo")["pr_auc"].agg(["mean", "count"]).reset_index()
            tabela = tabela.sort_values(["mean", "modelo"], ascending=[False, True], kind="mergesort")
            melhor = str(tabela.iloc[0]["modelo"])
            escolhas[nome] = melhor
            for r in tabela.itertuples(index=False):
                linhas.append({"cenario": nome, "modelo": r.modelo, "pr_auc_media": float(r.mean), "n_anos": int(r.count), "criterio": criterio, "escolhido": r.modelo == melhor})
            print(f"[melhor] {nome}: {melhor} ({criterio} = {float(tabela.iloc[0]['mean']):.5f})")
        return escolhas, pd.DataFrame(linhas)


    def tabela_celulas(self, ano: int, cenario: str, predicoes: dict[str, tuple[Predicao, np.ndarray]]) -> pd.DataFrame:
        est, n, ctx = self.dados.base.est, self.dados.n, self.ctx
        grade = mapas.grade_saida(est)
        cicatriz = self.dados.cicatriz(ano)
        partes = []
        for modelo in sorted(predicoes):
            pred, indice = predicoes[modelo]
            partes.append(pd.DataFrame({
                "celula": np.arange(n, dtype=np.int32),
                "Y": est["Y"].to_numpy().astype(np.int16),
                "X": est["X"].to_numpy().astype(np.int16),
                "lin": grade.lin.astype(np.int16),
                "col": grade.col.astype(np.int16),
                "x_g": est["x_g"].to_numpy(dtype=np.float64),
                "y_g2": est["y_g2"].to_numpy(dtype=np.float64),
                "lon": est["lon"].to_numpy(dtype=np.float64),
                "lat": est["lat"].to_numpy(dtype=np.float64),
                "regiao": self.dados.regiao,
                "escopo_modelo": pred.escopo_modelo.astype(str),
                "cenario": cenario,
                "modelo": modelo,
                "amostragem": pred.cenario.amostragem.texto(),
                "origem_parametros": pred.origem,
                "reaproveitou_parametros": pred.reaproveitou,
                "ano": np.full(n, ano, dtype=np.int16),
                "janela_parametros": np.full(n, pred.janela, dtype=np.int16),
                "defasagem_clima": np.full(n, self.cfg.defasagem_principal, dtype=np.int8),
                "probabilidade_pct": (100 * pred.p).astype(np.float32),
                "probabilidade_bruta_pct": (100 * pred.p_bruta).astype(np.float32),
                "indice_risco": indice.astype(np.float32),
                "cicatriz": pd.array(cicatriz if cicatriz is not None else [pd.NA] * n, dtype="Int8"),
                "rodada": ctx.rodada,
                "impressao_config": ctx.impressao_config,
            }))
        tabela = pd.concat(partes, ignore_index=True)
        for coluna in ("regiao", "escopo_modelo", "cenario", "modelo", "amostragem", "origem_parametros", "rodada", "impressao_config"):
            tabela[coluna] = tabela[coluna].astype("category")
        return tabela

    def etiquetas(self, pred: Predicao) -> dict:
        return {
            "ano": pred.ano, "cenario": pred.cenario.nome, "modelo": pred.modelo, "amostragem": pred.cenario.amostragem.texto(),
            "defasagem_clima": self.cfg.defasagem_principal, "interpolacao_clima": self.v2.interpolacao, "historico": pred.cenario.historico,
            "origem_parametros": pred.origem, "janela_parametros": pred.janela, "reaproveitou_parametros": pred.reaproveitou,
            "ultimo_ano_treino": pred.ultimo_ano_treino, "correcao_prior": pred.correcao(),
            "rodada": self.ctx.rodada, "impressao_config": self.ctx.impressao_config,
        }

    def gravar_mapas(self, escolhas: dict[str, str]) -> None:
        cfg, dados = self.cfg, self.dados
        grade = mapas.grade_saida(dados.base.est)
        cortes = self.v2.mapas["cortes_percentil"]
        for (ano, cenario), predicoes in sorted(self.predicoes.items()):
            todos = cenario in self.v2.mapas["cenarios"]
            melhor = escolhas.get(cenario)
            if not todos and melhor is None:
                continue
            cicatriz = dados.cicatriz(ano)
            for modelo, (pred, indice) in sorted(predicoes.items()):
                if not todos and modelo != melhor:
                    continue
                nome = f"risco_{ano}_{cenario}_{modelo}"
                mapas.gravar_risco_v2(config.destino(cfg, "mapas", f"{nome}.tif"), grade, 100 * pred.p, indice, self.etiquetas(pred))
                figura = mapas.figura_indice(grade, indice, cicatriz, mapas.titulo_indice(ano, cenario, modelo), ano, cortes)
                mapas.gravar_png(figura, config.destino(cfg, "mapas", f"{nome}.png"))
            paineis = {modelo: indice for modelo, (_, indice) in sorted(predicoes.items())}
            figura = mapas.figura_grade_indice(grade, paineis, cicatriz, f"Índice de risco de incêndio {ano} | {cenario}", ano, cortes)
            mapas.gravar_png(figura, config.destino(cfg, "mapas", f"painel_indice_{ano}_{cenario}.png"))
        self.gravar_comparacao(grade, cortes)

    def gravar_comparacao(self, grade: mapas.GradeSaida, cortes: list) -> None:
        comparacao = self.v2.mapas["comparacao"]
        if comparacao is None:
            return
        for ano in comparacao["anos"]:
            paineis = {}
            for modelo in comparacao["modelos"]:
                anterior = self.anteriores.get((ano, comparacao["anterior"], modelo))
                if anterior is None:
                    print(f"AVISO comparacao {ano}/{modelo}: sem a predicao 1:1 anterior; painel pulado")
                else:
                    paineis[f"{modelo} | 1:1 anterior ({comparacao['anterior']})"] = anterior
                for cenario in comparacao["cenarios"]:
                    par = self.predicoes.get((ano, cenario), {}).get(modelo)
                    if par is None:
                        print(f"AVISO comparacao {ano}/{cenario}/{modelo}: sem predicao; painel pulado")
                        continue
                    paineis[f"{modelo} | {cenario} ({rotulo_amostragem(par[0].cenario.amostragem)})"] = par[1]
            if not paineis:
                continue
            rotulos = [rotulo_amostragem(self.v2.cenario(c).amostragem) for c in comparacao["cenarios"]]
            titulo = f"Índice de risco {ano}: 1:1 anterior × " + " × ".join(rotulos)
            figura = mapas.figura_grade_indice(grade, paineis, self.dados.cicatriz(ano), titulo, ano, cortes, n_col=1 + len(comparacao["cenarios"]))
            mapas.gravar_png(figura, config.destino(self.cfg, "mapas", f"comparacao_{ano}.png"))

    def gravar_figuras(self) -> None:
        cfg = self.cfg
        if self.dependencias:
            tabela = pd.concat(self.dependencias, ignore_index=True)
            for (ano, variavel), grupo in tabela.groupby(["ano", "variavel"], sort=True):
                curvas = {f"{c} | {m}": g.sort_values("valor") for (c, m), g in grupo.groupby(["cenario", "modelo"], sort=True)}
                figura = mapas.figura_dependencia(curvas, variavel, f"Dependência parcial em {variavel} ({ano})")
                mapas.gravar_png(figura, config.destino(cfg, "figuras", f"dependencia_{ano}_{variavel}.png"))
        if self.cicatrizes:
            tabela = pd.concat(self.cicatrizes, ignore_index=True)
            for ano in sorted(set(tabela["ano"])):
                grupos = {}
                for (cenario, modelo), _ in tabela[tabela["ano"] == ano].groupby(["cenario", "modelo"], sort=True):
                    indice = self.indice_de(ano, cenario, modelo)
                    cicatriz = self.dados.cicatriz(ano)
                    if indice is not None and cicatriz is not None and (cicatriz == 1).any():
                        grupos[f"{cenario} | {modelo}"] = indice[cicatriz == 1]
                if grupos:
                    mapas.gravar_png(figura_caixas_indice(grupos, ano), config.destino(cfg, "figuras", f"caixas_indice_{ano}.png"))

    def indice_de(self, ano: int, cenario: str, modelo: str) -> np.ndarray | None:
        par = self.predicoes.get((ano, cenario), {}).get(modelo)
        if par is not None:
            return par[1]
        for antigo, rotulo in ROTULO_ANTERIOR.items():
            if rotulo == cenario:
                return self.anteriores.get((ano, antigo, modelo))
        return None


    def gravar_tabelas(self, escolhas_tabela: pd.DataFrame) -> None:
        cfg, comum = self.cfg, comuns(self.ctx)

        def gravar(tabela: pd.DataFrame, nome: str) -> None:
            execucao.gravar_tabela(tabela.reset_index(drop=True), config.destino(cfg, "tabelas", nome), comum)

        def juntar(partes: list[pd.DataFrame]) -> pd.DataFrame:
            return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()

        gravar(tabela_avaliacao(self.avaliacao), "avaliacao.csv")
        gravar(pd.DataFrame(self.classificacao), "classificacao.csv")
        gravar(pd.DataFrame(self.limiares), "limiares.csv")
        gravar(pd.DataFrame(self.calibracao), "calibracao.csv")
        gravar(juntar(self.confiabilidade), "confiabilidade.csv")
        gravar(juntar(self.cicatrizes), "risco_nas_cicatrizes.csv")
        gravar(juntar(self.importancias), "importancia_permutacao.csv")
        gravar(juntar(self.dependencias), "dependencia_parcial.csv")
        gravar(pd.DataFrame(self.parametros), "parametros_usados.csv")
        gravar(escolhas_tabela, "melhor_modelo.csv")
        longa, larga = self.antes_depois()
        gravar(longa, "antes_depois.csv")
        gravar(larga, "antes_depois_pr_auc.csv")

    def gravar_parquets(self) -> None:
        for (ano, cenario), predicoes in sorted(self.predicoes.items()):
            gravar_parquet(self.tabela_celulas(ano, cenario, predicoes), config.destino(self.cfg, "predicoes", f"risco_celulas_{ano}_{cenario}.parquet"))


def figura_caixas_indice(grupos: dict[str, np.ndarray], ano: int):
    fig, ax = plt.subplots(figsize=(max(6.0, 0.6 * len(grupos) + 2), 5.5))
    ax.boxplot(list(grupos.values()), showfliers=False)
    ax.set_xticks(range(1, len(grupos) + 1), list(grupos), rotation=70, ha="right", fontsize=7)
    ax.set_ylim(0, 100)
    for corte, estilo in ((90, ":"), (97, "--")):
        ax.axhline(corte, color="#b2182b", linestyle=estilo, linewidth=0.8)
    ax.set_ylabel(mapas.ROTULO_INDICE)
    ax.set_title(f"Índice de risco nas células com cicatriz em {ano} (cenário | modelo)")
    fig.tight_layout()
    return fig


def gravar_parquet(tabela: pd.DataFrame, caminho: Path) -> None:
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        tabela.to_parquet(temporario, index=False, compression="zstd")
        temporario.replace(caminho)
    except OSError as erro:
        raise SystemExit(f"ERRO ao gravar {caminho}: {erro}") from None


LIMPEZA_PREVER = {
    "mapas": ["*.tif", "*.png"],
    "predicoes": ["*.parquet"],
    "modelos": ["*.joblib"],
    "figuras": ["*.png"],
    "tabelas": [
        "avaliacao.csv", "avaliacao_rolante.csv", "classificacao.csv", "limiares.csv", "calibracao.csv", "confiabilidade.csv",
        "risco_nas_cicatrizes.csv", "importancia_permutacao.csv", "dependencia_parcial.csv", "parametros_usados.csv",
        "melhor_modelo.csv", "antes_depois.csv", "antes_depois_pr_auc.csv",
    ],
}


def anos_pedidos(cfg: config.Config, args) -> tuple[list[int], list[int]]:
    pedidos = getattr(args, "ano", None)
    if pedidos:
        fora = [a for a in pedidos if a not in cfg.anos_previsao and a not in cfg.anos_rolantes]
        if fora:
            raise SystemExit(f"ERRO ano {fora[0]} fora de anos_previsao e anos_rolantes")
        return [a for a in pedidos if a in cfg.anos_previsao], [a for a in pedidos if a in cfg.anos_rolantes]
    rolantes = list(cfg.anos_rolantes) if getattr(args, "rolante", False) else []
    if getattr(args, "rolante", False) and not cfg.anos_rolantes:
        print("AVISO --rolante: anos_rolantes vazio; avaliacao rolante pulada")
    return list(cfg.anos_previsao), rolantes


def conferir_anos(dados: Dados, anos: list[int]) -> None:
    dp = dados.cfg.defasagem_principal
    for ano in anos:
        if not risco.ano_previsivel(dados.base, ano, dp):
            lista = ", ".join(str(a) for a in dados.base.anos_clima)
            raise SystemExit(f"ERRO ano {ano}: sem clima completo em {ano - dp} (defasagem {dp}); anos com clima: {lista}")


def processar_principais(dados: Dados, consultor: Consultor, coletor: Coletor, anos: list[int], cenarios: list[CenarioV2], nomes: list[str]) -> None:
    cfg, v2 = dados.cfg, dados.v2
    aval = v2.avaliacao
    guardados = set(v2.mapas["cenarios"]) | set(v2.mapas["melhor_de"])
    total = len(anos) * len(cenarios) * len(nomes)
    i = 0
    for ano in anos:
        janela = risco.janela_para(ano, cfg.anos_previsao)
        avaliavel = risco.ano_avaliavel(dados.base, ano)
        if not avaliavel:
            print(f"AVISO ano {ano}: sem cicatriz ou clima do ano; avaliacao pulada, so mapas")
        for cenario in cenarios:
            for nome in nomes:
                i += 1
                consultas = {e: consultor.consultar(cenario, nome, e, janela) for e in cenario.escopos}
                importancia = avaliavel and cenario.nome == aval["importancia"]["cenario"]
                dependencia = cenario.nome == aval["dependencia"]["cenario"] and nome in aval["dependencia"]["modelos"]
                gravar = cfg.gravar_modelos and cenario.nome in guardados
                pred = ajustar_e_prever(dados, cenario, nome, consultas, ano - 1, ano, importancia or dependencia or gravar)
                print(f"[prever] {i}/{total} {ano} {cenario.nome} {nome}: treino <={ano - 1}, parametros <={janela} ({pred.origem})")
                limiar = None
                if avaliavel and cenario.nome in aval["cenarios_classificacao"]:
                    limiar = coletor.limiar(cenario, nome, consultas, ano)
                coletor.registrar_principal(pred, limiar, avaliavel)
                if importancia:
                    coletor.importancia(pred)
                if dependencia:
                    coletor.dependencia(pred)
                if gravar:
                    coletor.gravar_modelo(pred)
                pred.estimadores = {}


def processar_rolantes(dados: Dados, consultor: Consultor, coletor: Coletor, anos: list[int], cenarios: list[CenarioV2], nomes: list[str]) -> None:
    cfg = dados.cfg
    rolantes = [c for c in cenarios if c.rolante]
    total = len(anos) * len(rolantes) * len(nomes)
    i = 0
    for ano in anos:
        if not risco.ano_avaliavel(dados.base, ano):
            print(f"AVISO ano {ano}: sem cicatriz ou clima do ano; fora da avaliacao rolante")
            continue
        janela = risco.janela_para(ano, cfg.anos_previsao)
        for cenario in rolantes:
            for nome in nomes:
                i += 1
                consultas = {e: consultor.consultar(cenario, nome, e, janela) for e in cenario.escopos}
                pred = ajustar_e_prever(dados, cenario, nome, consultas, ano - 1, ano, False)
                print(f"[rolante] {i}/{total} {ano} {cenario.nome} {nome}: treino <={ano - 1}, parametros <={janela}")
                coletor.rolante.extend(avaliar_predicao(dados, pred))
                coletor.registrar_parametros(pred, "rolante")


def cmd_prever(ctx, base: fontes.Base) -> None:
    cfg, args = ctx.cfg, ctx.args
    with execucao.etapa("prever", ctx.tempos):
        principais, rolantes = anos_pedidos(cfg, args)
        nomes = modelos_pedidos(cfg, getattr(args, "modelo", None))
        cenarios = cenarios_pedidos(cfg, getattr(args, "cenario", None))
        todos_anos = principais + rolantes
        if not todos_anos:
            raise SystemExit("ERRO prever: nenhum ano pedido")
        dados = Dados(cfg, base, max(todos_anos) - 1)
        conferir_anos(dados, todos_anos)
        con = None if args.parametros_padrao else banco.conectar(cfg.banco, criar=False, esquema=banco.VERSAO_ESQUEMA_V2)
        if con is None and not args.parametros_padrao:
            raise SystemExit(f"ERRO banco {cfg.banco} sem parametros; rode: python {script()} validar")
        try:
            consultor = Consultor(ctx, dados, con)
            for ano in todos_anos:
                janela = risco.janela_para(ano, cfg.anos_previsao)
                for cenario in cenarios:
                    if ano in rolantes and ano not in principais and not cenario.rolante:
                        continue
                    for nome in nomes:
                        for escopo in cenario.escopos:
                            consultor.consultar(cenario, nome, escopo, janela)
        finally:
            if con is not None:
                con.close()
        parcial = bool(getattr(args, "ano", None) or getattr(args, "modelo", None) or getattr(args, "cenario", None))
        if parcial:
            print("AVISO saida parcial (filtros); rode sem filtros para a rodada final")
        else:
            for pasta, padroes in LIMPEZA_PREVER.items():
                config.limpar(cfg, pasta, padroes)
        coletor = Coletor(ctx, dados)
        processar_principais(dados, consultor, coletor, principais, cenarios, nomes)
    if rolantes:
        with execucao.etapa("rolante", ctx.tempos):
            processar_rolantes(dados, consultor, coletor, rolantes, cenarios, nomes)
            execucao.gravar_tabela(tabela_avaliacao(coletor.rolante), config.destino(cfg, "tabelas", "avaliacao_rolante.csv"), comuns(ctx))
    with execucao.etapa("saidas", ctx.tempos):
        coletor.ler_anteriores(principais)
        escolhas, tabela_escolhas = coletor.melhores()
        coletor.gravar_tabelas(tabela_escolhas)
        coletor.gravar_parquets()
        coletor.gravar_mapas(escolhas)
        coletor.gravar_figuras()
        mapas.gravar_indice_v2(cfg.saida, config.destino(cfg, "tabelas", "indice_rasters.csv"), comuns(ctx))
        print(f"[saidas] tabelas, mapas e predicoes em {cfg.saida}")


def fontes_extras(ctx, base: fontes.Base) -> None:
    cfg = ctx.cfg
    atributos = risco.Atributos(base, 0, cfg.v2.interpolacao)
    grade = mapas.grade_saida(base.est)
    config.limpar(cfg, "camadas", ["clima_celulas_*.tif"])
    for ano in base.anos_clima:
        variaveis = {nome: atributos.clima(ano, coluna) for coluna, nome in risco.CLIMA_DO_MODELO.items()}
        etiquetas = {"ano": ano, "interpolacao_clima": cfg.v2.interpolacao, "unidade": "ur_media: %; prec_acum: mm", "rodada": ctx.rodada, "impressao_config": ctx.impressao_config}
        mapas.gravar_clima_celulas(config.destino(cfg, "camadas", f"clima_celulas_{ano}.tif"), grade, variaveis, etiquetas)
    resumo = []
    if cfg.v2.interpolacao == "bilinear":
        resumo.append({"metodo": "bilinear", **atributos.pesos().resumo()})
    else:
        resumo.append({"metodo": "vizinho", "n_celulas": len(base.est)})
    vizinho = risco.Atributos(base, 0, "vizinho")
    for ano in base.anos_clima:
        for coluna in risco.CLIMA_DO_MODELO:
            diferenca = atributos.clima(ano, coluna) - vizinho.clima(ano, coluna)
            resumo.append({"metodo": f"diferenca_{cfg.v2.interpolacao}_menos_vizinho", "ano": ano, "variavel": coluna, "media": float(diferenca.mean()), "desvio": float(diferenca.std()), "maximo_absoluto": float(np.abs(diferenca).max())})
    execucao.gravar_tabela(pd.DataFrame(resumo), config.destino(cfg, "tabelas", "interpolacao_clima.csv"), comuns(ctx))
    print(f"[fontes] {len(base.anos_clima)} camadas de clima nas celulas ({cfg.v2.interpolacao}) em {config.pasta_destino(cfg, 'camadas')}")
