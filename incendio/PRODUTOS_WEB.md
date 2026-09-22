# Produtos web da suscetibilidade

## Separação de artefatos

O repositório versiona código, documentação, requisitos, o limite determinístico do
Acre e os produtos destinados ao navegador. Permanecem apenas no ambiente local:

- GeoTIFFs e planilhas de entrada;
- Parquets de preparação e caches de escores;
- modelos `.joblib`;
- PNGs, CSVs de avaliação e demais resultados intermediários;
- ambientes virtuais, caches Python e arquivos `*.Identifier`.

O diretório canônico é `produtos/suscetibilidade/v1/`. A cópia sob
`frontend/public` é criada pelos scripts do npm e nunca deve ser editada diretamente.

## Ambiente Python

Execute a partir da raiz do repositório:

```bash
python3 -m venv incendio/.venv
incendio/.venv/bin/python -m pip install -r incendio/requirements-pipeline.txt
```

Os insumos locais esperados em `incendio/` são os três GeoTIFFs e
`centroides2003a2013.xlsx`. Se `resultados/estatica.parquet` existir, o exportador o
reutiliza; caso contrário, reconstrói a tabela a partir desses insumos.

## Gerar e validar

```bash
cd incendio
.venv/bin/python exportar_suscetibilidade.py
.venv/bin/python exportar_suscetibilidade.py --validate-only
```

O alvo é “queimou em algum ano entre 2006 e 2016”. Os quatro modelos usam o mesmo
subconjunto balanceado, semente 42 e quatro preditores de paisagem. O exportador
calcula os escores das 307.410 células, valida finitude/domínio e agrega pela média
em setores de `0,28°`, preservando IDs `AC-RxxCxx`.

O arquivo `resultados/suscetibilidade_scores.parquet` é um cache local ignorado. Para
reutilizá-lo numa segunda exportação:

```bash
.venv/bin/python exportar_suscetibilidade.py --reuse-scores
```

## Contrato público agregado

`produtos/suscetibilidade/v1/aggregated/manifest.json` declara versão, modelos,
métricas da validação espacial de 25 km, período-fonte, domínio, resolução e arquivos.
Cada feature do `mapa.geojson` contém:

- ID e centroide representativo;
- `n_source_cells` e `aggregation: "mean"`;
- os quatro campos `score_*` no intervalo `[0, 1]`.

Os valores têm semântica `relative_score`; não são probabilidades calibradas.

## Grade nativa experimental

Na branch experimental, o mesmo exportador aceita `--native --reuse-scores`. Ele cria
`native_sharded_grid/index.json` e um GeoJSON por setor, com IDs
`AC-Y<Y>-X<X>`. Essa representação evita um arquivo monolítico com 307 mil polígonos.

Para auditar os dois produtos já gerados sem recalcular modelos:

```bash
.venv/bin/python exportar_suscetibilidade.py --validate-only
```

A validação percorre todos os setores, rejeita setores vazios, confirma os quatro
escores em `[0, 1]` e exige exatamente 307.410 IDs únicos.
