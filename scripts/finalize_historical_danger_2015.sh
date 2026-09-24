#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
product_dir="$repository_root/incendio/produtos/perigo/v1/2015"
expected_branch="feature/historical-danger-2015"

if [[ "$(git -C "$repository_root" branch --show-current)" != "$expected_branch" ]]; then
  echo "A branch ativa deve ser $expected_branch para finalizar o produto." >&2
  exit 1
fi

echo "Aguardando o produto público de Perigo 2015..."
while [[ ! -s "$product_dir/manifest.json" ]]; do
  if ! tmux has-session -t danger-2015-fuzzy 2>/dev/null; then
    echo "O cálculo Fuzzy terminou sem gerar o produto. Consulte perigo_2015_fuzzy_exact.log." >&2
    exit 1
  fi
  sleep 30
done

while tmux has-session -t danger-2015-fuzzy 2>/dev/null; do
  sleep 10
done

if [[ "$(git -C "$repository_root" branch --show-current)" != "$expected_branch" ]]; then
  echo "A branch mudou durante o cálculo. Finalização interrompida." >&2
  exit 1
fi

cd "$repository_root/incendio"
echo "Auditando janeiro, agosto e dezembro nos quatro modelos..."
MPLCONFIGDIR=/tmp/incendio-danger-final-audit .venv/bin/python exportar_perigo_2015.py --audit-samples
.venv/bin/python exportar_perigo_2015.py --validate-only
MPLCONFIGDIR=/tmp/incendio-danger-final-tests .venv/bin/python -m unittest discover -s tests -v

cd "$repository_root/frontend"
npm test
npm run build

public_dir="$repository_root/frontend/dist/data/danger/v1/2015"
for relative_path in \
  manifest.json \
  grid.geojson \
  scores/gradboost.json \
  scores/random_forest.json \
  scores/logistic_regression.json \
  scores/fuzzy_knn_k29.json; do
  test -s "$public_dir/$relative_path"
done

echo "Verificando os seis arquivos públicos por HTTP..."
./node_modules/.bin/vite preview --host 127.0.0.1 --port 4174 --strictPort &
preview_pid=$!
trap 'kill "$preview_pid" 2>/dev/null || true' EXIT
for attempt in {1..30}; do
  if curl --silent --fail --output /dev/null http://127.0.0.1:4174/; then
    break
  fi
  sleep 1
done
for relative_path in \
  manifest.json \
  grid.geojson \
  scores/gradboost.json \
  scores/random_forest.json \
  scores/logistic_regression.json \
  scores/fuzzy_knn_k29.json; do
  curl --fail --silent --show-error --head \
    "http://127.0.0.1:4174/data/danger/v1/2015/$relative_path" >/dev/null
  echo "HTTP 200: $relative_path"
done

echo "FINALIZATION_OK: produto, auditoria, testes, build e HTTP aprovados."
