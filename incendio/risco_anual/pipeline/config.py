from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sklearn.model_selection import ParameterGrid

from . import modelos, risco

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
    "clima": {"defasagem_principal", "defasagens_comparacao", "ajustar_comparacao"},
    "anos_previsao": None,
    "anos_rolantes": None,
    "cenarios": None,
    "mapas": {"cenarios"},
    "min_positivos": None,
    "limiares": None,
    "gravar_modelos": None,
    "saida": None,
    "banco": None,
}

PADROES = {
    "versao": 1,
    "centroides": "centroides2003a2013.xlsx",
    "fontes": {
        "cicatriz": ["novos/Cicatrizes_Acre_2006_2025.tif", "Cicatrizes_Incendio_Acre_2006_2016.tif"],
        "precipitacao": ["Precipitacao_13h_Diaria_Acre_2006_2016.tif", "novos/Precipitacao_13h_Diaria_Acre_2016_2026.tif"],
        "umidade": ["Umidade_Relativa_Diaria_Acre_2006_2016.tif", "novos/Umidade_Relativa_Diaria_Acre_2016_2026.tif"],
        "conferir": ["novos/Cicatrizes_Incendio_Acre_2006_2025_MODIS.tif"],
    },
    "divisao": {"tipo": "corte_x_g", "valor_m": 337100},
    "semente": 42,
    "cv": {"n_pastas": 10, "agrupamento": "ano", "lado_bloco_m": 25000, "metrica": "pr_auc"},
    "modelos": ["FuzzyKNN", "RandomForest", "GradBoost", "XGBoost", "RegLogistica"],
    "espacos": {},
    "preditores": ["veg", "dist_estrada", "dist_agua", "altitude", "ur_media_ano", "prec_acum_ano"],
    "clima": {"defasagem_principal": 1, "ajustar_comparacao": False},
    "anos_previsao": [2016, 2025],
    "cenarios": ["atual", "unico", "regional"],
    "mapas": {},
    "min_positivos": 30,
    "limiares": [50, 80, 90],
    "gravar_modelos": True,
    "saida": "resultados/risco",
    "banco": "resultados/parametros_otimos.sqlite",
}

SEMENTE_MAXIMA = 4294967295
AGRUPAMENTOS = ("ano", "bloco_espacial", "aleatorio")
METRICAS = ("pr_auc", "roc_auc")
CENARIOS = ("atual", "unico", "regional")
CENARIOS_MAPA = ("unico", "regional")
ANOS_ROLANTES_PADRAO = tuple(range(2017, 2025))


@dataclass(frozen=True)
class Config:
    arquivo: Path
    raiz: Path
    centroides: Path
    cicatriz: tuple[Path, ...]
    precipitacao: tuple[Path, ...]
    umidade: tuple[Path, ...]
    conferir: tuple[Path, ...]
    divisao: dict
    semente: int
    n_pastas: int
    agrupamento: str
    lado_bloco_m: float
    metrica: str
    modelos: tuple[str, ...]
    espacos: dict
    preditores: tuple[str, ...]
    defasagem_principal: int
    defasagens_comparacao: tuple[int, ...]
    ajustar_comparacao: bool
    anos_previsao: tuple[int, ...]
    anos_rolantes: tuple[int, ...]
    cenarios: tuple[str, ...]
    mapas_cenarios: tuple[str, ...]
    min_positivos: int
    limiares: tuple[float, ...]
    gravar_modelos: bool
    saida: Path
    banco: Path
    normalizada: dict


def _mostrar(valor) -> str:
    if isinstance(valor, float) and not math.isfinite(valor):
        return repr(valor)
    try:
        return json.dumps(valor, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(valor)


def _inteiro(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _texto(valor) -> bool:
    return isinstance(valor, str)


def _lista(valor, teste, minimo: int = 0) -> bool:
    return isinstance(valor, list) and len(valor) >= minimo and all(teste(x) for x in valor)


def _escalar(valor) -> bool:
    return valor is None or isinstance(valor, (bool, int, float, str))


class _Validador:
    def __init__(self, arquivo: str):
        self.arquivo = arquivo

    def erro(self, mensagem: str) -> SystemExit:
        return SystemExit(f"ERRO {self.arquivo}: {mensagem}")

    def regra(self, chave: str, ok: bool, descricao: str, valor) -> None:
        if not ok:
            raise self.erro(f"chave '{chave}' deve ser {descricao}; recebido {_mostrar(valor)}")

    def sem_repeticao(self, chave: str, valores: list) -> None:
        vistos = []
        for v in valores:
            if v in vistos:
                raise self.erro(f"chave '{chave}' tem valor repetido {_mostrar(v)}")
            vistos.append(v)

    def desconhecidas(self, bruto: dict) -> None:
        for chave, valor in bruto.items():
            if chave not in ESQUEMA:
                raise self.erro(f"chave desconhecida '{chave}'")
            sub = ESQUEMA[chave]
            if sub is not None and isinstance(valor, dict):
                for interna in valor:
                    if interna not in sub:
                        raise self.erro(f"chave desconhecida '{chave}.{interna}'")

    def finitos(self, valor, caminho: str) -> None:
        if isinstance(valor, float) and not math.isfinite(valor):
            raise self.erro(f"chave '{caminho}' deve ser um numero finito; recebido {_mostrar(valor)}")
        if isinstance(valor, dict):
            for chave, interno in valor.items():
                self.finitos(interno, f"{caminho}.{chave}" if caminho else str(chave))
        elif isinstance(valor, list):
            for i, interno in enumerate(valor):
                self.finitos(interno, f"{caminho}[{i}]")

    def modelo(self, nome, chave: str) -> str:
        for valido in modelos.REGISTRO:
            if isinstance(nome, str) and valido.lower() == nome.lower():
                return valido
        raise self.erro(f"chave '{chave}' tem modelo {_mostrar(nome)} desconhecido; validos: {', '.join(modelos.REGISTRO)}")


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


def _ler(caminho: Path, v: _Validador) -> dict:
    try:
        texto = caminho.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise SystemExit(f"ERRO arquivo de configuracao nao encontrado: {caminho}") from None
    except OSError as erro:
        raise SystemExit(f"ERRO ao ler {caminho}: {erro}") from None

    def recusar(nome: str):
        raise v.erro(f"{nome} nao e um numero JSON valido")

    try:
        bruto = json.loads(texto, parse_constant=recusar)
    except json.JSONDecodeError as erro:
        raise v.erro(f"JSON invalido na linha {erro.lineno}, coluna {erro.colno}: {erro.msg}") from None
    if not isinstance(bruto, dict):
        raise v.erro("o conteudo deve ser um objeto JSON")
    return bruto


def _validar_valores(d: dict, v: _Validador) -> tuple[list[str], dict]:
    v.regra("versao", _inteiro(d["versao"]) and d["versao"] == 1, "inteiro igual a 1", d["versao"])
    v.regra("centroides", _texto(d["centroides"]) and d["centroides"] != "", "um caminho de arquivo", d["centroides"])
    fontes = d["fontes"]
    for papel in ("cicatriz", "precipitacao", "umidade"):
        v.regra(f"fontes.{papel}", _lista(fontes[papel], _texto, 1), "lista de caminhos com pelo menos 1 item", fontes[papel])
    v.regra("fontes.conferir", _lista(fontes["conferir"], _texto), "lista de caminhos", fontes["conferir"])
    divisao = d["divisao"]
    if divisao["tipo"] == "ibge":
        raise v.erro("divisao pela malha do IBGE esta fora do escopo (D3)")
    if divisao["tipo"] != "corte_x_g":
        raise v.erro(f"divisao.tipo deve ser 'corte_x_g'; recebido {_mostrar(divisao['tipo'])}")
    v.regra("divisao.valor_m", _numero(divisao["valor_m"]), "numero", divisao["valor_m"])
    semente = d["semente"]
    v.regra("semente", _inteiro(semente) and 0 <= semente <= SEMENTE_MAXIMA, f"inteiro entre 0 e {SEMENTE_MAXIMA}", semente)
    cv = d["cv"]
    v.regra("cv.n_pastas", _inteiro(cv["n_pastas"]) and cv["n_pastas"] >= 2, "inteiro >= 2", cv["n_pastas"])
    v.regra("cv.agrupamento", _texto(cv["agrupamento"]) and cv["agrupamento"] in AGRUPAMENTOS, "'ano', 'bloco_espacial' ou 'aleatorio'", cv["agrupamento"])
    v.regra("cv.lado_bloco_m", _numero(cv["lado_bloco_m"]) and cv["lado_bloco_m"] > 0, "numero > 0", cv["lado_bloco_m"])
    v.regra("cv.metrica", _texto(cv["metrica"]) and cv["metrica"] in METRICAS, "'pr_auc' ou 'roc_auc'", cv["metrica"])
    v.regra("modelos", _lista(d["modelos"], _texto, 1), "lista de nomes de modelo com pelo menos 1 item", d["modelos"])
    nomes = [v.modelo(n, "modelos") for n in d["modelos"]]
    v.sem_repeticao("modelos", nomes)
    espacos = {}
    for nome, lista in d["espacos"].items():
        chave = f"espacos.{nome}"
        canonico = v.modelo(nome, chave)
        if canonico in espacos:
            raise v.erro(f"chave 'espacos' tem o modelo {canonico} repetido")
        v.regra(chave, isinstance(lista, list) and len(lista) >= 1 and all(isinstance(g, dict) and g for g in lista), "lista nao vazia de objetos {parametro: [valores]}", lista)
        for grade in lista:
            for parametro, valores in grade.items():
                v.regra(f"{chave}.{parametro}", _lista(valores, _escalar, 1), "lista nao vazia de valores escalares JSON", valores)
        espacos[canonico] = copy.deepcopy(lista)
    permitidos = risco.PREDITORES_PERMITIDOS
    v.regra("preditores", _lista(d["preditores"], _texto, 1) and all(p in permitidos for p in d["preditores"]), f"lista com pelo menos 1 de {', '.join(permitidos)}", d["preditores"])
    v.sem_repeticao("preditores", d["preditores"])
    clima = d["clima"]
    dp = clima["defasagem_principal"]
    v.regra("clima.defasagem_principal", _inteiro(dp) and dp in (0, 1), "0 ou 1", dp)
    v.regra("clima.ajustar_comparacao", isinstance(clima["ajustar_comparacao"], bool), "booleano", clima["ajustar_comparacao"])
    if "defasagens_comparacao" in clima:
        v.regra("clima.defasagens_comparacao", _lista(clima["defasagens_comparacao"], _inteiro), "lista de inteiros", clima["defasagens_comparacao"])
    ap = d["anos_previsao"]
    crescente = _lista(ap, _inteiro, 1) and all(1900 <= a <= 2100 for a in ap) and all(a < b for a, b in zip(ap, ap[1:]))
    v.regra("anos_previsao", crescente, "lista crescente, sem repeticao, de anos entre 1900 e 2100", ap)
    if "anos_rolantes" in d:
        v.regra("anos_rolantes", _lista(d["anos_rolantes"], _inteiro), "lista de anos inteiros", d["anos_rolantes"])
    v.regra("cenarios", _lista(d["cenarios"], _texto, 1) and all(c in CENARIOS for c in d["cenarios"]), "lista com pelo menos 1 de 'atual', 'unico', 'regional'", d["cenarios"])
    v.sem_repeticao("cenarios", d["cenarios"])
    if "cenarios" in d["mapas"]:
        v.regra("mapas.cenarios", _lista(d["mapas"]["cenarios"], _texto), "lista de cenarios", d["mapas"]["cenarios"])
    v.regra("min_positivos", _inteiro(d["min_positivos"]) and d["min_positivos"] >= 1, "inteiro >= 1", d["min_positivos"])
    lim = d["limiares"]
    ok = _lista(lim, _numero) and all(0 < x < 100 for x in lim) and all(a < b for a, b in zip(lim, lim[1:]))
    v.regra("limiares", ok, "lista crescente de numeros entre 0 e 100 (exclusive)", lim)
    v.regra("gravar_modelos", isinstance(d["gravar_modelos"], bool), "booleano", d["gravar_modelos"])
    v.regra("saida", _texto(d["saida"]) and d["saida"] != "", "um caminho de pasta", d["saida"])
    v.regra("banco", _texto(d["banco"]) and d["banco"].lower().endswith(".sqlite"), "um caminho de arquivo .sqlite", d["banco"])
    return nomes, espacos


def _derivar(d: dict, v: _Validador) -> None:
    clima = d["clima"]
    dp = clima["defasagem_principal"]
    if "defasagens_comparacao" not in clima:
        clima["defasagens_comparacao"] = [1 - dp]
    dc = clima["defasagens_comparacao"]
    v.regra("clima.defasagens_comparacao", all(x in (0, 1) and x != dp for x in dc), "lista de defasagens 0 ou 1 diferentes da principal", dc)
    v.sem_repeticao("clima.defasagens_comparacao", dc)
    ap = d["anos_previsao"]
    if "anos_rolantes" not in d:
        d["anos_rolantes"] = [a for a in ANOS_ROLANTES_PADRAO if a not in ap and a > min(ap)]
    ar = d["anos_rolantes"]
    v.regra("anos_rolantes", all(a not in ap and a > min(ap) for a in ar), "lista de anos fora de anos_previsao e maiores que min(anos_previsao)", ar)
    v.sem_repeticao("anos_rolantes", ar)
    mapas = d["mapas"]
    if "cenarios" not in mapas:
        mapas["cenarios"] = [c for c in d["cenarios"] if c in CENARIOS_MAPA]
    mc = mapas["cenarios"]
    v.regra("mapas.cenarios", all(c in d["cenarios"] and c in CENARIOS_MAPA for c in mc), "subconjunto de cenarios com 'unico' ou 'regional'", mc)
    v.sem_repeticao("mapas.cenarios", mc)


def _relativo(raiz: Path, caminho: Path) -> str:
    try:
        return Path(caminho).resolve().relative_to(raiz).as_posix()
    except ValueError:
        return Path(caminho).resolve().as_posix()


def _caminhos(d: dict, v: _Validador, raiz: Path) -> tuple[Path, dict, Path, Path]:
    def resolver(texto: str) -> Path:
        p = Path(texto)
        return (p if p.is_absolute() else raiz / p).resolve()

    centroides = resolver(d["centroides"])
    if not centroides.is_file():
        raise v.erro(f"chave 'centroides': arquivo nao encontrado: {centroides}")
    if centroides.suffix.lower() != ".xlsx":
        raise v.erro(f"chave 'centroides': extensao deve ser .xlsx: {centroides}")
    fontes = {}
    for papel in ("cicatriz", "precipitacao", "umidade", "conferir"):
        lista = [resolver(t) for t in d["fontes"][papel]]
        for caminho in lista:
            if not caminho.is_file():
                raise v.erro(f"chave 'fontes.{papel}': arquivo nao encontrado: {caminho}")
            if papel != "conferir" and caminho.suffix.lower() not in (".tif", ".tiff"):
                raise v.erro(f"chave 'fontes.{papel}': extensao deve ser .tif ou .tiff: {caminho}")
        v.sem_repeticao(f"fontes.{papel}", [str(c) for c in lista])
        fontes[papel] = tuple(lista)
    saida = resolver(d["saida"])
    banco = resolver(d["banco"])
    if saida.is_file():
        raise v.erro(f"chave 'saida' aponta para um arquivo: {saida}")
    entradas = [centroides] + [c for papel in fontes for c in fontes[papel]]
    for entrada in entradas:
        if entrada == banco:
            raise v.erro(f"o banco coincide com um arquivo de entrada: {entrada}")
        if entrada.parent == saida:
            raise v.erro(f"saida e a pasta do arquivo de entrada {entrada}")
        if entrada.is_relative_to(saida):
            raise v.erro(f"arquivo de entrada dentro de saida: {entrada}")
        if banco.parent == entrada.parent:
            raise v.erro(f"o banco ficaria na pasta do arquivo de entrada {entrada}")
    return centroides, fontes, saida, banco


def carregar(caminho: Path) -> Config:
    caminho = Path(caminho)
    v = _Validador(caminho.name)
    bruto = _ler(caminho, v)
    v.desconhecidas(bruto)
    v.finitos(bruto, "")
    for chave, sub in ESQUEMA.items():
        if (sub is not None or chave == "espacos") and chave in bruto:
            v.regra(chave, isinstance(bruto[chave], dict), "um objeto JSON", bruto[chave])
    d = _mesclar(bruto)
    nomes, espacos = _validar_valores(d, v)
    _derivar(d, v)
    raiz = caminho.resolve().parent
    centroides, fontes, saida, banco = _caminhos(d, v, raiz)
    preditores = tuple(d["preditores"])
    for nome, lista in espacos.items():
        if not modelos.disponivel(nome):
            continue
        for candidato in ParameterGrid(lista):
            try:
                modelos.criar(nome, dict(candidato), d["semente"], preditores)
            except (TypeError, ValueError) as erro:
                raise v.erro(f"chave 'espacos.{nome}': parametro invalido para {nome}: {erro}") from None
    clima = d["clima"]
    normalizada = {
        "versao": d["versao"],
        "centroides": _relativo(raiz, centroides),
        "fontes": {papel: [_relativo(raiz, c) for c in lista] for papel, lista in fontes.items()},
        "divisao": {"tipo": d["divisao"]["tipo"], "valor_m": d["divisao"]["valor_m"]},
        "semente": d["semente"],
        "cv": dict(d["cv"]),
        "modelos": list(nomes),
        "espacos": espacos,
        "preditores": list(preditores),
        "clima": {
            "defasagem_principal": clima["defasagem_principal"],
            "defasagens_comparacao": list(clima["defasagens_comparacao"]),
            "ajustar_comparacao": clima["ajustar_comparacao"],
        },
        "anos_previsao": list(d["anos_previsao"]),
        "anos_rolantes": list(d["anos_rolantes"]),
        "cenarios": list(d["cenarios"]),
        "mapas": {"cenarios": list(d["mapas"]["cenarios"])},
        "min_positivos": d["min_positivos"],
        "limiares": list(d["limiares"]),
        "gravar_modelos": d["gravar_modelos"],
        "saida": _relativo(raiz, saida),
        "banco": _relativo(raiz, banco),
    }
    return Config(
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
        defasagens_comparacao=tuple(clima["defasagens_comparacao"]),
        ajustar_comparacao=clima["ajustar_comparacao"],
        anos_previsao=tuple(d["anos_previsao"]),
        anos_rolantes=tuple(d["anos_rolantes"]),
        cenarios=tuple(d["cenarios"]),
        mapas_cenarios=tuple(d["mapas"]["cenarios"]),
        min_positivos=d["min_positivos"],
        limiares=tuple(float(x) for x in d["limiares"]),
        gravar_modelos=d["gravar_modelos"],
        saida=saida,
        banco=banco,
        normalizada=normalizada,
    )


def impressao(cfg: Config) -> str:
    texto = json.dumps(cfg.normalizada, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def relativo(cfg: Config, caminho: Path) -> str:
    return _relativo(cfg.raiz, caminho)


def fonte_cicatriz(cfg: Config) -> str:
    return "+".join(relativo(cfg, c) for c in cfg.cicatriz)


def texto_agrupamento(cfg: Config) -> str:
    if cfg.agrupamento == "bloco_espacial":
        return f"bloco_espacial:{float(cfg.lado_bloco_m)!r}"
    return cfg.agrupamento


def _dentro_de_saida(cfg: Config, partes: tuple[str, ...]) -> Path:
    caminho = cfg.saida.joinpath(*partes)
    if not caminho.resolve().is_relative_to(cfg.saida.resolve()):
        raise SystemExit(f"ERRO caminho fora de saida: {caminho}")
    return caminho


def destino(cfg: Config, *partes: str) -> Path:
    caminho = _dentro_de_saida(cfg, partes)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho


def pasta_destino(cfg: Config, *partes: str) -> Path:
    caminho = _dentro_de_saida(cfg, partes)
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def limpar(cfg: Config, pasta: str, padroes: Sequence[str]) -> list[Path]:
    alvo = pasta_destino(cfg, pasta)
    base = alvo.resolve()
    apagados = []
    for padrao in padroes:
        for caminho in sorted(alvo.glob(padrao)):
            if not caminho.is_file() or caminho.resolve().parent != base or caminho in apagados:
                continue
            try:
                caminho.unlink()
            except OSError as erro:
                raise SystemExit(f"ERRO nao foi possivel apagar {caminho}: {erro}; feche o arquivo e repita") from None
            apagados.append(caminho)
    return apagados
