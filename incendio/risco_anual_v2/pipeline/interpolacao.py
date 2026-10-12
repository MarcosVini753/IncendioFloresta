from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from . import dados

METODOS = ("vizinho", "bilinear")


@dataclass(frozen=True)
class PesosBilineares:
    ids: np.ndarray
    pesos: np.ndarray
    reserva: np.ndarray

    def resumo(self) -> dict:
        usados = (self.pesos > 0).sum(axis=1)
        return {
            "n_celulas": int(self.ids.shape[0]),
            "quatro_vizinhos": int((usados == 4).sum()),
            "renormalizadas": int(((usados < 4) & ~self.reserva).sum()),
            "reserva_vizinho_valido": int(self.reserva.sum()),
        }


def _coeficientes(transformacao: Sequence[float]) -> tuple[float, float, float, float]:
    a, b, c, d, e, f = (float(x) for x in list(transformacao)[:6])
    if abs(b) > 0 or abs(d) > 0:
        raise SystemExit(f"ERRO interpolacao: transformacao com rotacao ({list(transformacao)[:6]}); esperado norte para cima")
    if not a > 0 or not e < 0:
        raise SystemExit(f"ERRO interpolacao: transformacao com eixo invertido (a={a}, e={e})")
    return a, c, e, f


def mapa_de_ids(mascara: np.ndarray) -> np.ndarray:
    mascara = np.asarray(mascara, dtype=bool)
    ids = np.full(mascara.shape, -1, dtype=np.int64)
    ids[mascara] = np.arange(int(mascara.sum()), dtype=np.int64)
    return ids


def mascara_do_clima(forma: Sequence[int], lin: np.ndarray, col: np.ndarray) -> np.ndarray:
    mascara = np.zeros(tuple(int(x) for x in forma), dtype=bool)
    mascara[np.asarray(lin, dtype=np.int64), np.asarray(col, dtype=np.int64)] = True
    return mascara


def vizinho_valido(lon: np.ndarray, lat: np.ndarray, transformacao: Sequence[float], mascara: np.ndarray) -> np.ndarray:
    a, c, e, f = _coeficientes(transformacao)
    mascara = np.asarray(mascara, dtype=bool)
    n_lin, n_col = mascara.shape
    col = np.clip(np.floor((np.asarray(lon, dtype=np.float64) - c) / a).astype(np.int64), 0, n_col - 1)
    lin = np.clip(np.floor((np.asarray(lat, dtype=np.float64) - f) / e).astype(np.int64), 0, n_lin - 1)
    lin, col = dados._puxar_para_valido(lin, col, mascara)
    return mapa_de_ids(mascara)[lin, col]


def pesos_bilineares(lon: np.ndarray, lat: np.ndarray, transformacao: Sequence[float], mascara: np.ndarray, reserva_ids: np.ndarray | None = None) -> PesosBilineares:
    a, c, e, f = _coeficientes(transformacao)
    mascara = np.asarray(mascara, dtype=bool)
    if not mascara.any():
        raise SystemExit("ERRO interpolacao: mascara do clima sem nenhum pixel valido")
    lon = np.asarray(lon, dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)
    if lon.shape != lat.shape or lon.ndim != 1:
        raise SystemExit("ERRO interpolacao: lon e lat devem ser vetores do mesmo tamanho")
    if not (np.isfinite(lon).all() and np.isfinite(lat).all()):
        raise SystemExit("ERRO interpolacao: lon ou lat com valor nao finito")
    n_lin, n_col = mascara.shape
    u = (lon - c) / a - 0.5
    v = (lat - f) / e - 0.5
    j0 = np.floor(u).astype(np.int64)
    i0 = np.floor(v).astype(np.int64)
    du = u - j0
    dv = v - i0
    lin = np.column_stack([i0, i0, i0 + 1, i0 + 1])
    col = np.column_stack([j0, j0 + 1, j0, j0 + 1])
    pesos = np.column_stack([(1 - dv) * (1 - du), (1 - dv) * du, dv * (1 - du), dv * du])
    dentro = (lin >= 0) & (lin < n_lin) & (col >= 0) & (col < n_col)
    ids_grade = mapa_de_ids(mascara)
    ids = np.full(lin.shape, -1, dtype=np.int64)
    ids[dentro] = ids_grade[lin[dentro], col[dentro]]
    pesos = np.where(ids >= 0, pesos, 0.0)
    soma = pesos.sum(axis=1)
    reserva = soma <= 0
    if reserva.any():
        if reserva_ids is None:
            reserva_ids = vizinho_valido(lon[reserva], lat[reserva], transformacao, mascara)
        else:
            reserva_ids = np.asarray(reserva_ids, dtype=np.int64)[reserva]
        if (reserva_ids < 0).any() or (reserva_ids >= int(mascara.sum())).any():
            raise SystemExit("ERRO interpolacao: vizinho valido de reserva fora da mascara do clima")
        ids[reserva] = -1
        ids[reserva, 0] = reserva_ids
        pesos[reserva] = 0.0
        pesos[reserva, 0] = 1.0
        soma = pesos.sum(axis=1)
    pesos = pesos / soma[:, None]
    return PesosBilineares(ids, pesos, reserva)


def interpolar(pesos: PesosBilineares, valores: np.ndarray) -> np.ndarray:
    valores = np.asarray(valores, dtype=np.float64)
    usados = pesos.ids >= 0
    if (pesos.ids[usados] >= valores.size).any():
        raise SystemExit(f"ERRO interpolacao: id de pixel fora dos {valores.size} valores do clima")
    coletados = np.where(usados, valores[np.where(usados, pesos.ids, 0)], 0.0)
    if np.isnan(coletados[usados]).any():
        raise SystemExit("ERRO interpolacao: valor NaN num pixel valido do clima")
    return (coletados * pesos.pesos).sum(axis=1)


def vizinho(ids: np.ndarray, valores: np.ndarray) -> np.ndarray:
    return np.asarray(valores, dtype=np.float64)[np.asarray(ids, dtype=np.int64)]
