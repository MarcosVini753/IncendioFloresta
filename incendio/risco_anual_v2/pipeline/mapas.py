from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import ListedColormap
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from rasterio.errors import RasterioError
from rasterio.transform import Affine

from . import execucao, geo

CRS_SAIDA = f"EPSG:{geo.EPSG_CENTROIDES}"
NODATA_RISCO = -9999.0
NODATA_CICATRIZ = 255
BANDAS_CLIMA = ("ur_min", "ur_max", "ur_media", "prec_min", "prec_max", "prec_media", "prec_acum")
UNIDADES = {"risco": "%", "cicatriz": "1 = cicatriz, 0 = sem cicatriz", "clima": "ur_*: %; prec_*: mm"}
COLUNAS_INDICE = ["caminho", "tipo", "ano", "cenario", "modelo", "crs", "unidade", "bandas", "rodada_arquivo", "impressao_config_arquivo"]
COR_CICATRIZ = "#1f4fff"


@dataclass(frozen=True)
class GradeSaida:
    n_lin: int
    n_col: int
    transformacao: Affine
    lin: np.ndarray
    col: np.ndarray


def grade_saida(est: pd.DataFrame) -> GradeSaida:
    Y = est["Y"].to_numpy(dtype=np.int64)
    X = est["X"].to_numpy(dtype=np.int64)
    y_max, x_min = int(Y.max()), int(X.min())
    n_lin = y_max - int(Y.min()) + 1
    n_col = int(X.max()) - x_min + 1
    transformacao = Affine(
        geo.XG_A, 0.0, geo.XG_A * (x_min - 0.5) + geo.XG_B,
        0.0, -geo.YG_A, geo.YG_A * (y_max + 0.5) + geo.YG_B,
    )
    return GradeSaida(n_lin, n_col, transformacao, y_max - Y, X - x_min)


def raster_de(grade: GradeSaida, valores: np.ndarray, nodata: float, dtype: str) -> np.ndarray:
    matriz = np.full((grade.n_lin, grade.n_col), nodata, dtype=dtype)
    matriz[grade.lin, grade.col] = np.asarray(valores).astype(dtype)
    return matriz


def gravar_geotiff(caminho: Path, matriz: np.ndarray, transformacao: Affine, crs: str, nodata: float, descricoes: Sequence[str], etiquetas: dict) -> None:
    caminho = Path(caminho)
    matriz = np.asarray(matriz)
    if matriz.ndim == 2:
        matriz = matriz[None]
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            caminho, "w", driver="GTiff", height=matriz.shape[1], width=matriz.shape[2], count=matriz.shape[0],
            dtype=matriz.dtype.name, crs=crs, transform=transformacao, nodata=nodata, compress="deflate",
        ) as ds:
            ds.write(matriz)
            for i, descricao in enumerate(descricoes, start=1):
                ds.set_band_description(i, descricao)
            if etiquetas:
                ds.update_tags(**{str(k): "" if v is None else str(v) for k, v in etiquetas.items()})
    except (RasterioError, OSError) as erro:
        raise SystemExit(f"ERRO ao gravar {caminho}: {erro}") from None


def gravar_risco(caminho: Path, grade: GradeSaida, risco_pct: np.ndarray, etiquetas: dict) -> None:
    matriz = raster_de(grade, np.asarray(risco_pct, dtype=np.float32), NODATA_RISCO, "float32")
    gravar_geotiff(caminho, matriz, grade.transformacao, CRS_SAIDA, NODATA_RISCO, ["risco_pct"], {"unidade": "%", **etiquetas})


def gravar_cicatriz(caminho: Path, grade: GradeSaida, cicatriz: np.ndarray, ano: int) -> None:
    matriz = raster_de(grade, np.asarray(cicatriz).astype(np.uint8), NODATA_CICATRIZ, "uint8")
    gravar_geotiff(caminho, matriz, grade.transformacao, CRS_SAIDA, NODATA_CICATRIZ, ["cicatriz"], {"ano": ano})


def gravar_clima(caminho: Path, perfil_clima: dict, clima_ano: pd.DataFrame, ano: int) -> None:
    n_lin, n_col = (int(x) for x in perfil_clima["forma"])
    matriz = np.full((len(BANDAS_CLIMA), n_lin, n_col), np.nan, dtype=np.float32)
    lin = clima_ano["cli_lin"].to_numpy(dtype=np.int64)
    col = clima_ano["cli_col"].to_numpy(dtype=np.int64)
    for k, nome in enumerate(BANDAS_CLIMA):
        matriz[k, lin, col] = clima_ano[nome].to_numpy(dtype=np.float64).astype(np.float32)
    transformacao = Affine(*[float(x) for x in perfil_clima["transformacao"][:6]])
    gravar_geotiff(caminho, matriz, transformacao, perfil_clima["crs"], float("nan"), list(BANDAS_CLIMA), {"ano": ano})


def titulo_risco(ano: int, cenario: str, modelo: str) -> str:
    return f"Risco de incêndio {ano} | {cenario} | {modelo}"


def _extensao(grade: GradeSaida) -> tuple[float, float, float, float]:
    t = grade.transformacao
    return (t.c, t.c + t.a * grade.n_col, t.f + t.e * grade.n_lin, t.f)


def _desenhar(ax, grade: GradeSaida, risco_pct: np.ndarray, cicatriz: np.ndarray | None, rotulo_cicatriz: str):
    matriz = raster_de(grade, np.asarray(risco_pct, dtype=np.float32), np.nan, "float32")
    imagem = ax.imshow(matriz, cmap="YlOrRd", vmin=0, vmax=100, extent=_extensao(grade), origin="upper", interpolation="nearest")
    if cicatriz is not None:
        marcas = raster_de(grade, (np.asarray(cicatriz) == 1).astype(np.float32), 0.0, "float32")
        marcas[marcas == 0] = np.nan
        ax.imshow(marcas, cmap=ListedColormap([COR_CICATRIZ]), vmin=0, vmax=1, extent=_extensao(grade), origin="upper", interpolation="nearest")
        ax.legend(handles=[Line2D([], [], marker="s", linestyle="", color=COR_CICATRIZ, label=rotulo_cicatriz)], loc="lower left", fontsize=8)
    ax.set_aspect("equal")
    ax.set_xlabel("UTM 19S leste (m)")
    ax.set_ylabel("UTM 19S norte (m)")
    return imagem


def figura_risco(grade: GradeSaida, risco_pct: np.ndarray, cicatriz: np.ndarray | None, titulo: str, ano: int | None = None) -> Figure:
    fig, ax = plt.subplots(figsize=(10, 7.5))
    imagem = _desenhar(ax, grade, risco_pct, cicatriz, f"Cicatriz {ano}" if ano is not None else "Cicatriz")
    fig.colorbar(imagem, ax=ax, label="Risco (%)", fraction=0.04)
    ax.set_title(titulo)
    return fig


def figura_painel(grade: GradeSaida, riscos: dict[str, np.ndarray], cicatriz: np.ndarray | None, titulo: str, ano: int | None = None) -> Figure:
    n = len(riscos)
    n_col = min(3, n)
    n_lin = math.ceil(n / 3)
    fig, eixos = plt.subplots(n_lin, n_col, figsize=(6 * n_col, 4.8 * n_lin), squeeze=False, constrained_layout=True)
    eixos = eixos.ravel()
    imagem = None
    for ax, (modelo, risco_pct) in zip(eixos, riscos.items()):
        imagem = _desenhar(ax, grade, risco_pct, cicatriz, f"Cicatriz {ano}" if ano is not None else "Cicatriz")
        ax.set_title(modelo)
    for ax in eixos[n:]:
        ax.set_visible(False)
    if imagem is not None:
        fig.colorbar(imagem, ax=list(eixos[:n]), label="Risco (%)", shrink=0.8)
    fig.suptitle(titulo)
    return fig


def gravar_png(fig: Figure, caminho: Path) -> None:
    caminho = Path(caminho)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(caminho, dpi=150)
    except (OSError, ValueError) as erro:
        raise SystemExit(f"ERRO ao gravar {caminho}: {erro}") from None
    finally:
        plt.close(fig)


def _tipo(caminho: Path) -> str:
    for tipo in ("risco", "cicatriz", "clima"):
        if caminho.name.startswith(f"{tipo}_"):
            return tipo
    return "outro"


def gravar_indice(saida: Path, caminho: Path, comuns: dict) -> None:
    saida = Path(saida)
    linhas = []
    for pasta in ("camadas", "mapas"):
        for arquivo in sorted((saida / pasta).glob("*.tif")):
            try:
                with rasterio.open(arquivo) as ds:
                    etiquetas = ds.tags()
                    crs = ds.crs.to_string() if ds.crs else ""
                    bandas = ";".join(d or "" for d in ds.descriptions)
            except (RasterioError, OSError) as erro:
                print(f"AVISO indice: {arquivo} nao pode ser lido ({erro}); fora do indice")
                continue
            tipo = _tipo(arquivo)
            linhas.append({
                "caminho": arquivo.relative_to(saida).as_posix(),
                "tipo": tipo,
                "ano": etiquetas.get("ano", ""),
                "cenario": etiquetas.get("cenario", ""),
                "modelo": etiquetas.get("modelo", ""),
                "crs": crs,
                "unidade": UNIDADES.get(tipo, ""),
                "bandas": bandas,
                "rodada_arquivo": etiquetas.get("rodada", ""),
                "impressao_config_arquivo": etiquetas.get("impressao_config", ""),
            })
    tabela = pd.DataFrame(linhas, columns=COLUNAS_INDICE)
    execucao.gravar_tabela(tabela, caminho, comuns)


BANDAS_RISCO_V2 = ("probabilidade_pct", "indice_risco")
UNIDADES_V2 = {
    "risco": "probabilidade_pct: % (escala real, 0-100); indice_risco: percentil da probabilidade entre as celulas do ano (0-100)",
    "cicatriz": UNIDADES["cicatriz"],
    "clima": UNIDADES["clima"],
}
CORES_INDICE = ("#313695", "#4575b4", "#74add1", "#abd9e9", "#fee090", "#fdae61", "#e31a1c", "#67000d")
COR_CICATRIZ_V2 = "#000000"
ROTULO_INDICE = "Índice de risco (percentil no ano)"


def gravar_risco_v2(caminho: Path, grade: GradeSaida, probabilidade_pct: np.ndarray, indice: np.ndarray, etiquetas: dict) -> None:
    bandas = np.stack([
        raster_de(grade, np.asarray(probabilidade_pct, dtype=np.float32), NODATA_RISCO, "float32"),
        raster_de(grade, np.asarray(indice, dtype=np.float32), NODATA_RISCO, "float32"),
    ])
    gravar_geotiff(caminho, bandas, grade.transformacao, CRS_SAIDA, NODATA_RISCO, list(BANDAS_RISCO_V2), {"unidade": UNIDADES_V2["risco"], **etiquetas})


def gravar_clima_celulas(caminho: Path, grade: GradeSaida, variaveis: dict[str, np.ndarray], etiquetas: dict) -> None:
    bandas = np.stack([raster_de(grade, np.asarray(v, dtype=np.float32), np.nan, "float32") for v in variaveis.values()])
    gravar_geotiff(caminho, bandas, grade.transformacao, CRS_SAIDA, float("nan"), list(variaveis), etiquetas)


def cores_classes(n: int) -> list[str]:
    if n == len(CORES_INDICE):
        return list(CORES_INDICE)
    if n < 3:
        raise SystemExit(f"ERRO mapas: {n} classes de percentil; minimo 3")
    mapa = plt.get_cmap("RdYlBu_r")
    frios = [matplotlib.colors.to_hex(mapa(x)) for x in np.linspace(0.0, 0.62, n - 2)]
    return frios + [CORES_INDICE[-2], CORES_INDICE[-1]]


def _norma_indice(cortes: Sequence[float]):
    from matplotlib.colors import BoundaryNorm

    cortes = [float(c) for c in cortes]
    cmap = ListedColormap(cores_classes(len(cortes) - 1)).with_extremes(bad=(1.0, 1.0, 1.0, 0.0))
    return cmap, BoundaryNorm(cortes, cmap.N)


def _desenhar_indice(ax, grade: GradeSaida, indice: np.ndarray, cicatriz: np.ndarray | None, rotulo_cicatriz: str, cortes: Sequence[float]):
    cmap, norma = _norma_indice(cortes)
    matriz = raster_de(grade, np.asarray(indice, dtype=np.float32), np.nan, "float32")
    imagem = ax.imshow(np.ma.masked_invalid(matriz), cmap=cmap, norm=norma, extent=_extensao(grade), origin="upper", interpolation="nearest")
    if cicatriz is not None:
        marcas = raster_de(grade, (np.asarray(cicatriz) == 1).astype(np.float32), 0.0, "float32")
        marcas[marcas == 0] = np.nan
        ax.imshow(marcas, cmap=ListedColormap([COR_CICATRIZ_V2]), vmin=0, vmax=1, extent=_extensao(grade), origin="upper", interpolation="nearest")
        ax.legend(handles=[Line2D([], [], marker="s", linestyle="", color=COR_CICATRIZ_V2, label=rotulo_cicatriz)], loc="lower left", fontsize=8)
    ax.set_aspect("equal")
    ax.set_xlabel("UTM 19S leste (m)")
    ax.set_ylabel("UTM 19S norte (m)")
    return imagem


def _barra_indice(fig, imagem, eixos, cortes: Sequence[float], **opcoes) -> None:
    barra = fig.colorbar(imagem, ax=eixos, ticks=[float(c) for c in cortes], **opcoes)
    barra.set_label(ROTULO_INDICE)


def figura_indice(grade: GradeSaida, indice: np.ndarray, cicatriz: np.ndarray | None, titulo: str, ano: int | None, cortes: Sequence[float]) -> Figure:
    fig, ax = plt.subplots(figsize=(10, 7.5))
    imagem = _desenhar_indice(ax, grade, indice, cicatriz, f"Cicatriz {ano}" if ano is not None else "Cicatriz", cortes)
    _barra_indice(fig, imagem, ax, cortes, fraction=0.04)
    ax.set_title(titulo)
    return fig


def figura_grade_indice(grade: GradeSaida, paineis: dict[str, np.ndarray], cicatriz: np.ndarray | None, titulo: str, ano: int | None, cortes: Sequence[float], n_col: int = 3) -> Figure:
    n = len(paineis)
    n_col = max(1, min(n_col, n))
    n_lin = math.ceil(n / n_col)
    fig, eixos = plt.subplots(n_lin, n_col, figsize=(6 * n_col, 4.8 * n_lin), squeeze=False, constrained_layout=True)
    eixos = eixos.ravel()
    imagem = None
    for ax, (rotulo, indice) in zip(eixos, paineis.items()):
        imagem = _desenhar_indice(ax, grade, indice, cicatriz, f"Cicatriz {ano}" if ano is not None else "Cicatriz", cortes)
        ax.set_title(rotulo)
    for ax in eixos[n:]:
        ax.set_visible(False)
    if imagem is not None:
        _barra_indice(fig, imagem, list(eixos[:n]), cortes, shrink=0.8)
    fig.suptitle(titulo)
    return fig


def titulo_indice(ano: int, cenario: str, modelo: str) -> str:
    return f"Índice de risco de incêndio {ano} | {cenario} | {modelo}"


def figura_dependencia(curvas: dict[str, pd.DataFrame], variavel: str, titulo: str) -> Figure:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for rotulo, tabela in curvas.items():
        ax.plot(tabela["valor"] / 1000.0, 100.0 * tabela["p_media"], marker="o", markersize=3, label=rotulo)
    ax.set_xlabel(f"{variavel} (km)")
    ax.set_ylabel("Probabilidade média prevista (%)")
    ax.set_title(titulo)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def gravar_indice_v2(saida: Path, caminho: Path, comuns: dict) -> None:
    gravar_indice(saida, caminho, comuns)
    tabela = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    tabela["unidade"] = [UNIDADES_V2.get(t, u) for t, u in zip(tabela["tipo"], tabela["unidade"])]
    for coluna in ("gerado_em", "rodada", "impressao_config"):
        if coluna in tabela.columns:
            tabela = tabela.drop(columns=coluna)
    execucao.gravar_tabela(tabela, caminho, comuns)
