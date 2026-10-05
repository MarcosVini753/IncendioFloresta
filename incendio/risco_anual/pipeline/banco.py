from __future__ import annotations

import contextlib
import importlib.metadata
import json
import math
import platform
import sqlite3
from collections.abc import Iterator
from dataclasses import astuple, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import sklearn

from . import execucao

if TYPE_CHECKING:
    from .ajuste import ResultadoBusca

DDL = """CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY,
    inicio TEXT NOT NULL,
    fim TEXT,
    situacao TEXT NOT NULL CHECK (situacao IN ('em_andamento', 'concluida', 'interrompida')),
    comando TEXT NOT NULL,
    impressao_config TEXT NOT NULL,
    impressao_fontes TEXT NOT NULL,
    versao_python TEXT NOT NULL,
    versao_sklearn TEXT NOT NULL,
    versao_xgboost TEXT
);
CREATE TABLE IF NOT EXISTS chaves (
    id INTEGER PRIMARY KEY,
    modelo TEXT NOT NULL,
    escopo TEXT NOT NULL CHECK (escopo IN ('acre', 'oeste', 'leste')),
    ultimo_ano_treino INTEGER NOT NULL,
    fonte_cicatriz TEXT NOT NULL,
    preditores TEXT NOT NULL,
    agrupamento_cv TEXT NOT NULL,
    n_pastas INTEGER NOT NULL,
    semente INTEGER NOT NULL,
    divisao TEXT NOT NULL,
    defasagem_clima INTEGER NOT NULL,
    metrica TEXT NOT NULL CHECK (metrica IN ('pr_auc', 'roc_auc')),
    impressao_espaco TEXT NOT NULL,
    impressao_tabela TEXT NOT NULL,
    UNIQUE (modelo, escopo, ultimo_ano_treino, fonte_cicatriz, preditores, agrupamento_cv,
            n_pastas, semente, divisao, defasagem_clima, metrica, impressao_espaco, impressao_tabela)
);
CREATE TABLE IF NOT EXISTS candidatos (
    id INTEGER PRIMARY KEY,
    chave_id INTEGER NOT NULL REFERENCES chaves (id),
    execucao_id INTEGER NOT NULL REFERENCES execucoes (id),
    ordem INTEGER NOT NULL,
    parametros TEXT NOT NULL,
    pr_auc_media REAL,
    pr_auc_desvio REAL,
    roc_auc_media REAL,
    roc_auc_desvio REAL,
    pr_auc_pastas TEXT NOT NULL,
    n_linhas INTEGER NOT NULL,
    n_positivos INTEGER NOT NULL,
    segundos REAL NOT NULL,
    UNIQUE (chave_id, execucao_id, ordem)
);
CREATE TABLE IF NOT EXISTS vencedores (
    chave_id INTEGER PRIMARY KEY REFERENCES chaves (id),
    candidato_id INTEGER NOT NULL REFERENCES candidatos (id),
    execucao_id INTEGER NOT NULL REFERENCES execucoes (id),
    parametros TEXT NOT NULL,
    pr_auc_media REAL NOT NULL,
    gravado_em TEXT NOT NULL
);
"""
VERSAO_ESQUEMA = 1


@dataclass(frozen=True)
class Chave:
    modelo: str
    escopo: str
    ultimo_ano_treino: int
    fonte_cicatriz: str
    preditores: str
    agrupamento_cv: str
    n_pastas: int
    semente: int
    divisao: str
    defasagem_clima: int
    metrica: str
    impressao_espaco: str
    impressao_tabela: str


CAMPOS_CHAVE = tuple(f.name for f in fields(Chave))
_FILTRO_CHAVE = " AND ".join(f"c.{campo} = ?" for campo in CAMPOS_CHAVE)


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _caminho(con: sqlite3.Connection) -> str:
    for _, nome, arquivo in con.execute("PRAGMA database_list"):
        if nome == "main":
            return arquivo
    return "?"


@contextlib.contextmanager
def traduzir_travamento(caminho: Path) -> Iterator[None]:
    try:
        yield
    except sqlite3.OperationalError as erro:
        texto = str(erro).lower()
        if "locked" in texto or "busy" in texto:
            raise SystemExit(f"ERRO banco travado: {caminho}; feche outros processos ou pause o OneDrive e repita") from None
        raise SystemExit(f"ERRO banco {caminho}: {erro}") from None


def conectar(caminho: Path, criar: bool = True, timeout: float = 30.0) -> sqlite3.Connection | None:
    caminho = Path(caminho)
    if not criar and not caminho.exists():
        return None
    with traduzir_travamento(caminho):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(caminho, timeout=timeout)
        try:
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("PRAGMA journal_mode = DELETE")
            versao = con.execute("PRAGMA user_version").fetchone()[0]
            if versao == 0 and not criar:
                con.close()
                return None
            if versao == 0:
                con.executescript(DDL)
                con.execute(f"PRAGMA user_version = {VERSAO_ESQUEMA}")
                con.commit()
            elif versao != VERSAO_ESQUEMA:
                raise SystemExit(f"ERRO {caminho}: versao de esquema {versao} desconhecida (esperada {VERSAO_ESQUEMA})")
        except BaseException:
            con.close()
            raise
    return con


def _versao_xgboost() -> str | None:
    try:
        return importlib.metadata.version("xgboost")
    except importlib.metadata.PackageNotFoundError:
        return None


def iniciar_execucao(con: sqlite3.Connection, comando: str, impressao_config: str, impressao_fontes: str) -> int:
    with traduzir_travamento(_caminho(con)), con:
        cursor = con.execute(
            "INSERT INTO execucoes (inicio, situacao, comando, impressao_config, impressao_fontes, versao_python, versao_sklearn, versao_xgboost) "
            "VALUES (?, 'em_andamento', ?, ?, ?, ?, ?, ?)",
            (_agora(), comando, impressao_config, impressao_fontes, platform.python_version(), sklearn.__version__, _versao_xgboost()),
        )
    return int(cursor.lastrowid)


def finalizar_execucao(con: sqlite3.Connection, execucao_id: int, situacao: str) -> None:
    with traduzir_travamento(_caminho(con)), con:
        con.execute("UPDATE execucoes SET fim = ?, situacao = ? WHERE id = ?", (_agora(), situacao, int(execucao_id)))


def vencedor(con: sqlite3.Connection, chave: Chave) -> dict | None:
    with traduzir_travamento(_caminho(con)):
        linha = con.execute(
            "SELECT v.chave_id, v.candidato_id, v.execucao_id, v.parametros, v.pr_auc_media, v.gravado_em "
            f"FROM vencedores v JOIN chaves c ON c.id = v.chave_id WHERE {_FILTRO_CHAVE}",
            astuple(chave),
        ).fetchone()
    if linha is None:
        return None
    return {
        "chave_id": int(linha[0]),
        "candidato_id": int(linha[1]),
        "execucao_id": int(linha[2]),
        "parametros": json.loads(linha[3]),
        "parametros_texto": linha[3],
        "pr_auc_media": float(linha[4]),
        "gravado_em": linha[5],
    }


def outras_chaves(con: sqlite3.Connection, chave: Chave) -> int:
    with traduzir_travamento(_caminho(con)):
        total = con.execute(
            "SELECT COUNT(*) FROM chaves c WHERE c.modelo = ? AND c.escopo = ? AND c.ultimo_ano_treino = ? "
            f"AND NOT ({_FILTRO_CHAVE})",
            (chave.modelo, chave.escopo, chave.ultimo_ano_treino, *astuple(chave)),
        ).fetchone()[0]
    return int(total)


def _real(valor) -> float | None:
    if valor is None:
        return None
    numero = float(valor)
    return numero if math.isfinite(numero) else None


def _json(valor) -> str:
    return json.dumps(valor, sort_keys=True, allow_nan=False)


def gravar_chave(con: sqlite3.Connection, execucao_id: int, chave: Chave, resultado: ResultadoBusca, n_linhas: int, n_positivos: int) -> None:
    gravado_em = _agora()
    with traduzir_travamento(_caminho(con)), con:
        valores = astuple(chave)
        con.execute(f"INSERT OR IGNORE INTO chaves ({', '.join(CAMPOS_CHAVE)}) VALUES ({', '.join('?' * len(CAMPOS_CHAVE))})", valores)
        chave_id = con.execute(f"SELECT c.id FROM chaves c WHERE {_FILTRO_CHAVE}", valores).fetchone()[0]
        linhas = []
        for linha in resultado.candidatos.itertuples(index=False):
            pastas = [_real(v) for v in json.loads(linha.pr_auc_pastas)]
            linhas.append((
                chave_id,
                int(execucao_id),
                int(linha.ordem),
                _json(json.loads(linha.parametros)),
                _real(linha.pr_auc_media),
                _real(linha.pr_auc_desvio),
                _real(linha.roc_auc_media),
                _real(linha.roc_auc_desvio),
                _json(pastas),
                int(n_linhas),
                int(n_positivos),
                float(linha.segundos),
            ))
        con.executemany(
            "INSERT INTO candidatos (chave_id, execucao_id, ordem, parametros, pr_auc_media, pr_auc_desvio, roc_auc_media, roc_auc_desvio, "
            "pr_auc_pastas, n_linhas, n_positivos, segundos) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            linhas,
        )
        candidato = con.execute(
            "SELECT id, parametros, pr_auc_media FROM candidatos WHERE chave_id = ? AND execucao_id = ? AND ordem = ?",
            (chave_id, int(execucao_id), int(resultado.ordem_vencedor)),
        ).fetchone()
        if candidato is None:
            raise ValueError(f"gravar_chave: vencedor de ordem {resultado.ordem_vencedor} ausente nos candidatos")
        con.execute(
            "INSERT OR REPLACE INTO vencedores (chave_id, candidato_id, execucao_id, parametros, pr_auc_media, gravado_em) VALUES (?, ?, ?, ?, ?, ?)",
            (chave_id, candidato[0], int(execucao_id), candidato[1], candidato[2], gravado_em),
        )


def exportar_csv(con: sqlite3.Connection, pasta: Path, comuns: dict) -> tuple[Path, Path]:
    colunas_chave = ", ".join(f"c.{campo}" for campo in CAMPOS_CHAVE)
    with traduzir_travamento(_caminho(con)):
        candidatos = pd.read_sql_query(
            f"SELECT c.id AS chave_id, {colunas_chave}, k.id AS candidato_id, k.execucao_id, e.inicio AS execucao_inicio, "
            "k.ordem, k.parametros, k.pr_auc_media, k.pr_auc_desvio, k.roc_auc_media, k.roc_auc_desvio, k.pr_auc_pastas, "
            "k.n_linhas, k.n_positivos, k.segundos "
            "FROM candidatos k JOIN chaves c ON c.id = k.chave_id JOIN execucoes e ON e.id = k.execucao_id "
            "ORDER BY c.id, k.execucao_id, k.ordem",
            con,
        )
        vencedores = pd.read_sql_query(
            f"SELECT c.id AS chave_id, {colunas_chave}, v.candidato_id, v.execucao_id, v.parametros, v.pr_auc_media, v.gravado_em "
            "FROM vencedores v JOIN chaves c ON c.id = v.chave_id ORDER BY c.id",
            con,
        )
    pasta = Path(pasta)
    return (
        execucao.gravar_tabela(candidatos, pasta / "banco_candidatos.csv", comuns),
        execucao.gravar_tabela(vencedores, pasta / "banco_vencedores.csv", comuns),
    )
