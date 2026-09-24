# Produtos web científicos

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

O perigo histórico tem cópia canônica em `produtos/perigo/v1/2015/` e segue a mesma
regra: checkpoints e modelos ajustados ficam em `resultados/`, fora do Git.

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

## Perigo histórico diário de 2015

O produto diário preserva o protocolo científico do pipeline: treino em 2006–2012,
validação em 2013, teste histórico em 2014–2015, 44 preditores e contexto de fogo
formado exclusivamente por dias anteriores. Para gerar ou retomar:

```bash
cd incendio
.venv/bin/python exportar_perigo_2015.py
```

O cubo climático é carregado uma vez. Após cada modelo/data, uma matriz agregada é
gravada em `resultados/perigo_2015_checkpoints/`; interromper e executar o mesmo
comando continua apenas os pontos pendentes. Antes do primeiro cálculo, o exportador
grava nesse diretório um manifesto com os 44 preditores, ordem das 212 células,
semente, protocolo temporal e implementação dos modelos. Uma retomada com contrato
divergente é recusada para impedir a mistura de resultados incompatíveis.

Para preparar e inspecionar esse contrato sem iniciar previsões:

```bash
.venv/bin/python exportar_perigo_2015.py --prepare-only
```

Também é possível processar modelos ou intervalos separadamente:

```bash
.venv/bin/python exportar_perigo_2015.py --models gradboost random_forest logistic_regression
.venv/bin/python exportar_perigo_2015.py --models fuzzy_knn_k29
.venv/bin/python exportar_perigo_2015.py --start 2015-08-01 --end 2015-08-31
```

O Fuzzy k-NN usa busca exata dos 29 vizinhos, sem índice aproximado. Como ele é o
modelo mais custoso, a retomada diária evita repetir dias já concluídos.
Para uma execução longa independente do terminal atual:

```bash
tmux new-session -d -s danger-2015-fuzzy \
  "cd $PWD && MPLCONFIGDIR=/tmp/incendio-danger-fuzzy-exact \
  .venv/bin/python exportar_perigo_2015.py --models fuzzy_knn_k29 \
  > resultados/perigo_2015_fuzzy_exact.log 2>&1"
tmux attach -t danger-2015-fuzzy
```

Quando os quatro checkpoints possuem 365 dias, o exportador grava `manifest.json`,
`grid.geojson` e quatro matrizes `scores/*.json`. A geometria aparece uma única vez;
linhas e colunas das matrizes seguem `dates` e `cell_order` do manifesto. Para auditar
o produto sem recalcular previsões, incluindo a proveniência científica:

```bash
.venv/bin/python exportar_perigo_2015.py --validate-only
```

Os valores são `relative_score`, nunca probabilidade calibrada ou perigo operacional.
