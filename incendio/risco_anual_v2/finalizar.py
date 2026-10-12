"""Finaliza a entrega aprovada somente com produto completo e árvores esperadas.

Roda em tmux, separado do cálculo; não sobrescreve alterações concorrentes.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "incendio"))
CACHE = REPO / "incendio/resultados/risco_professor_v2"
PRODUCT = REPO / "incendio/produtos/risco/v2/2025"
PYTHON = REPO / "incendio/risco_anual_v2/.venv/bin/python"


def run(*args, cwd=REPO, timeout=None, capture=False, env=None):
    print("+", " ".join(map(str, args)), flush=True)
    result = subprocess.run(list(map(str, args)), cwd=cwd, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None, timeout=timeout, env=env)
    return result.stdout.strip() if capture else None


def state(phase, **data):
    value = {"phase": phase, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **data}
    temporary = CACHE / "delivery.tmp.json"
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(CACHE / "delivery.json")
    print(json.dumps(value, ensure_ascii=False), flush=True)


def assert_main(expected):
    if run("git", "branch", "--show-current", capture=True) != "main":
        raise RuntimeError("A main não está ativa; nenhuma atualização será aplicada.")
    if run("git", "rev-parse", "HEAD", capture=True) != expected:
        raise RuntimeError("A main mudou durante o processamento; revisar antes de integrar.")
    changes = run("git", "status", "--porcelain", "--untracked-files=all", capture=True)
    if any(not line.startswith("?? incendio/produtos/risco/v2/2025/") for line in changes.splitlines()):
        raise RuntimeError("Alterações concorrentes na árvore principal; preservadas sem sobrescrita.")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def check_http_and_browser(worktree):
    dist = worktree / "frontend/dist"
    base = "data/risk/v2/2025"
    index = json.loads((dist / base / "native_sharded_grid/index.json").read_text())
    paths = [f"{base}/aggregated/{name}" for name in ("manifest.json", "mapa.geojson", "limite_acre.geojson")]
    paths += [f"{base}/native_sharded_grid/{name}" for name in ("manifest.json", "index.json")]
    paths += [f"{base}/native_sharded_grid/{entry['url']}" for entry in index["sectors"]]
    paths += [f"data/climate/v1/2025/{name}" for name in ("manifest.json", "grid.geojson", "boundary.geojson", "humidity.json", "precipitation.json", "scars.geojson")]
    if (dist / "data/risk/v1").exists() or any((dist / "data" / name).exists() for name in ("danger", "inpe", "susceptibility")):
        raise RuntimeError("Produto antigo ou Perigo indevidamente incluído no dist.")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(dist)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        for path in paths:
            with urlopen(f"{url}/{path}", timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"Arquivo público indisponível: {path}")
                response.read()
        state("http_verified", http_200=len(paths))
        env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(CACHE / "browsers"))
        run(REPO / "incendio/.venv/bin/python", worktree / "frontend/scripts/smoke-professor-v2.py",
            "--url", url, env=env, timeout=180)
    finally:
        server.shutdown()
        server.server_close()


def finalize(args):
    expected = args.expected_main
    worktree = args.worktree.resolve()
    if not worktree.is_relative_to(CACHE):
        raise ValueError("A cópia de trabalho deve ficar no cache local da entrega.")
    state("waiting_for_product", expected_main=expected)
    assert_main(expected)
    while not (PRODUCT / "aggregated/manifest.json").exists():
        status = subprocess.run(["tmux", "display-message", "-pt", "risk-professor-v2", "#{pane_dead} #{pane_dead_status}"],
                                text=True, capture_output=True)
        if status.returncode or status.stdout.startswith("1 "):
            raise RuntimeError("O cálculo terminou sem produto completo; conferir export.log e retomar pelos checkpoints.")
        time.sleep(30)
        # Checagem barata; a validação completa da árvore ocorre antes da integração.
        if run("git", "rev-parse", "HEAD", capture=True) != expected:
            raise RuntimeError("A main mudou; finalização suspensa para preservar o trabalho concorrente.")
    assert_main(expected)
    progress = json.loads((CACHE / "progress.json").read_text())
    if progress["completed_combinations"] != 16:
        raise RuntimeError("As 16 combinações ainda não estão completas.")
    state("auditing_product")
    run(PYTHON, REPO / "incendio/exportar_risco_professor_v2.py", "--validate-only")
    manifest = json.loads((PRODUCT / "aggregated/manifest.json").read_text())
    if manifest["default_model"] != "random_forest" or manifest["default_scenario"] != "todos_historico":
        raise RuntimeError("Padrões iniciais diferentes do aprovado.")
    if len(manifest["models"]) != 4 or len(manifest["scenarios"]) != 4:
        raise RuntimeError("Produto incompleto.")
    if any(p.stat().st_size >= 100_000_000 for p in PRODUCT.rglob("*") if p.is_file()):
        raise RuntimeError("Artefato excede o limite por arquivo para publicação Git.")
    from risco_anual_v2.pipeline import config
    cfg = config.carregar(REPO / "incendio/risco_anual_v2/config_2025.json")
    declared = {item["file"]: item["sha256"] for item in manifest["provenance"]["sources"]}
    for path in (cfg.centroides, *cfg.cicatriz, *cfg.precipitacao, *cfg.umidade, *cfg.conferir):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != declared[path.name]:
            raise RuntimeError(f"Insumo alterado durante o cálculo: {path.name}")
    for commit in args.commits:
        changed = run("git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit, capture=True).splitlines()
        if not changed or any(not (path.startswith("frontend/") or path in ("README.md", "incendio/PRODUTOS_WEB.md")) for path in changed):
            raise RuntimeError("Commit preparado contém caminhos fora do escopo esperado.")
    worktree_changes = run("git", "status", "--porcelain", cwd=worktree, capture=True)
    if any(line != "?? incendio/produtos/risco/v2" for line in worktree_changes.splitlines()):
        raise RuntimeError("A cópia de trabalho foi modificada depois dos commits; preservada para revisão.")
    link = worktree / "incendio/produtos/risco/v2"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        if link.resolve() != PRODUCT.parent:
            raise RuntimeError("Destino da cópia de trabalho já ocupado.")
    else:
        link.symlink_to(PRODUCT.parent, target_is_directory=True)
    state("building_isolated_frontend")
    run("npm", "run", "build", cwd=worktree / "frontend", timeout=600)
    check_http_and_browser(worktree)
    assert_main(expected)
    state("integrating_main")
    run("git", "add", "incendio/produtos/risco/v2/2025")
    run("git", "commit", "-m", "feat(data): publish complete professor v2 risk product for 2025")
    run("git", "cherry-pick", *args.commits)
    if run("git", "diff", args.commits[-1], "--", "frontend", "README.md", "incendio/PRODUTOS_WEB.md", capture=True):
        raise RuntimeError("Código integrado difere do código verificado.")
    run("npm", "run", "build", cwd=REPO / "frontend", timeout=600)
    if run("git", "status", "--porcelain", capture=True):
        raise RuntimeError("Árvore não está limpa; envio suspenso.")
    state("pushing_main")
    run("git", "push", "origin", "main", timeout=1800)
    state("complete", main_commit=run("git", "rev-parse", "HEAD", capture=True), combinations=16)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--commits", nargs="+", required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    args = parser.parse_args()
    try:
        finalize(args)
    except Exception as error:
        state("stopped", error=str(error))
        raise
