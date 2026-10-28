# Produtos web — Risco professor v4 de 2025 e 2026

## Entrada e ambiente

Esta integração importa os GeoTIFFs finais do professor, sem executar
treinamento, previsão, seleção de parâmetros ou calibração. Os pipelines
anteriores permanecem disponíveis, mas não alimentam o frontend ativo.

O importador usa Python >=3.11, NumPy, Rasterio com o driver COG, PyProj e
Shapely. Instale `risco_anual_v4/requirements.txt` em um ambiente local.

Entradas padrão, na raiz do repositório:

- `entrega_professor_v4/mapas_geotiff/risco_30m_RandomForest_AB30C_suave_2026.tif`
- `entrega_professor_v4/mapas_geotiff/risco_30m_XGBoost_AB30C_suave_2026.tif`
- Relatórios em `entrega_professor_v4/2_resultados/treino_MapBiomas_Fogo`.
- Limite cartográfico versionado em `incendio/recursos/limite_acre.geojson`.

~~~bash
incendio/.venv/bin/python incendio/importar_risco_professor_v4.py --year 2025
incendio/.venv/bin/python incendio/importar_risco_professor_v4.py --year 2026
~~~

`--year` seleciona 2025 ou 2026 (padrão). Cada ano lê os dois GeoTIFFs e
relatórios correspondentes, publica em `incendio/produtos/risco/v4/ANO` e tem
staging e checkpoints separados. Para 2025, o treino é 2016–2024 e o clima é
de 2024; para 2026, treino 2016–2025 e clima de 2025. Não se reutilizam os
valores de 2026 como se fossem de 2025. `--source-root` e `--reports-root` permitem indicar pastas alternativas.
O pacote original, GeoTIFFs, modelos e arquivos Zone.Identifier ficam fora do Git.

## Semântica científica

Os mapas são da variante AB30C com clima suavizado, treinada com MapBiomas
Fogo 5.1. O treino vai de 2016 ao ano anterior ao previsto; o clima também é
do ano anterior, sem usar queimadas do ano previsto como histórico.
A grade original é EPSG:4326, com pixel de 0,000269494585 graus, aproximadamente 30 m.

A banda 1 já contém o valor em porcentagem. **Não multiplicar novamente por 100.**
Random Forest tem calibração temporal (Platt) fornecida pelo professor;
XGBoost tem correção de amostragem e não é calibrado. A calibração não transforma
o mapa em uma previsão operacional.

A banda 2 contém o índice percentil estadual produzido pelo histograma do
pipeline recebido. Preservar esses valores, sem recalcular rankings no frontend,
na viewport ou sobre os grupos de 5 km.

Avaliações publicadas: mapas `AB30C_suave`, anos 2023–2025, nível `30m_fogo`.
São relatórios fornecidos pelo professor, não métricas recalculadas nesta
integração. Seus histogramas aproximam ranking e métricas. Os relatórios de
2026 não contêm observações para avaliação; não associar métricas de 2025
à previsão de 2026. Pixels positivos não equivalem a incêndios confirmados.

## Produto canônico e contrato

Cada diretório `incendio/produtos/risco/v4/2025/` e `incendio/produtos/risco/v4/2026/` contém:

- `manifest.json`: contrato 4.0, modelos, unidades, calibração, treinamento,
  proveniência/hashes, classes, arquivos e avaliações históricas.
- `grid.geojson`: grupos de 5 km em UTM 19S, com geometria em EPSG:4326.
- `boundary.geojson`: limite de referência do Acre.
- `index.json`: geotransformação original, bandas e setores.
- `sectors/AC-V4-RxxxCxxx.tif`: COGs gerados; **2026 é versionado** e 2025 permanece local/ignorado.

Cada grupo guarda `value_<modelo>`, `percentile_<modelo>`,
`n_source_pixels`, `centroid`, `aggregation: mean` e
`share_<modelo>_<classe>`. Médias e proporções usam apenas pixels válidos.
A cor classifica a média dos percentis nas faixas [0,50), [50,70), [70,90),
[90,95), [95,100]. As proporções contam pixels e aproximam a proporção da área.

Os setores preservam janelas da grade original de até 1024 × 1024 pixels.
Setores vazios são omitidos. Quatro bandas Float32, nesta ordem:

1. valor percentual de Random Forest;
2. percentil de Random Forest;
3. valor percentual de XGBoost;
4. percentil de XGBoost.

NoData é -9999 e nunca é tratado como risco zero. Compressão é sem perda;
overviews são calculadas por média, ignorando NoData. Cada COG é reaberto e
comparado integralmente à janela de entrada antes de salvar seu checkpoint.

A cobertura científica é a máscara dos GeoTIFFs. O limite cartográfico pode
diferir ligeiramente dessa máscara; não são descartados pixels científicos
por essa diferença. Polígonos visuais são recortados pelo limite quando há
interseção válida. A seleção individual usa o retângulo original do pixel.

## Retomada e publicação

Checkpoints locais em `incendio/resultados/risco_professor_v4` vinculam cada
setor aos hashes dos mapas, relatórios, limite e versão do contrato de importação.
Uma retomada confere o hash do COG e reutiliza os agregados locais por setor.
Para alterar regras de cálculo, incrementar a versão do contrato no importador.

O importador confere máscaras e valores em toda a área na primeira execução,
soma a cobertura dos setores e agregados, e recalcula três grupos diretamente
das entradas. A máscara atual possui **172.340.796 pixels**, distribuídos em
**208 setores** e **6.393 grupos**. Os COGs gerados totalizam aproximadamente
1,67 GiB; o maior setor tem menos de 15 MiB.

A geração usa staging; somente o produto auditado substitui o diretório ativo.
O produto anterior é movido para backup local antes da troca. Uma falha na
troca tenta restaurar esse backup. Não remover caches/backups para resolver
uma interrupção sem conferir o estado da geração.

O script npm `sync-products.mjs` inclui somente os setores de **2026** no
modo local, padrão também na Vercel. O GitHub fornece os 208 COGs; o build não
executa importação científica e não precisa das entradas brutas. O ano de
**2025 é sempre agregado**, mesmo se seus setores existirem localmente.

Para compilar sem rasters de nenhum ano, use `RISK_RASTER_MODE=aggregated`.
A origem externa opcional `RISK_RASTER_BASE_URL` aplica-se somente a 2026.
`deployment.json`, gerado separadamente do manifesto, registra a distribuição
de cada ano. O build inclui Risco v4/2025 agregado, Risco v4/2026 e Clima v1/2025.

Os códigos de treino e produtos v1/v2, suscetibilidade, INPE e Perigo foram
retirados da árvore atual. O exportador `exportar_clima_2025.py` utiliza somente
`risco_anual_v4/climate_geometry.py`, Rasterio e o grid climático ativo; não
depende da geometria dos antigos produtos de risco. O clima pronto permanece
versionado. Insumos e resultados históricos ignorados continuam locais e os
códigos removidos são recuperáveis pelo histórico/branches de arquivo.

A limpeza não reescreve o histórico Git. As cópias geradas não incluem produtos
antigos, mas os commits anteriores continuam fazendo parte da história do
repositório.

Os produtos observados de 2025 permanecem independentes. A sobreposição de
cicatrizes do inventário anterior inicia desativada no Risco de 2026 e exige
aviso temporal quando ativada. Não é a camada MapBiomas Fogo de 2026.
