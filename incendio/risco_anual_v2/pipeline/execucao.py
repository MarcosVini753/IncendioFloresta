from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pandas as pd
import psutil

COLUNAS_TEMPOS = ["rodada", "comando", "execucao", "impressao_config", "inicio", "etapa", "segundos", "pico_mb"]


class MonitorMemoria:
    def __init__(self, intervalo: float = 0.5):
        self.intervalo = intervalo
        self.pico_mb = 0.0
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    def _medir(self) -> None:
        total = 0
        try:
            processo = psutil.Process()
            total = processo.memory_info().rss
            filhos = processo.children(recursive=True)
        except psutil.NoSuchProcess:
            filhos = []
        for filho in filhos:
            try:
                total += filho.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        self.pico_mb = max(self.pico_mb, total / 2**20)

    def _laco(self) -> None:
        while not self._parar.wait(self.intervalo):
            self._medir()

    def __enter__(self) -> MonitorMemoria:
        self._medir()
        self._parar.clear()
        self._thread = threading.Thread(target=self._laco, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join()
        self._medir()


class _Duplicador:
    def __init__(self, original, arquivo):
        self.original = original
        self.arquivo = arquivo

    def write(self, texto: str) -> int:
        self.original.write(texto)
        self.arquivo.write(texto)
        return len(texto)

    def flush(self) -> None:
        self.original.flush()
        self.arquivo.flush()

    def __getattr__(self, nome: str):
        return getattr(self.original, nome)


@contextlib.contextmanager
def registrar_log(pasta: Path) -> Iterator[Path]:
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    base = datetime.now().strftime("log_%Y%m%d_%H%M%S")
    caminho = pasta / f"{base}.txt"
    n = 0
    while caminho.exists():
        n += 1
        caminho = pasta / f"{base}_{n}.txt"
    saida, erro = sys.stdout, sys.stderr
    with caminho.open("x", encoding="utf-8") as arquivo:
        sys.stdout = _Duplicador(saida, arquivo)
        sys.stderr = _Duplicador(erro, arquivo)
        try:
            yield caminho
        finally:
            sys.stdout, sys.stderr = saida, erro


@contextlib.contextmanager
def etapa(nome: str, tempos: list[dict]) -> Iterator[dict]:
    linha = {"etapa": nome, "inicio": datetime.now().isoformat(timespec="seconds"), "execucao": None, "segundos": None, "pico_mb": None}
    inicio = time.perf_counter()
    monitor = MonitorMemoria()
    monitor.__enter__()
    try:
        yield linha
    finally:
        monitor.__exit__(None, None, None)
        linha["segundos"] = round(time.perf_counter() - inicio, 3)
        linha["pico_mb"] = round(monitor.pico_mb, 1)
        tempos.append(linha)


def gravar_tempos(tempos: list[dict], caminho: Path, comuns: dict) -> None:
    if not tempos:
        return
    caminho = Path(caminho)
    linhas = [{**linha, "rodada": comuns["rodada"], "comando": comuns["comando"], "impressao_config": comuns["impressao_config"]} for linha in tempos]
    tabela = pd.DataFrame(linhas).reindex(columns=COLUNAS_TEMPOS)
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tabela.to_csv(caminho, mode="a", header=not caminho.exists(), index=False, encoding="utf-8")
    except OSError as erro:
        raise SystemExit(f"ERRO ao gravar {caminho}: {erro}") from None


def gravar_tabela(tabela: pd.DataFrame, caminho: Path, comuns: dict) -> Path:
    caminho = Path(caminho)
    if not isinstance(tabela.index, pd.RangeIndex) or tabela.index.name is not None:
        raise ValueError(f"gravar_tabela: indice deve ser RangeIndex em {caminho}")
    saida = tabela.copy()
    saida["gerado_em"] = datetime.now().isoformat(timespec="seconds")
    saida["rodada"] = comuns["rodada"]
    saida["impressao_config"] = comuns["impressao_config"]
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        saida.to_csv(temporario, index=False, encoding="utf-8")
        os.replace(temporario, caminho)
    except OSError as erro:
        raise SystemExit(f"ERRO ao gravar {caminho}: {erro}") from None
    return caminho
