from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import psutil
import rasterio
from rasterio.errors import RasterioError

from . import config, dados, geo, risco

if TYPE_CHECKING:
    from .config import Config

ANO = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
DATA = re.compile(r"^\d{8}(?!\d)")
VERSAO_CACHE = 1
DICA_CICATRIZ = (
    "um arquivo de cicatriz anual precisa de uma banda por ano com o ano na descricao; "
    "arquivos sem ano, como o _MODIS, vao em fontes.conferir"
)
ESTATISTICAS_CLIMA = ("ur_min", "ur_max", "ur_media", "prec_min", "prec_max", "prec_media", "prec_acum")
MEMORIA_MINIMA_GIB = 3.0


@dataclass(frozen=True)
class InfoRaster:
    caminho: Path
    papel: str
    tamanho: int
    mtime_ns: int
    n_bandas: int
    dtype: str
    forma: tuple[int, int]
    transformacao: tuple[float, ...]
    crs: str
    descricoes: tuple[str | None, ...]


@dataclass
class Base:
    est: pd.DataFrame
    clima_anual: pd.DataFrame
    anos_cicatriz: tuple[int, ...]
    anos_clima: tuple[int, ...]
    perfil_clima: dict
    relatorio: dict
    impressao_fontes: str


def ano_da_banda(caminho: Path, indice: int, descricao: str | None) -> int:
    achados = ANO.findall(descricao or "")
    if len(achados) != 1:
        raise SystemExit(
            f"ERRO {caminho} banda {indice}: {descricao!r} precisa ter exatamente um ano; achados {achados}; {DICA_CICATRIZ}"
        )
    return int(achados[0])


def data_da_banda(caminho: Path, indice: int, descricao: str | None) -> date:
    texto = descricao or ""
    try:
        if not DATA.match(texto):
            raise ValueError
        return datetime.strptime(texto[:8], "%Y%m%d").date()
    except ValueError:
        raise SystemExit(f"ERRO {caminho} banda {indice}: {descricao!r} nao comeca com uma data AAAAMMDD valida") from None


def inspecionar(caminho: Path, papel: str) -> InfoRaster:
    caminho = Path(caminho)
    try:
        estado = caminho.stat()
        with rasterio.open(caminho) as ds:
            return InfoRaster(
                caminho=caminho,
                papel=papel,
                tamanho=estado.st_size,
                mtime_ns=estado.st_mtime_ns,
                n_bandas=ds.count,
                dtype=str(ds.dtypes[0]),
                forma=(ds.height, ds.width),
                transformacao=tuple(float(x) for x in tuple(ds.transform)[:6]),
                crs=ds.crs.to_string() if ds.crs else "",
                descricoes=tuple(ds.descriptions),
            )
    except (RasterioError, OSError) as erro:
        raise SystemExit(f"ERRO ao ler {caminho}: {erro}") from None


def grade_de(info: InfoRaster) -> geo.GradeRaster:
    a, b, c, d, e, f = info.transformacao
    if abs(b) > 0 or abs(d) > 0:
        raise SystemExit(f"ERRO {info.caminho}: transformacao com rotacao ({info.transformacao}); esperado norte para cima")
    if not (a > 0 and np.isclose(a, -e, rtol=1e-9, atol=0.0)):
        raise SystemExit(f"ERRO {info.caminho}: pixel nao quadrado ou eixo invertido (a={a}, e={e})")
    altura, largura = info.forma
    return geo.GradeRaster(int(altura), int(largura), float(c), float(f), float(a))


def chaves(info: InfoRaster) -> list:
    leitor = ano_da_banda if info.papel == "cicatriz" else data_da_banda
    lista = []
    vistos: dict = {}
    for indice, descricao in enumerate(info.descricoes, start=1):
        chave = leitor(info.caminho, indice, descricao)
        if chave in vistos:
            raise SystemExit(
                f"ERRO {info.caminho}: {chave} repetido nas bandas {vistos[chave]} e {indice} do mesmo arquivo"
            )
        vistos[chave] = indice
        lista.append(chave)
    return lista


def _mesma_grade(a: InfoRaster, b: InfoRaster) -> bool:
    return a.forma == b.forma and a.crs == b.crs and np.allclose(a.transformacao, b.transformacao, rtol=0.0, atol=1e-9)


def _conferir_grades(infos: Sequence[InfoRaster], rotulo: str) -> None:
    for info in infos[1:]:
        if not _mesma_grade(infos[0], info):
            raise SystemExit(
                f"ERRO {rotulo}: {info.caminho} tem grade diferente de {infos[0].caminho} "
                f"(forma {info.forma} x {infos[0].forma}, crs {info.crs} x {infos[0].crs}, "
                f"transformacao {info.transformacao} x {infos[0].transformacao})"
            )


def _ler(info: InfoRaster, **opcoes) -> np.ndarray:
    try:
        with rasterio.open(info.caminho) as ds:
            return ds.read(**opcoes)
    except (RasterioError, OSError) as erro:
        raise SystemExit(f"ERRO ao ler {info.caminho}: {erro}") from None


def _diferencas(lista: list[tuple], rotulo: str) -> None:
    if not lista:
        return
    partes = [f"{chave} ({a} x {b}, maior diferenca absoluta {d:g})" for chave, a, b, d in lista[:10]]
    resto = f"; e mais {len(lista) - 10}" if len(lista) > 10 else ""
    raise SystemExit(f"ERRO {rotulo}: {len(lista)} chave(s) repetida(s) com valores diferentes: {'; '.join(partes)}{resto}")


def unir_cicatrizes(infos: Sequence[InfoRaster]) -> tuple[np.ndarray, tuple[int, ...], dict]:
    _conferir_grades(infos, "cicatriz")
    uniao: dict[int, tuple[np.ndarray, Path]] = {}
    deduplicados = []
    diferentes = []
    for info in infos:
        if not np.issubdtype(np.dtype(info.dtype), np.integer):
            raise SystemExit(f"ERRO {info.caminho}: cicatriz precisa de dtype inteiro; recebido {info.dtype}")
        anos = chaves(info)
        cubo = _ler(info)
        for k, ano in enumerate(anos):
            banda = cubo[k]
            menor, maior = int(banda.min()), int(banda.max())
            if menor < 0 or maior > 366:
                valor = menor if menor < 0 else maior
                raise SystemExit(f"ERRO {info.caminho} banda {k + 1}: valor {valor} fora de 0 a 366")
            if ano in uniao:
                anterior, origem = uniao[ano]
                if np.array_equal(anterior, banda):
                    deduplicados.append({"ano": ano, "mantido": origem.as_posix(), "repetido": info.caminho.as_posix()})
                else:
                    diferenca = float(np.abs(anterior.astype(np.int64) - banda.astype(np.int64)).max())
                    diferentes.append((ano, origem.name, info.caminho.name, diferenca))
                continue
            uniao[ano] = (banda.astype(np.int16), info.caminho)
        del cubo
    _diferencas(diferentes, "cicatriz")
    anos = tuple(sorted(uniao))
    bandas = np.stack([uniao[a][0] for a in anos]).astype(np.int16)
    registro = {
        "anos": list(anos),
        "deduplicados": deduplicados,
        "origem": {str(a): uniao[a][1].as_posix() for a in anos},
    }
    return bandas, anos, registro


def unir_clima(infos: Sequence[InfoRaster]) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    papel = infos[0].papel
    _conferir_grades(infos, papel)
    uniao: dict[date, tuple[np.ndarray, Path]] = {}
    deduplicadas = []
    diferentes = []
    mascara = None
    origem_mascara = None
    for info in infos:
        datas = chaves(info)
        cubo = _ler(info, out_dtype="float64")
        valida = np.isfinite(cubo).any(axis=0)
        if mascara is None:
            mascara, origem_mascara = valida, info.caminho
        elif not np.array_equal(mascara, valida):
            raise SystemExit(f"ERRO {papel}: mascara valida de {info.caminho} diferente da de {origem_mascara}")
        valores = cubo[:, mascara]
        del cubo
        com_nan = np.flatnonzero(np.isnan(valores).any(axis=1))
        if com_nan.size:
            raise SystemExit(f"ERRO {info.caminho} banda {int(com_nan[0]) + 1}: NaN dentro da mascara valida do clima")
        for k, dia in enumerate(datas):
            if dia in uniao:
                anterior, origem = uniao[dia]
                if np.allclose(anterior, valores[k], rtol=0.0, atol=1e-6, equal_nan=True):
                    deduplicadas.append({"data": dia.isoformat(), "mantido": origem.as_posix(), "repetido": info.caminho.as_posix()})
                else:
                    diferentes.append((dia.isoformat(), origem.name, info.caminho.name, float(np.nanmax(np.abs(anterior - valores[k])))))
                continue
            uniao[dia] = (valores[k], info.caminho)
    _diferencas(diferentes, papel)
    ordem = sorted(uniao)
    datas = np.array(ordem, dtype="datetime64[D]")
    serie = np.stack([uniao[d][0] for d in ordem]).astype(np.float64)
    registro = {
        "arquivos": [i.caminho.as_posix() for i in infos],
        "n_datas": int(datas.size),
        "primeira": str(datas[0]),
        "ultima": str(datas[-1]),
        "datas_repetidas": len(deduplicadas),
        "deduplicadas": deduplicadas,
    }
    return datas, serie, mascara, registro


def alinhar_clima(datas_p: np.ndarray, prec: np.ndarray, datas_u: np.ndarray, umid: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    comuns = np.intersect1d(datas_p, datas_u)
    if comuns.size == 0:
        raise SystemExit("ERRO clima: precipitacao e umidade sem nenhuma data em comum")
    em_p = np.isin(datas_p, comuns)
    em_u = np.isin(datas_u, comuns)
    so_uma = {}
    for nome, datas, dentro in (("precipitacao", datas_p, em_p), ("umidade", datas_u, em_u)):
        fora = datas[~dentro]
        if fora.size:
            so_uma[nome] = {"n": int(fora.size), "primeira": str(fora.min()), "ultima": str(fora.max())}
    return comuns, prec[em_p], umid[em_u], so_uma


def _anos_de(datas: np.ndarray) -> np.ndarray:
    return datas.astype("datetime64[Y]").astype(np.int64) + 1970


def anos_completos(datas: np.ndarray) -> tuple[tuple[int, ...], dict[int, int]]:
    anos = _anos_de(datas)
    completos = []
    faltando = {}
    for ano in range(int(anos.min()), int(anos.max()) + 1):
        total = 366 if calendar.isleap(ano) else 365
        n = int((anos == ano).sum())
        if n == total:
            completos.append(ano)
        else:
            faltando[ano] = total - n
    return tuple(completos), faltando


def resumo_anual(datas: np.ndarray, umid: np.ndarray, prec: np.ndarray, mascara: np.ndarray, anos: Sequence[int]) -> pd.DataFrame:
    lin, col = np.nonzero(mascara)
    n = lin.size
    anos_datas = _anos_de(datas)
    blocos = []
    for ano in anos:
        sel = anos_datas == ano
        u = umid[sel]
        p = prec[sel]
        blocos.append(pd.DataFrame({
            "ano": np.full(n, ano, dtype=np.int64),
            "cli_id": np.arange(n, dtype=np.int64),
            "cli_lin": lin.astype(np.int64),
            "cli_col": col.astype(np.int64),
            "ur_min": u.min(axis=0),
            "ur_max": u.max(axis=0),
            "ur_media": u.mean(axis=0),
            "prec_min": p.min(axis=0),
            "prec_max": p.max(axis=0),
            "prec_media": p.mean(axis=0),
            "prec_acum": p.sum(axis=0),
        }))
    if not blocos:
        colunas = ["ano", "cli_id", "cli_lin", "cli_col", *ESTATISTICAS_CLIMA]
        return pd.DataFrame({c: pd.Series(dtype=np.int64 if c in ("ano", "cli_id", "cli_lin", "cli_col") else np.float64) for c in colunas})
    return pd.concat(blocos, ignore_index=True)


def conferir_uniao(info: InfoRaster, bandas: np.ndarray, referencia: InfoRaster | None = None) -> dict:
    registro = {"arquivo": info.caminho.as_posix(), "n_bandas": info.n_bandas}
    grade_igual = info.forma == tuple(bandas.shape[1:]) and (referencia is None or _mesma_grade(info, referencia))
    registro["grade_igual"] = bool(grade_igual)
    if not grade_igual:
        print(f"AVISO conferencia: {info.caminho} tem grade diferente das cicatrizes; comparacao pulada")
        return registro
    cubo = _ler(info)
    banda = cubo.max(axis=0) if cubo.shape[0] > 1 else cubo[0]
    del cubo
    queimou = banda > 0
    uniao = (bandas > 0).any(axis=0)
    registro["pixels_maior_que_zero"] = int(queimou.sum())
    registro["pixels_uniao_anual"] = int(uniao.sum())
    registro["igual_a_uniao"] = bool(np.array_equal(queimou, uniao))
    registro["so_no_arquivo"] = int((queimou & ~uniao).sum())
    registro["so_na_uniao"] = int((~queimou & uniao).sum())
    registro["pixels_em_mais_de_um_ano"] = int(((bandas > 0).sum(axis=0) > 1).sum())
    bate = np.zeros(banda.shape, dtype=bool)
    for k in range(bandas.shape[0]):
        bate |= (bandas[k] > 0) & (bandas[k] == banda)
    registro["valor_e_dia_de_algum_ano"] = int((bate & queimou).sum())
    registro["todos_os_valores_sao_dia_de_algum_ano"] = bool(registro["valor_e_dia_de_algum_ano"] == registro["pixels_maior_que_zero"])
    return registro


def _texto_chave(chave) -> str | None:
    if chave is None:
        return None
    return chave.isoformat() if isinstance(chave, date) else str(chave)


def _infos(cfg: Config) -> dict[str, list[InfoRaster]]:
    return {papel: [inspecionar(c, papel) for c in getattr(cfg, papel)] for papel in ("cicatriz", "precipitacao", "umidade", "conferir")}


def _descricao_arquivo(cfg: Config, info: InfoRaster) -> dict:
    if info.papel == "conferir":
        primeira = info.descricoes[0] if info.descricoes else None
        ultima = info.descricoes[-1] if info.descricoes else None
        n_chaves = info.n_bandas
    else:
        lista = chaves(info)
        primeira, ultima, n_chaves = _texto_chave(lista[0]), _texto_chave(lista[-1]), len(lista)
    return {
        "papel": info.papel,
        "caminho": config.relativo(cfg, info.caminho),
        "tamanho": info.tamanho,
        "mtime_ns": info.mtime_ns,
        "modificado_em": datetime.fromtimestamp(info.mtime_ns / 1e9).isoformat(timespec="seconds"),
        "bandas": info.n_bandas,
        "dtype": info.dtype,
        "forma": list(info.forma),
        "transformacao": list(info.transformacao),
        "crs": info.crs,
        "primeira": primeira,
        "ultima": ultima,
        "n_chaves": n_chaves,
    }


def impressao_fontes(cfg: Config, infos: Sequence[InfoRaster]) -> str:
    estado = cfg.centroides.stat()
    itens: list = [VERSAO_CACHE, ["centroides", config.relativo(cfg, cfg.centroides), estado.st_size, estado.st_mtime_ns, None, None, None]]
    for info in infos:
        d = _descricao_arquivo(cfg, info)
        itens.append([d["papel"], d["caminho"], d["tamanho"], d["mtime_ns"], d["primeira"], d["ultima"], d["n_chaves"]])
    texto = json.dumps(itens, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _faixas(anos: Sequence[int]) -> str:
    anos = sorted(int(a) for a in anos)
    if not anos:
        return "nenhum"
    partes = []
    inicio = anterior = anos[0]
    for ano in anos[1:] + [None]:
        if ano is not None and ano == anterior + 1:
            anterior = ano
            continue
        partes.append(str(inicio) if inicio == anterior else f"{inicio}-{anterior}")
        if ano is not None:
            inicio = anterior = ano
    return ", ".join(partes)


def imprimir_resumo(relatorio: dict) -> None:
    cic = relatorio.get("cicatriz", {})
    clima = relatorio.get("clima", {})
    dedup = sorted({d["ano"] for d in cic.get("deduplicados", [])})
    print(f"[fontes] cicatriz: {len(cic.get('anos', []))} anos ({_faixas(cic.get('anos', []))}); {len(dedup)} deduplicados ({_faixas(dedup)})")
    repetidas = clima.get("datas_repetidas", {})
    print(
        f"[fontes] clima: {clima.get('primeira')} a {clima.get('ultima')} ({clima.get('n_dias')} dias comuns); "
        f"datas repetidas {sum(repetidas.values()) if isinstance(repetidas, dict) else repetidas}; lacunas {clima.get('lacunas')}"
    )
    incompletos = clima.get("anos_incompletos", {})
    texto = ", ".join(f"{a} ({n} dias faltando)" for a, n in incompletos.items()) or "nenhum"
    print(f"[fontes] anos incompletos: {texto}")
    rotulaveis = relatorio.get("anos_rotulaveis", {})
    partes = "; ".join(f"d{d}: {_faixas(anos)}" for d, anos in sorted(rotulaveis.items()))
    print(f"[fontes] anos rotulaveis {partes}; treino: {_faixas(relatorio.get('anos_treino', []))}")


def _gravar_atomico(caminho: Path, gravar: Callable[[Path], None]) -> None:
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        gravar(temporario)
        os.replace(temporario, caminho)
    except OSError as erro:
        raise SystemExit(f"ERRO ao gravar {caminho}: {erro}") from None


def gravar_json(caminho: Path, dados_json: dict) -> None:
    texto = json.dumps(dados_json, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False)
    _gravar_atomico(caminho, lambda p: p.write_text(texto, encoding="utf-8"))


def _anos_do_relatorio(base: Base, cfg: Config) -> None:
    defasagens = sorted({cfg.defasagem_principal, *cfg.defasagens_comparacao})
    base.relatorio["anos_rotulaveis"] = {str(d): list(risco.anos_rotulaveis(base, d)) for d in defasagens}
    base.relatorio["anos_treino"] = list(risco.anos_treino(base, cfg))


def _ler_cache(pasta: Path, impressao: str) -> Base | None:
    metadados = pasta / "metadados.json"
    arquivos = (pasta / "estatica.parquet", pasta / "clima_anual.parquet")
    if not metadados.is_file() or not all(a.is_file() for a in arquivos):
        return None
    try:
        meta = json.loads(metadados.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if meta.get("versao_cache") != VERSAO_CACHE or meta.get("impressao_fontes") != impressao:
        return None
    try:
        est = pd.read_parquet(arquivos[0])
        clima_anual = pd.read_parquet(arquivos[1])
    except (OSError, ValueError) as erro:
        print(f"AVISO cache ilegivel ({erro}); reconstruindo")
        return None
    return Base(
        est=est,
        clima_anual=clima_anual,
        anos_cicatriz=tuple(meta["anos_cicatriz"]),
        anos_clima=tuple(meta["anos_clima"]),
        perfil_clima=meta["perfil_clima"],
        relatorio=meta["relatorio"],
        impressao_fontes=impressao,
    )


def _avisar_memoria() -> None:
    livre = psutil.virtual_memory().available / 2**30
    if livre < MEMORIA_MINIMA_GIB:
        print(f"AVISO memoria livre {livre:.1f} GiB")


def _reconstruir(cfg: Config, infos: dict[str, list[InfoRaster]], impressao: str, ler_centroides: Callable[[Path], pd.DataFrame]) -> Base:
    _avisar_memoria()
    bandas, anos_cicatriz, registro_cic = unir_cicatrizes(infos["cicatriz"])
    conferencia = []
    for info in infos["conferir"]:
        registro = conferir_uniao(info, bandas, infos["cicatriz"][0])
        registro["arquivo"] = config.relativo(cfg, info.caminho)
        conferencia.append(registro)
    datas_p, prec, mascara_p, registro_p = unir_clima(infos["precipitacao"])
    datas_u, umid, mascara_u, registro_u = unir_clima(infos["umidade"])
    if not np.array_equal(mascara_p, mascara_u):
        raise SystemExit("ERRO clima: mascaras de precipitacao e umidade diferentes")
    comuns, prec, umid, so_uma = alinhar_clima(datas_p, prec, datas_u, umid)
    for variavel, dados_so in so_uma.items():
        print(f"AVISO clima: {dados_so['n']} datas so em {variavel} ({dados_so['primeira']} a {dados_so['ultima']}); fora do resumo e dos anos completos")
    anos_clima, faltando = anos_completos(comuns)
    for ano, n in faltando.items():
        print(
            f"AVISO clima: {ano} incompleto ({n} dias faltando); fora de treino, rotulo e resumo; "
            f"nenhuma previsao usa o clima de {ano}; {ano} pode ser previsto so com defasagem >= 1, sem avaliacao"
        )
    clima_anual = resumo_anual(comuns, umid, prec, mascara_u, anos_clima)
    lacunas = int((comuns[-1] - comuns[0]).astype(np.int64)) + 1 - int(comuns.size)
    del prec, umid
    centroides = ler_centroides(cfg.centroides)
    est = dados.tabela_estatica(
        centroides,
        grade_clima=grade_de(infos["umidade"][0]),
        mascara_clima=mascara_u,
        cicatrizes=(grade_de(infos["cicatriz"][0]), bandas, anos_cicatriz),
    )
    del bandas
    rel = lambda texto: config.relativo(cfg, Path(texto))
    relatorio = {
        "arquivos": [_descricao_arquivo(cfg, i) for papel in infos for i in infos[papel]],
        "cicatriz": {
            "anos": list(anos_cicatriz),
            "deduplicados": [{"ano": d["ano"], "mantido": rel(d["mantido"]), "repetido": rel(d["repetido"])} for d in registro_cic["deduplicados"]],
            "origem": {a: rel(c) for a, c in registro_cic["origem"].items()},
        },
        "clima": {
            "primeira": str(comuns[0]),
            "ultima": str(comuns[-1]),
            "n_dias": int(comuns.size),
            "datas_repetidas": {"precipitacao": registro_p["datas_repetidas"], "umidade": registro_u["datas_repetidas"]},
            "lacunas": lacunas,
            "datas_so_em_uma_variavel": so_uma,
            "anos_completos": list(anos_clima),
            "anos_incompletos": {str(a): n for a, n in faltando.items()},
        },
        "conferencia": conferencia,
    }
    perfil = {"forma": list(infos["umidade"][0].forma), "transformacao": list(infos["umidade"][0].transformacao), "crs": infos["umidade"][0].crs}
    return Base(est, clima_anual, tuple(anos_cicatriz), tuple(anos_clima), perfil, relatorio, impressao)


def _gravar_cache(pasta: Path, base: Base) -> None:
    try:
        (pasta / "metadados.json").unlink(missing_ok=True)
    except OSError as erro:
        raise SystemExit(f"ERRO nao foi possivel apagar {pasta / 'metadados.json'}: {erro}; feche o arquivo e repita") from None
    _gravar_atomico(pasta / "estatica.parquet", lambda p: base.est.to_parquet(p, index=False))
    _gravar_atomico(pasta / "clima_anual.parquet", lambda p: base.clima_anual.to_parquet(p, index=False))
    meta = {
        "versao_cache": VERSAO_CACHE,
        "impressao_fontes": base.impressao_fontes,
        "anos_cicatriz": list(base.anos_cicatriz),
        "anos_clima": list(base.anos_clima),
        "perfil_clima": base.perfil_clima,
        "relatorio": base.relatorio,
    }
    gravar_json(pasta / "metadados.json", meta)


def carregar_base(cfg: Config, reconstruir: bool = False, ler_centroides: Callable[[Path], pd.DataFrame] = geo.ler_centroides) -> Base:
    infos = _infos(cfg)
    impressao = impressao_fontes(cfg, [i for papel in infos for i in infos[papel]])
    pasta = config.pasta_destino(cfg, "cache")
    base = None if reconstruir else _ler_cache(pasta, impressao)
    if base is not None:
        print(f"[cache] lendo base de {pasta}")
        _anos_do_relatorio(base, cfg)
        return base
    if reconstruir:
        print("[cache] reconstrucao pedida (--reconstruir-cache)")
    elif (pasta / "metadados.json").exists():
        print("[cache] fontes mudaram; reconstruindo")
    else:
        print(f"[cache] construindo base em {pasta}")
    base = _reconstruir(cfg, infos, impressao, ler_centroides)
    _anos_do_relatorio(base, cfg)
    _gravar_cache(pasta, base)
    gravar_json(config.destino(cfg, "relatorio_fontes.json"), base.relatorio)
    return base
