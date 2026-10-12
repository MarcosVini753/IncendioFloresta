from __future__ import annotations

import functools
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
import tifffile
from pyproj import Transformer

ARQ_CICATRIZES = "Cicatrizes_Incendio_Acre_2006_2016.tif"
ARQ_PRECIPITACAO = "Precipitacao_13h_Diaria_Acre_2006_2016.tif"
ARQ_UMIDADE = "Umidade_Relativa_Diaria_Acre_2006_2016.tif"
ARQ_CENTROIDES = "centroides2003a2013.xlsx"

EPSG_CENTROIDES = 31979
ANOS_CICATRIZ = tuple(range(2006, 2017))
DATA_INICIO_CLIMA = np.datetime64("2006-01-01")
N_DIAS_CLIMA = 3652
ANOS_CLIMA = tuple(range(2006, 2016))

XG_A, XG_B = 892.980533, -91431.715127
YG_A, YG_B = 598.158593, 8690698.257560

VEG_ORDINAL = {
    "Áreas Antropizadas": 1,
    "FAP - Aluvial + Vs": 2,
    "FAP - Aluvial": 3,
    "FAP + FD": 4,
    "FD + FAP": 4,
    "FAB - Aluvial": 5,
    "FAP": 6,
    "FAB + FD": 7,
    "FD + FAB": 7,
    "FAB + FAP": 8,
    "FAP + FAB": 8,
    "FAP - Aluvial + Pab": 9,
    "Campinaranas": 10,
    "FAB + FAP + FD": 11,
    "FAP + FAB + FD": 11,
    "FAP + FD + FAB": 11,
    "FABD": 12,
    "FD": 13,
    "FD - Submontana": 14,
    "FAP + Pab": 15,
}


@dataclass(frozen=True)
class GradeRaster:
    n_lin: int
    n_col: int
    lon0: float
    lat0: float
    passo: float

    def indices(self, lon, lat, recortar: bool = True):
        col = np.floor((np.asarray(lon) - self.lon0) / self.passo).astype(np.int64)
        lin = np.floor((self.lat0 - np.asarray(lat)) / self.passo).astype(np.int64)
        if recortar:
            np.clip(col, 0, self.n_col - 1, out=col)
            np.clip(lin, 0, self.n_lin - 1, out=lin)
        else:
            fora = (col < 0) | (col >= self.n_col) | (lin < 0) | (lin >= self.n_lin)
            col[fora] = -1
            lin[fora] = -1
        return lin, col

    def centros(self):
        lat = self.lat0 - (np.arange(self.n_lin) + 0.5) * self.passo
        lon = self.lon0 + (np.arange(self.n_col) + 0.5) * self.passo
        return lat, lon


def ler_grade(caminho: str) -> GradeRaster:
    with tifffile.TiffFile(caminho) as tf:
        p = tf.pages[0]
        passo_x, passo_y, _ = p.tags[33550].value
        _, _, _, lon0, lat0, _ = p.tags[33922].value
        n_lin, n_col = p.tags[257].value, p.tags[256].value
    if not np.isclose(passo_x, passo_y):
        raise ValueError(f"{caminho}: pixel nao quadrado ({passo_x}, {passo_y})")
    return GradeRaster(n_lin, n_col, lon0, lat0, passo_x)


def nomes_bandas(caminho: str) -> list[str]:
    with tifffile.TiffFile(caminho) as tf:
        tag = tf.pages[0].tags.get(42112)
        bruto = None if tag is None else str(tag.value)
    if bruto is None:
        return []
    achados = re.findall(r'sample="(\d+)"[^>]*>([^<]+)<', bruto)
    return [nome for _, nome in sorted(achados, key=lambda t: int(t[0]))]


@functools.lru_cache(maxsize=1)
def _transformador():
    return Transformer.from_crs(EPSG_CENTROIDES, 4326, always_xy=True)


def utm_para_lonlat(x_g, y_g):
    return _transformador().transform(np.asarray(x_g), np.asarray(y_g))


@functools.lru_cache(maxsize=1)
def _transformador_inverso():
    return Transformer.from_crs(4326, EPSG_CENTROIDES, always_xy=True)


def lonlat_para_utm(lon, lat):
    return _transformador_inverso().transform(np.asarray(lon), np.asarray(lat))


def utm_para_indice_grade(x_g, y_g):
    xi = np.rint((np.asarray(x_g) - XG_B) / XG_A).astype(np.int64)
    yi = np.rint((np.asarray(y_g) - YG_B) / YG_A).astype(np.int64)
    return yi, xi


def ler_cubo(caminho: str, dtype=None) -> np.ndarray:
    arr = tifffile.imread(caminho)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    return arr if dtype is None else arr.astype(dtype)


def ler_centroides(caminho: str = ARQ_CENTROIDES) -> pd.DataFrame:
    d = pd.read_excel(caminho, engine="openpyxl")
    n0 = len(d)
    d = d[(d["x_g"] != 0) | (d["y_g2"] != 0)].copy()
    d = d[d["y_g2"] > 1e6].copy()

    d["veg"] = d["VEG_TIP"].map(VEG_ORDINAL).astype("float64")
    d["altitude"] = d["RASTERVALU"].astype("float64")
    d.loc[d["altitude"] <= -9000, "altitude"] = np.nan
    d = d.rename(columns={"Distance": "dist_estrada", "Distance_1": "dist_agua"})

    lon, lat = utm_para_lonlat(d["x_g"].values, d["y_g2"].values)
    d["lon"], d["lat"] = lon, lat

    d = d.reset_index(drop=True)
    d.attrs["linhas_descartadas"] = n0 - len(d)
    return d


def clima_valido(caminho: str) -> tuple[np.ndarray, np.ndarray]:
    cubo = ler_cubo(caminho, dtype=np.float32)
    mascara = np.isfinite(cubo).any(axis=2)
    series = cubo[mascara]
    del cubo
    return series, mascara


def datas_clima() -> np.ndarray:
    return DATA_INICIO_CLIMA + np.arange(N_DIAS_CLIMA)
