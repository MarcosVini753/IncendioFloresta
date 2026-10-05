from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from . import geo

JANELAS_PRECIPITACAO = (3, 7, 15, 30, 60, 90)
JANELAS_UMIDADE = (3, 7, 15, 30)
LIMIAR_DIA_CHUVOSO = 1.0

DIA_INICIO_ESTACAO = 121
DIA_FIM_ESTACAO = 334

COLUNAS_ESTATICAS = ["veg", "dist_estrada", "dist_agua", "altitude", "lon", "lat"]


def tabela_estatica(
    centroides: pd.DataFrame | None = None,
    grade_clima: geo.GradeRaster | None = None,
    mascara_clima: np.ndarray | None = None,
    cicatrizes: tuple[geo.GradeRaster, np.ndarray, tuple[int, ...]] | None = None,
) -> pd.DataFrame:
    if (grade_clima is None) != (mascara_clima is None):
        raise ValueError("tabela_estatica: grade_clima e mascara_clima devem vir juntos")
    d = geo.ler_centroides() if centroides is None else centroides.copy()

    if grade_clima is None:
        grade_cli = geo.ler_grade(geo.ARQ_UMIDADE)
        _, mascara_cli = geo.clima_valido(geo.ARQ_UMIDADE)
    else:
        grade_cli, mascara_cli = grade_clima, np.asarray(mascara_clima, dtype=bool)
    lin, col = grade_cli.indices(d["lon"].values, d["lat"].values)
    lin, col = _puxar_para_valido(lin, col, mascara_cli)
    d["cli_lin"], d["cli_col"] = lin, col

    id_cli = np.full(mascara_cli.shape, -1, dtype=np.int64)
    id_cli[mascara_cli] = np.arange(int(mascara_cli.sum()))
    d["cli_id"] = id_cli[lin, col]

    if cicatrizes is None:
        cic, anos = _agregar_cicatrizes(d), geo.ANOS_CICATRIZ
    else:
        grade_cic, bandas, anos = cicatrizes
        cic = agregar_bandas_anuais(d, grade_cic, bandas, anos)
    for ano in anos:
        d[f"queimou_{ano}"] = cic["queimou"][ano]
        d[f"dia_{ano}"] = cic["dia"][ano]
        d[f"npix_{ano}"] = cic["npix"][ano]

    return d


def _puxar_para_valido(lin, col, mascara):
    invalido = ~mascara[lin, col]
    if not invalido.any():
        return lin, col
    vl, vc = np.nonzero(mascara)
    li, ci = lin[invalido], col[invalido]
    d2 = (vl[None, :] - li[:, None]) ** 2 + (vc[None, :] - ci[:, None]) ** 2
    melhor = d2.argmin(axis=1)
    lin = lin.copy()
    col = col.copy()
    lin[invalido] = vl[melhor]
    col[invalido] = vc[melhor]
    return lin, col


def _agregar_cicatrizes(centroides: pd.DataFrame) -> dict:
    grade = geo.ler_grade(geo.ARQ_CICATRIZES)
    cubo = geo.ler_cubo(geo.ARQ_CICATRIZES)
    saida = agregar_bandas_anuais(centroides, grade, np.moveaxis(cubo, 2, 0), geo.ANOS_CICATRIZ)
    del cubo
    return saida


def _destino_dos_pixels(centroides: pd.DataFrame, grade: geo.GradeRaster) -> np.ndarray:
    lat_c, lon_c = grade.centros()
    malha_lon, malha_lat = np.meshgrid(lon_c, lat_c)
    x_utm, y_utm = geo.lonlat_para_utm(malha_lon.ravel(), malha_lat.ravel())
    yi, xi = geo.utm_para_indice_grade(x_utm, y_utm)

    Y = centroides["Y"].values.astype(np.int64)
    X = centroides["X"].values.astype(np.int64)
    y_min, x_min = Y.min(), X.min()
    n_y, n_x = Y.max() - y_min + 1, X.max() - x_min + 1
    consulta = np.full((n_y, n_x), -1, dtype=np.int64)
    consulta[Y - y_min, X - x_min] = np.arange(len(centroides))

    yi -= y_min
    xi -= x_min
    dentro = (yi >= 0) & (yi < n_y) & (xi >= 0) & (xi < n_x)
    destino = np.full(yi.shape, -1, dtype=np.int64)
    destino[dentro] = consulta[yi[dentro], xi[dentro]]
    return destino


def agregar_bandas_anuais(
    centroides: pd.DataFrame,
    grade: geo.GradeRaster,
    bandas: np.ndarray,
    anos: Sequence[int],
) -> dict[str, dict[int, np.ndarray]]:
    destino = _destino_dos_pixels(centroides, grade)
    n_cel = len(centroides)
    saida = {"queimou": {}, "dia": {}, "npix": {}}
    for k, ano in enumerate(anos):
        dia_pix = bandas[k].ravel()
        sel = (destino >= 0) & (dia_pix > 0)
        alvo = destino[sel]
        dias = dia_pix[sel].astype(np.int64)

        npix = np.bincount(alvo, minlength=n_cel).astype(np.int32)
        primeiro = np.zeros(n_cel, dtype=np.int16)
        tmp = np.full(n_cel, 9999, dtype=np.int64)
        np.minimum.at(tmp, alvo, dias)
        tem = tmp < 9999
        primeiro[tem] = tmp[tem].astype(np.int16)

        saida["queimou"][ano] = npix > 0
        saida["dia"][ano] = primeiro
        saida["npix"][ano] = npix
    return saida


def features_climaticas() -> tuple[np.ndarray, list[str]]:
    prec, _ = geo.clima_valido(geo.ARQ_PRECIPITACAO)
    umid, _ = geo.clima_valido(geo.ARQ_UMIDADE)
    n_cel, n_dias = prec.shape

    feats: list[np.ndarray] = []
    nomes: list[str] = []

    def somar(arr: np.ndarray) -> np.ndarray:
        s = np.zeros((arr.shape[0], arr.shape[1] + 1), dtype=np.float64)
        np.cumsum(arr, axis=1, out=s[:, 1:])
        return s

    cs_prec = somar(prec)
    cs_umid = somar(umid)
    idx = np.arange(n_dias)

    for j in JANELAS_PRECIPITACAO:
        ini = np.maximum(idx - j + 1, 0)
        n = (idx - ini + 1).astype(np.float32)
        acum = (cs_prec[:, idx + 1] - cs_prec[:, ini]).astype(np.float32)
        feats.append(acum)
        nomes.append(f"prec_acum_{j}d")
        feats.append(acum / n)
        nomes.append(f"prec_media_{j}d")

    for j in JANELAS_UMIDADE:
        ini = np.maximum(idx - j + 1, 0)
        n = (idx - ini + 1).astype(np.float32)
        feats.append(((cs_umid[:, idx + 1] - cs_umid[:, ini]) / n).astype(np.float32))
        nomes.append(f"ur_media_{j}d")

    feats.append(umid.copy())
    nomes.append("ur_dia")
    feats.append(prec.copy())
    nomes.append("prec_dia")

    for j in (7, 15):
        feats.append(_min_movel(umid, j))
        nomes.append(f"ur_min_{j}d")

    feats.append(_dias_secos_consecutivos(prec, LIMIAR_DIA_CHUVOSO))
    nomes.append("dias_estiagem")

    feats.append(_indice_seca(prec, umid))
    nomes.append("indice_seca")

    cubo = np.stack(feats, axis=2).astype(np.float32)
    return cubo, nomes


def _min_movel(arr: np.ndarray, janela: int) -> np.ndarray:
    saida = arr.astype(np.float32, copy=True)
    for k in range(1, janela):
        deslocado = np.empty_like(saida)
        deslocado[:, :k] = arr[:, :1]
        deslocado[:, k:] = arr[:, :-k]
        np.minimum(saida, deslocado, out=saida)
    return saida


def _dias_secos_consecutivos(prec: np.ndarray, limiar: float) -> np.ndarray:
    seco = prec < limiar
    saida = np.zeros(prec.shape, dtype=np.float32)
    corrente = np.zeros(prec.shape[0], dtype=np.float32)
    for t in range(prec.shape[1]):
        corrente = np.where(seco[:, t], corrente + 1.0, 0.0)
        saida[:, t] = corrente
    return saida


def _indice_seca(prec: np.ndarray, umid: np.ndarray) -> np.ndarray:
    n_cel, n_dias = prec.shape
    saida = np.zeros((n_cel, n_dias), dtype=np.float32)
    q = np.zeros(n_cel, dtype=np.float32)
    for t in range(n_dias):
        deficit = np.maximum(100.0 - umid[:, t], 0.0) / 100.0 * 8.0
        chuva_efetiva = np.maximum(prec[:, t] - LIMIAR_DIA_CHUVOSO, 0.0) * 10.0
        q = np.clip(q + deficit - chuva_efetiva, 0.0, 800.0)
        saida[:, t] = q
    return saida


def amostrar_celula_dia(
    estatica: pd.DataFrame,
    cubo_clima: np.ndarray,
    nomes_clima: list[str],
    anos=geo.ANOS_CLIMA,
    negativos_por_positivo: int = 40,
    exclusao_dias: int = 45,
    semente: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(semente)
    n_cel = len(estatica)
    cli_id = estatica["cli_id"].values
    tem_clima = cli_id >= 0

    dias_por_ano = {
        ano: estatica[f"dia_{ano}"].values.astype(np.int64) for ano in geo.ANOS_CICATRIZ
    }
    datas = geo.datas_clima()
    ano_da_banda = datas.astype("datetime64[Y]").astype(int) + 1970
    inicio_do_ano = {a: int(np.argmax(ano_da_banda == a)) for a in anos}

    blocos = []
    for ano in anos:
        dia_ano = dias_por_ano[ano]
        base = inicio_do_ano[ano]

        pos = np.nonzero(
            tem_clima
            & (dia_ano >= DIA_INICIO_ESTACAO)
            & (dia_ano <= DIA_FIM_ESTACAO)
        )[0]
        dia_pos = dia_ano[pos]

        n_neg = len(pos) * negativos_por_positivo
        cand_cel = rng.choice(np.nonzero(tem_clima)[0], size=n_neg, replace=True)
        cand_dia = rng.integers(DIA_INICIO_ESTACAO, DIA_FIM_ESTACAO + 1, size=n_neg)
        d_cel = dia_ano[cand_cel]
        ambiguo = (d_cel > 0) & (np.abs(d_cel - cand_dia) <= exclusao_dias)
        cand_cel, cand_dia = cand_cel[~ambiguo], cand_dia[~ambiguo]

        celula = np.concatenate([pos, cand_cel])
        dia = np.concatenate([dia_pos, cand_dia])
        rotulo = np.concatenate(
            [np.ones(len(pos), dtype=np.int8), np.zeros(len(cand_cel), dtype=np.int8)]
        )

        bloco = pd.DataFrame({"celula": celula, "ano": ano, "dia_ano": dia, "y": rotulo})
        bloco["banda"] = base + dia - 1
        blocos.append(bloco)

    am = pd.concat(blocos, ignore_index=True)

    for c in COLUNAS_ESTATICAS:
        am[c] = estatica[c].values[am["celula"].values]

    matriz_queima = np.column_stack(
        [estatica[f"queimou_{a}"].values for a in geo.ANOS_CICATRIZ]
    ).astype(np.float32)
    anos_arr = np.array(geo.ANOS_CICATRIZ)
    taxa = np.full(len(am), np.nan, dtype=np.float32)
    ult1 = np.full(len(am), np.nan, dtype=np.float32)
    for ano in anos:
        m = am["ano"].values == ano
        anteriores = anos_arr < ano
        if anteriores.any():
            sub = matriz_queima[:, anteriores]
            taxa_cel = sub.mean(axis=1)
            taxa[m] = taxa_cel[am["celula"].values[m]]
            ult1[m] = matriz_queima[:, anos_arr == ano - 1].ravel()[
                am["celula"].values[m]
            ]
    am["taxa_queima_hist"] = taxa
    am["queimou_ano_anterior"] = ult1

    ang = 2 * np.pi * am["dia_ano"].values / 366.0
    am["dia_sin"] = np.sin(ang)
    am["dia_cos"] = np.cos(ang)

    ids = cli_id[am["celula"].values]
    bandas = am["banda"].values
    for k, nome in enumerate(nomes_clima):
        am[nome] = cubo_clima[ids, bandas, k]

    return am


def colunas_preditoras(am: pd.DataFrame, nomes_clima: list[str]) -> list[str]:
    extras = [
        "taxa_queima_hist",
        "queimou_ano_anterior",
        "dia_sin",
        "dia_cos",
        "dia_ano",
    ]
    return [c for c in COLUNAS_ESTATICAS + extras + nomes_clima if c in am.columns]
