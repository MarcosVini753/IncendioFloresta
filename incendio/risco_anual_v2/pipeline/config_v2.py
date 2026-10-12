from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path

from sklearn.model_selection import ParameterGrid

from . import config, historico, interpolacao, modelos, risco

ESQUEMA = {
    "versao": None,
    "centroides": None,
    "fontes": {"cicatriz", "precipitacao", "umidade", "conferir"},
    "divisao": {"tipo", "valor_m"},
    "semente": None,
    "cv": {"n_pastas", "agrupamento", "lado_bloco_m", "metrica"},
    "modelos": None,
    "espacos": None,
    "preditores": None,
    "clima": {"defasagem_principal", "interpolacao"},
    "modelagem": {"veg_categorica", "peso_classe", "dispositivo_xgboost"},
    "historico": {"teto_anos", "tau_anos"},
    "anos_previsao": None,
    "anos_rolantes": None,
    "cenarios": None,
    "definicao_cenarios": None,
    "avaliacao": {"areas_alerta_pct", "negativos_amostra_teste", "limiar_professor", "cenarios_classificacao", "importancia", "dependencia"},
    "mapas": {"cenarios", "melhor_de", "cortes_percentil", "comparacao"},
    "anterior": {"saida"},
    "min_positivos": None,
    "limiares": None,
    "gravar_modelos": None,
    "saida": None,
    "banco": None,
}
CHAVES_CENARIO = {"escopos", "amostragem", "historico", "parametros", "rolante"}
CHAVES_AMOSTRAGEM = {"tipo", "negativos_por_positivo"}
CHAVES_IMPORTANCIA = {"cenario", "repeticoes"}
CHAVES_DEPENDENCIA = {"cenario", "modelos", "variaveis", "pontos", "amostra"}
CHAVES_COMPARACAO = {"modelos", "anos", "cenarios", "anterior"}
ESCOPOS_VALIDOS = (["acre"], ["oeste", "leste"])
NOMES_RESERVADOS = ("atual", "unico", "regional", "proprios")
NOME_CENARIO = re.compile(r"^[a-z][a-z0-9_]*$")
CORTES_PADRAO = [0, 50, 70, 80, 90, 95, 97, 99, 100]

PADROES = {
    "versao": 2,
    "centroides": config.PADROES["centroides"],
    "fontes": copy.deepcopy(config.PADROES["fontes"]),
    "divisao": dict(config.PADROES["divisao"]),
    "semente": 42,
    "cv": {"n_pastas": 10, "agrupamento": "ano", "lado_bloco_m": 25000, "metrica": "pr_auc"},
    "modelos": ["RandomForest", "GradBoost", "XGBoost", "RegLogistica"],
    "espacos": {},
    "preditores": list(config.PADROES["preditores"]),
    "clima": {"defasagem_principal": 1, "interpolacao": "bilinear"},
    "modelagem": {"veg_categorica": True, "peso_classe": "nenhum", "dispositivo_xgboost": "cpu"},
    "historico": {"teto_anos": 10, "tau_anos": 3.0},
    "anos_previsao": [2016, 2025],
    "avaliacao": {"areas_alerta_pct": [1, 3, 5, 10], "negativos_amostra_teste": 19, "limiar_professor": 0.75},
    "mapas": {"melhor_de": [], "cortes_percentil": list(CORTES_PADRAO)},
    "min_positivos": 30,
    "limiares": [90, 95, 97],
    "gravar_modelos": True,
    "saida": "resultados/risco_v2",
    "banco": "resultados/risco_v2/parametros_otimos.sqlite",
}


@dataclass(frozen=True)
class Amostragem:
    tipo: str
    negativos_por_positivo: int | None

    def texto(self) -> str:
        return "todos" if self.tipo == "todos" else f"razao:{self.negativos_por_positivo}"

    @property
    def amostrada(self) -> bool:
        return self.tipo != "todos"


@dataclass(frozen=True)
class CenarioV2:
    nome: str
    escopos: tuple[str, ...]
    amostragem: Amostragem
    historico: bool
    parametros: str
    rolante: bool

    @property
    def proprio(self) -> bool:
        return self.parametros == "proprios"

    @property
    def regional(self) -> bool:
        return self.escopos != ("acre",)


@dataclass(frozen=True)
class ConfigV2:
    cenarios: tuple[CenarioV2, ...]
    interpolacao: str
    opcoes_modelo: dict
    historico: dict
    avaliacao: dict
    mapas: dict
    anterior_saida: Path | None

    def cenario(self, nome: str) -> CenarioV2:
        for c in self.cenarios:
            if c.nome == nome:
                return c
        raise SystemExit(f"ERRO cenario {nome!r} nao configurado; validos: {', '.join(c.nome for c in self.cenarios)}")

    def colunas(self, cenario: CenarioV2, preditores: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(preditores) + (tuple(historico.COLUNAS) if cenario.historico else ())

    def fonte_parametros(self, cenario: CenarioV2) -> CenarioV2:
        return cenario if cenario.proprio else self.cenario(cenario.parametros)


def _mesclar(bruto: dict) -> dict:
    dados = {}
    for chave, sub in ESQUEMA.items():
        if chave not in bruto:
            if chave in PADROES:
                dados[chave] = copy.deepcopy(PADROES[chave])
            continue
        valor = copy.deepcopy(bruto[chave])
        if sub is not None and isinstance(valor, dict):
            base = copy.deepcopy(PADROES.get(chave, {}))
            base.update(valor)
            valor = base
        dados[chave] = valor
    return dados


def _desconhecidas(bruto: dict, v: config._Validador) -> None:
    for chave, valor in bruto.items():
        if chave not in ESQUEMA:
            raise v.erro(f"chave desconhecida '{chave}'")
        sub = ESQUEMA[chave]
        if sub is not None and isinstance(valor, dict):
            for interna in valor:
                if interna not in sub:
                    raise v.erro(f"chave desconhecida '{chave}.{interna}'")
    for chave, sub in ESQUEMA.items():
        if (sub is not None or chave in ("espacos", "definicao_cenarios")) and chave in bruto:
            v.regra(chave, isinstance(bruto[chave], dict), "um objeto JSON", bruto[chave])


def _objeto(v: config._Validador, chave: str, valor, permitidas: set) -> dict:
    v.regra(chave, isinstance(valor, dict), "um objeto JSON", valor)
    for interna in valor:
        if interna not in permitidas:
            raise v.erro(f"chave desconhecida '{chave}.{interna}'")
    return valor


def _crescente(valores, minimo: float, maximo: float, inclusivo: bool = False) -> bool:
    if not config._lista(valores, config._numero, 1):
        return False
    if inclusivo:
        dentro = all(minimo <= x <= maximo for x in valores)
    else:
        dentro = all(minimo < x < maximo for x in valores)
    return dentro and all(a < b for a, b in zip(valores, valores[1:]))


def _basicos(d: dict, v: config._Validador) -> tuple[list[str], dict]:
    v.regra("versao", config._inteiro(d["versao"]) and d["versao"] == 2, "inteiro igual a 2", d["versao"])
    v.regra("centroides", config._texto(d["centroides"]) and d["centroides"] != "", "um caminho de arquivo", d["centroides"])
    fontes = d["fontes"]
    for papel in ("cicatriz", "precipitacao", "umidade"):
        v.regra(f"fontes.{papel}", config._lista(fontes[papel], config._texto, 1), "lista de caminhos com pelo menos 1 item", fontes[papel])
    v.regra("fontes.conferir", config._lista(fontes["conferir"], config._texto), "lista de caminhos", fontes["conferir"])
    divisao = d["divisao"]
    if divisao["tipo"] != "corte_x_g":
        raise v.erro(f"divisao.tipo deve ser 'corte_x_g'; recebido {config._mostrar(divisao['tipo'])}")
    v.regra("divisao.valor_m", config._numero(divisao["valor_m"]), "numero", divisao["valor_m"])
    semente = d["semente"]
    v.regra("semente", config._inteiro(semente) and 0 <= semente <= config.SEMENTE_MAXIMA, f"inteiro entre 0 e {config.SEMENTE_MAXIMA}", semente)
    cv = d["cv"]
    v.regra("cv.n_pastas", config._inteiro(cv["n_pastas"]) and cv["n_pastas"] >= 2, "inteiro >= 2", cv["n_pastas"])
    v.regra("cv.agrupamento", cv["agrupamento"] == "ano", "'ano' no v2 (as pastas sao avaliadas no mapa inteiro dos anos deixados de fora)", cv["agrupamento"])
    v.regra("cv.lado_bloco_m", config._numero(cv["lado_bloco_m"]) and cv["lado_bloco_m"] > 0, "numero > 0", cv["lado_bloco_m"])
    v.regra("cv.metrica", config._texto(cv["metrica"]) and cv["metrica"] in config.METRICAS, "'pr_auc' ou 'roc_auc'", cv["metrica"])
    v.regra("modelos", config._lista(d["modelos"], config._texto, 1), "lista de nomes de modelo com pelo menos 1 item", d["modelos"])
    nomes = [v.modelo(n, "modelos") for n in d["modelos"]]
    v.sem_repeticao("modelos", nomes)
    if "FuzzyKNN" in nomes:
        raise v.erro("chave 'modelos': FuzzyKNN fica fora do v2 (nao roda com o conjunto todo; pedido do professor: por ultimo)")
    espacos = {}
    for nome, lista in d["espacos"].items():
        chave = f"espacos.{nome}"
        canonico = v.modelo(nome, chave)
        if canonico in espacos:
            raise v.erro(f"chave 'espacos' tem o modelo {canonico} repetido")
        v.regra(chave, isinstance(lista, list) and len(lista) >= 1 and all(isinstance(g, dict) and g for g in lista), "lista nao vazia de objetos {parametro: [valores]}", lista)
        for grade in lista:
            for parametro, valores in grade.items():
                v.regra(f"{chave}.{parametro}", config._lista(valores, config._escalar, 1), "lista nao vazia de valores escalares JSON", valores)
        espacos[canonico] = copy.deepcopy(lista)
    for nome in nomes:
        if nome not in espacos:
            raise v.erro(f"chave 'espacos.{nome}' obrigatoria no v2 (a grade padrao do registro nao cabe no conjunto todo)")
    permitidos = risco.PREDITORES_PERMITIDOS
    v.regra("preditores", config._lista(d["preditores"], config._texto, 1) and all(p in permitidos for p in d["preditores"]), f"lista com pelo menos 1 de {', '.join(permitidos)}", d["preditores"])
    v.sem_repeticao("preditores", d["preditores"])
    clima = d["clima"]
    v.regra("clima.defasagem_principal", config._inteiro(clima["defasagem_principal"]) and clima["defasagem_principal"] in (0, 1), "0 ou 1", clima["defasagem_principal"])
    v.regra("clima.interpolacao", clima["interpolacao"] in interpolacao.METODOS, "'vizinho' ou 'bilinear'", clima["interpolacao"])
    modelagem = d["modelagem"]
    v.regra("modelagem.veg_categorica", isinstance(modelagem["veg_categorica"], bool), "booleano", modelagem["veg_categorica"])
    v.regra("modelagem.peso_classe", modelagem["peso_classe"] in modelos.PESOS_CLASSE, "'nenhum' ou 'balanceado'", modelagem["peso_classe"])
    v.regra("modelagem.dispositivo_xgboost", modelagem["dispositivo_xgboost"] in modelos.DISPOSITIVOS_XGBOOST, "'cpu' ou 'cuda'", modelagem["dispositivo_xgboost"])
    hist = d["historico"]
    v.regra("historico.teto_anos", config._inteiro(hist["teto_anos"]) and hist["teto_anos"] >= 1, "inteiro >= 1", hist["teto_anos"])
    v.regra("historico.tau_anos", config._numero(hist["tau_anos"]) and hist["tau_anos"] > 0, "numero > 0", hist["tau_anos"])
    ap = d["anos_previsao"]
    v.regra("anos_previsao", _crescente(ap, 1899, 2101) and all(config._inteiro(a) for a in ap), "lista crescente, sem repeticao, de anos entre 1900 e 2100", ap)
    if "anos_rolantes" not in d:
        d["anos_rolantes"] = [a for a in config.ANOS_ROLANTES_PADRAO if a not in ap and a > min(ap)]
    ar = d["anos_rolantes"]
    v.regra("anos_rolantes", config._lista(ar, config._inteiro) and all(a not in ap and a > min(ap) for a in ar), "lista de anos fora de anos_previsao e maiores que min(anos_previsao)", ar)
    v.sem_repeticao("anos_rolantes", ar)
    v.regra("min_positivos", config._inteiro(d["min_positivos"]) and d["min_positivos"] >= 1, "inteiro >= 1", d["min_positivos"])
    v.regra("limiares", _crescente(d["limiares"], 0, 100), "lista crescente de percentis entre 0 e 100 (exclusive)", d["limiares"])
    v.regra("gravar_modelos", isinstance(d["gravar_modelos"], bool), "booleano", d["gravar_modelos"])
    v.regra("saida", config._texto(d["saida"]) and d["saida"] != "", "um caminho de pasta", d["saida"])
    v.regra("banco", config._texto(d["banco"]) and d["banco"].lower().endswith(".sqlite"), "um caminho de arquivo .sqlite", d["banco"])
    return nomes, espacos


def _amostragem(valor, chave: str, v: config._Validador) -> Amostragem:
    valor = _objeto(v, chave, valor, CHAVES_AMOSTRAGEM)
    tipo = valor.get("tipo")
    if tipo == "todos":
        if "negativos_por_positivo" in valor:
            raise v.erro(f"chave '{chave}.negativos_por_positivo' so vale com tipo 'razao'")
        return Amostragem("todos", None)
    if tipo == "razao":
        n = valor.get("negativos_por_positivo")
        v.regra(f"{chave}.negativos_por_positivo", config._inteiro(n) and n >= 1, "inteiro >= 1", n)
        return Amostragem("razao", int(n))
    raise v.erro(f"chave '{chave}.tipo' deve ser 'todos' ou 'razao'; recebido {config._mostrar(tipo)}")


def _cenarios(d: dict, v: config._Validador) -> tuple[CenarioV2, ...]:
    nomes = d.get("cenarios")
    v.regra("cenarios", config._lista(nomes, config._texto, 1), "lista com pelo menos 1 nome de cenario", nomes)
    v.sem_repeticao("cenarios", nomes)
    definicoes = d.get("definicao_cenarios")
    if not isinstance(definicoes, dict) or not definicoes:
        raise v.erro("chave 'definicao_cenarios' deve ser um objeto JSON com a definicao de cada cenario")
    for nome in definicoes:
        if not NOME_CENARIO.match(nome) or nome in NOMES_RESERVADOS:
            raise v.erro(f"chave 'definicao_cenarios.{nome}': nome deve ter so letras minusculas, digitos e '_' e nao pode ser {', '.join(NOMES_RESERVADOS)}")
    for nome in nomes:
        if nome not in definicoes:
            raise v.erro(f"chave 'cenarios' cita {config._mostrar(nome)} sem definicao em 'definicao_cenarios'")
    saida = []
    for nome in nomes:
        chave = f"definicao_cenarios.{nome}"
        spec = _objeto(v, chave, definicoes[nome], CHAVES_CENARIO)
        faltando = sorted(CHAVES_CENARIO - set(spec))
        if faltando:
            raise v.erro(f"chave '{chave}' sem {', '.join(faltando)}")
        escopos = spec["escopos"]
        v.regra(f"{chave}.escopos", escopos in ESCOPOS_VALIDOS, "[\"acre\"] ou [\"oeste\", \"leste\"]", escopos)
        amostragem = _amostragem(spec["amostragem"], f"{chave}.amostragem", v)
        v.regra(f"{chave}.historico", isinstance(spec["historico"], bool), "booleano", spec["historico"])
        v.regra(f"{chave}.rolante", isinstance(spec["rolante"], bool), "booleano", spec["rolante"])
        parametros = spec["parametros"]
        v.regra(f"{chave}.parametros", config._texto(parametros), "'proprios' ou o nome de um cenario com parametros proprios", parametros)
        saida.append(CenarioV2(nome, tuple(escopos), amostragem, spec["historico"], parametros, spec["rolante"]))
    por_nome = {c.nome: c for c in saida}
    for c in saida:
        if c.proprio:
            continue
        fonte = por_nome.get(c.parametros)
        if fonte is None or not fonte.proprio:
            raise v.erro(f"chave 'definicao_cenarios.{c.nome}.parametros' deve ser 'proprios' ou um cenario de 'cenarios' com parametros proprios; recebido {config._mostrar(c.parametros)}")
        if not (set(c.escopos) <= set(fonte.escopos) or fonte.escopos == ("acre",)):
            raise v.erro(f"chave 'definicao_cenarios.{c.nome}.parametros': o cenario {fonte.nome} nao tem os escopos {', '.join(c.escopos)}")
    return tuple(saida)


def _lista_de(v: config._Validador, chave: str, valores, validos: list[str], minimo: int = 0) -> list[str]:
    v.regra(chave, config._lista(valores, config._texto, minimo) and all(x in validos for x in valores), f"lista com nomes de {', '.join(validos)}", valores)
    v.sem_repeticao(chave, valores)
    return list(valores)


def _avaliacao(d: dict, v: config._Validador, nomes_cenarios: list[str], nomes_modelos: list[str], preditores: list[str]) -> dict:
    a = d["avaliacao"]
    v.regra("avaliacao.areas_alerta_pct", _crescente(a["areas_alerta_pct"], 0, 100), "lista crescente de percentuais entre 0 e 100 (exclusive)", a["areas_alerta_pct"])
    n = a["negativos_amostra_teste"]
    v.regra("avaliacao.negativos_amostra_teste", config._inteiro(n) and n >= 1, "inteiro >= 1", n)
    limiar = a["limiar_professor"]
    v.regra("avaliacao.limiar_professor", config._numero(limiar) and 0 < limiar < 1, "numero entre 0 e 1 (exclusive)", limiar)
    classificacao = _lista_de(v, "avaliacao.cenarios_classificacao", a.get("cenarios_classificacao", nomes_cenarios), nomes_cenarios)
    padrao_imp = {"cenario": nomes_cenarios[0], "repeticoes": 3}
    imp = dict(padrao_imp, **_objeto(v, "avaliacao.importancia", a.get("importancia", {}), CHAVES_IMPORTANCIA))
    v.regra("avaliacao.importancia.cenario", imp["cenario"] in nomes_cenarios, f"um de {', '.join(nomes_cenarios)}", imp["cenario"])
    v.regra("avaliacao.importancia.repeticoes", config._inteiro(imp["repeticoes"]) and imp["repeticoes"] >= 1, "inteiro >= 1", imp["repeticoes"])
    distancias = [c for c in preditores if c in modelos.COLUNAS_DISTANCIA]
    padrao_dep = {"cenario": nomes_cenarios[0], "modelos": [m for m in nomes_modelos if m == "XGBoost"] or nomes_modelos[:1], "variaveis": distancias, "pontos": 25, "amostra": 20000}
    dep = dict(padrao_dep, **_objeto(v, "avaliacao.dependencia", a.get("dependencia", {}), CHAVES_DEPENDENCIA))
    v.regra("avaliacao.dependencia.cenario", dep["cenario"] in nomes_cenarios, f"um de {', '.join(nomes_cenarios)}", dep["cenario"])
    dep["modelos"] = _lista_de(v, "avaliacao.dependencia.modelos", dep["modelos"], nomes_modelos)
    dep["variaveis"] = _lista_de(v, "avaliacao.dependencia.variaveis", dep["variaveis"], list(preditores))
    v.regra("avaliacao.dependencia.pontos", config._inteiro(dep["pontos"]) and dep["pontos"] >= 2, "inteiro >= 2", dep["pontos"])
    v.regra("avaliacao.dependencia.amostra", config._inteiro(dep["amostra"]) and dep["amostra"] >= 100, "inteiro >= 100", dep["amostra"])
    return {
        "areas_alerta_pct": list(a["areas_alerta_pct"]),
        "negativos_amostra_teste": int(n),
        "limiar_professor": float(limiar),
        "cenarios_classificacao": classificacao,
        "importancia": imp,
        "dependencia": dep,
    }


def _mapas(d: dict, v: config._Validador, nomes_cenarios: list[str], nomes_modelos: list[str]) -> dict:
    m = d["mapas"]
    cenarios = _lista_de(v, "mapas.cenarios", m.get("cenarios", nomes_cenarios[:1]), nomes_cenarios)
    melhor = _lista_de(v, "mapas.melhor_de", m.get("melhor_de", []), nomes_cenarios)
    repetidos = sorted(set(cenarios) & set(melhor))
    if repetidos:
        raise v.erro(f"chave 'mapas.melhor_de' repete cenarios de 'mapas.cenarios': {', '.join(repetidos)}")
    cortes = m["cortes_percentil"]
    ok = _crescente(cortes, 0, 100, inclusivo=True) and len(cortes) >= 3 and cortes[0] == 0 and cortes[-1] == 100
    v.regra("mapas.cortes_percentil", ok, "lista crescente de percentis de 0 a 100, com pelo menos 3 cortes", cortes)
    comparacao = m.get("comparacao")
    if comparacao is not None:
        comparacao = _objeto(v, "mapas.comparacao", comparacao, CHAVES_COMPARACAO)
        faltando = sorted(CHAVES_COMPARACAO - set(comparacao))
        if faltando:
            raise v.erro(f"chave 'mapas.comparacao' sem {', '.join(faltando)}")
        comparacao = dict(comparacao)
        comparacao["modelos"] = _lista_de(v, "mapas.comparacao.modelos", comparacao["modelos"], nomes_modelos, 1)
        comparacao["cenarios"] = _lista_de(v, "mapas.comparacao.cenarios", comparacao["cenarios"], nomes_cenarios, 1)
        anos = comparacao["anos"]
        v.regra("mapas.comparacao.anos", config._lista(anos, config._inteiro, 1) and all(a in d["anos_previsao"] for a in anos), "lista de anos de anos_previsao", anos)
        v.regra("mapas.comparacao.anterior", comparacao["anterior"] in ("unico", "regional"), "'unico' ou 'regional'", comparacao["anterior"])
    return {"cenarios": cenarios, "melhor_de": melhor, "cortes_percentil": list(cortes), "comparacao": comparacao}


def _anterior(d: dict, v: config._Validador, raiz: Path, saida: Path) -> Path | None:
    if "anterior" not in d:
        return None
    texto = d["anterior"].get("saida")
    v.regra("anterior.saida", config._texto(texto) and texto != "", "um caminho de pasta", texto)
    caminho = Path(texto)
    anterior = (caminho if caminho.is_absolute() else raiz / caminho).resolve()
    if not anterior.is_dir():
        raise v.erro(f"chave 'anterior.saida': pasta nao encontrada: {anterior}")
    if saida == anterior or saida.is_relative_to(anterior) or anterior.is_relative_to(saida):
        raise v.erro(f"chave 'saida' nao pode coincidir, ficar dentro nem conter 'anterior.saida' ({anterior}); a rodada anterior e so leitura")
    return anterior


def carregar(caminho: Path, bruto: dict, v: config._Validador) -> config.Config:
    _desconhecidas(bruto, v)
    v.finitos(bruto, "")
    d = _mesclar(bruto)
    nomes, espacos = _basicos(d, v)
    cenarios = _cenarios(d, v)
    nomes_cenarios = [c.nome for c in cenarios]
    avaliacao = _avaliacao(d, v, nomes_cenarios, nomes, list(d["preditores"]))
    mapas = _mapas(d, v, nomes_cenarios, nomes)
    raiz = caminho.resolve().parent
    centroides, fontes, saida, banco = config._caminhos(d, v, raiz)
    if not banco.is_relative_to(saida):
        raise v.erro(f"chave 'banco' deve ficar dentro de 'saida' no v2 (banco proprio da rodada): {banco}")
    anterior = _anterior(d, v, raiz, saida)
    if mapas["comparacao"] is not None and anterior is None:
        raise v.erro("chave 'mapas.comparacao' precisa de 'anterior.saida' (predicoes 1:1 da rodada anterior)")
    preditores = tuple(d["preditores"])
    opcoes = dict(d["modelagem"])
    colunas = preditores + (tuple(historico.COLUNAS) if any(c.historico for c in cenarios) else ())
    for nome, lista in espacos.items():
        if not modelos.disponivel(nome):
            continue
        for candidato in ParameterGrid(lista):
            try:
                modelos.criar(nome, dict(candidato), d["semente"], colunas, opcoes)
            except (TypeError, ValueError) as erro:
                raise v.erro(f"chave 'espacos.{nome}': parametro invalido para {nome}: {erro}") from None
    clima = d["clima"]
    hist = {"teto_anos": int(d["historico"]["teto_anos"]), "tau_anos": float(d["historico"]["tau_anos"])}
    normalizada = {
        "versao": 2,
        "centroides": config._relativo(raiz, centroides),
        "fontes": {papel: [config._relativo(raiz, c) for c in lista] for papel, lista in fontes.items()},
        "divisao": {"tipo": d["divisao"]["tipo"], "valor_m": d["divisao"]["valor_m"]},
        "semente": d["semente"],
        "cv": dict(d["cv"]),
        "modelos": list(nomes),
        "espacos": espacos,
        "preditores": list(preditores),
        "clima": {"defasagem_principal": clima["defasagem_principal"], "interpolacao": clima["interpolacao"]},
        "modelagem": opcoes,
        "historico": hist,
        "anos_previsao": list(d["anos_previsao"]),
        "anos_rolantes": list(d["anos_rolantes"]),
        "cenarios": nomes_cenarios,
        "definicao_cenarios": {
            c.nome: {
                "escopos": list(c.escopos),
                "amostragem": c.amostragem.texto(),
                "historico": c.historico,
                "parametros": c.parametros,
                "rolante": c.rolante,
            }
            for c in cenarios
        },
        "avaliacao": avaliacao,
        "mapas": mapas,
        "anterior": None if anterior is None else config._relativo(raiz, anterior),
        "min_positivos": d["min_positivos"],
        "limiares": list(d["limiares"]),
        "gravar_modelos": d["gravar_modelos"],
        "saida": config._relativo(raiz, saida),
        "banco": config._relativo(raiz, banco),
    }
    extra = ConfigV2(cenarios, clima["interpolacao"], opcoes, hist, avaliacao, mapas, anterior)
    return config.Config(
        arquivo=caminho.resolve(),
        raiz=raiz,
        centroides=centroides,
        cicatriz=fontes["cicatriz"],
        precipitacao=fontes["precipitacao"],
        umidade=fontes["umidade"],
        conferir=fontes["conferir"],
        divisao=dict(normalizada["divisao"]),
        semente=d["semente"],
        n_pastas=d["cv"]["n_pastas"],
        agrupamento=d["cv"]["agrupamento"],
        lado_bloco_m=float(d["cv"]["lado_bloco_m"]),
        metrica=d["cv"]["metrica"],
        modelos=tuple(nomes),
        espacos=copy.deepcopy(espacos),
        preditores=preditores,
        defasagem_principal=clima["defasagem_principal"],
        defasagens_comparacao=(),
        ajustar_comparacao=False,
        anos_previsao=tuple(d["anos_previsao"]),
        anos_rolantes=tuple(d["anos_rolantes"]),
        cenarios=tuple(nomes_cenarios),
        mapas_cenarios=tuple(mapas["cenarios"]),
        min_positivos=d["min_positivos"],
        limiares=tuple(float(x) for x in d["limiares"]),
        gravar_modelos=d["gravar_modelos"],
        saida=saida,
        banco=banco,
        normalizada=normalizada,
        versao=2,
        v2=extra,
    )
