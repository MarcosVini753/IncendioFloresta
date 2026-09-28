# Produtos web científicos

## Clima diário e cicatrizes observadas de 2015

Na branch `feature/historical-climate-scars-2015`, o exportador gera um produto
histórico independente dos modelos. Execute, a partir de `incendio/`:

```bash
.venv/bin/python exportar_clima_2015.py
.venv/bin/python exportar_clima_2015.py --validate-only
```

Os insumos locais são os três GeoTIFFs e a malha agregada já versionada em
`produtos/suscetibilidade/v1/aggregated/mapa.geojson`. A única cópia pública
versionada fica em `produtos/clima/v1/2015/`:

- `manifest.json`: 365 datas, ordem de 212 células, cobertura por célula e fontes;
- `grid.geojson` e `boundary.geojson`: geometria sem valores diários duplicados;
- `humidity.json` e `precipitation.json`: matrizes `values[365][212][min, mean, max]`;
- `scars.geojson`: pixels do raster anual de 2015 com data de detecção.

Cada célula visual mede cerca de `0,28°`. O exportador intersecta seus polígonos
com pixels climáticos de aproximadamente `0,1°`; a média usa a área geodésica
das interseções como peso. Mínimo e máximo são espaciais naquele dia, entre
pixels válidos que intersectam a célula. Os 8 setores sem pixels válidos têm
`[null, null, null]` e aparecem sem dado no mapa. Os números não representam
extremos horários nem uma medição pontual.

O GeoTIFF de cicatrizes tem uma banda por ano; seus valores positivos codificam
o dia do ano da detecção. Em 2015, há 445 pixels positivos no raster bruto e
425 polígonos após o recorte pelo limite versionado do Acre. Um dia sem
cicatriz no produto significa somente que este raster não registrou detecção.
O clima termina em 2015, apesar de `2016` aparecer no nome dos arquivos.

Os scripts npm `predev` e `prebuild` sincronizam a cópia canônica para
`frontend/public/data/climate/`, que é gerada e ignorada pelo Git.

## Separação de artefatos

O repositório versiona código, documentação, requisitos, o limite determinístico do
Acre e os produtos destinados ao navegador. Permanecem apenas no ambiente local:

- GeoTIFFs e planilhas de entrada;
- Parquets de preparação e caches de escores;
- modelos `.joblib`;
- PNGs, CSVs de avaliação e demais resultados intermediários;
- ambientes virtuais, caches Python e arquivos `*.Identifier`.

O diretório canônico da suscetibilidade é `produtos/suscetibilidade/v1/`. A cópia sob
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
