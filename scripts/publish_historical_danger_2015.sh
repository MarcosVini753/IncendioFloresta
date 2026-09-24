#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
validation_log="$repository_root/incendio/resultados/perigo_2015_finalization.log"
product_path="incendio/produtos/perigo/v1/2015"
expected_branch="feature/historical-danger-2015"

echo "Aguardando a auditoria final do Perigo 2015..."
while ! rg -q '^FINALIZATION_OK:' "$validation_log" 2>/dev/null; do
  if ! tmux has-session -t danger-2015-finalize 2>/dev/null; then
    echo "A auditoria terminou sem aprovação. Consulte $validation_log." >&2
    exit 1
  fi
  sleep 30
done

cd "$repository_root"
if [[ "$(git branch --show-current)" != "$expected_branch" ]]; then
  echo "A branch ativa mudou; produto não enviado." >&2
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "A árvore possui alterações alheias ao produto; produto não enviado." >&2
  exit 1
fi
while IFS= read -r path; do
  if [[ "$path" != "$product_path/"* ]]; then
    echo "Arquivo não rastreado fora do produto: $path. Produto não enviado." >&2
    exit 1
  fi
done < <(git ls-files --others --exclude-standard)

for relative_path in \
  manifest.json \
  grid.geojson \
  scores/gradboost.json \
  scores/random_forest.json \
  scores/logistic_regression.json \
  scores/fuzzy_knn_k29.json; do
  test -s "$product_path/$relative_path"
done

git add -- "$product_path"
git diff --cached --check
if [[ "$(git diff --cached --name-only | wc -l)" -ne 6 ]]; then
  echo "O commit precisa conter exatamente os seis arquivos públicos." >&2
  exit 1
fi
git commit -m "feat(data): publish historical daily danger for 2015"
git push -u origin "$expected_branch"
echo "PUBLICATION_OK: produto versionado e $expected_branch enviada ao origin."
