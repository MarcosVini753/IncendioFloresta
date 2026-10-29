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
- `aggregation-stats.json`: produto derivado, contrato próprio 1.0, resumos
  exatos e metodologias por grupo/modelo; não altera os campos do GeoJSON.
- `sectors/AC-V4-RxxxCxxx.tif`: COGs gerados e versionados nos dois anos.

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

### Gerar os resumos selecionáveis

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
incendio/.venv/bin/python incendio/risco_anual_v4/exportar_resumos.py
```

`--year 2025` ou `--year 2026` restringe a geração. O exportador lê os COGs
versionados, sem treino, previsão ou dependência dos CSVs exploratórios locais.
Usa aproximadamente 1,3 GiB temporários em disco por ano para os percentis,
com leitura por setor e partição por grupo para os quantis. Remove os arquivos
temporários ao concluir ou interromper por exceção e publica o JSON atomicamente.

Mediana/P75 usam a posição `ceil(q*n)` e não são aproximações de histograma.
Área usa cantos geodésicos WGS84. Classes ocupadas recebem pesos iguais na
raridade local; raridade estadual usa inversos das frequências daquele ano e
modelo. A CDF da banda 1 conta valores menores ou iguais à média do grupo e tem
outra convenção de empates que o histograma do professor. Classes vazias ficam
com média `null` e são excluídas das ponderações.

Os arquivos registram hashes de manifesto, grade, índice e todos os COGs,
identidade do produto de origem e hash do exportador executado. A auditoria
confere contagens/médias/proporções e relê janelas independentes de grupos,
incluindo grupo pequeno, caso do relatório e fronteira entre setores.
Uma reimportação dos mapas requer regenerar os resumos antes do build.

Os resumos dos dois anos são versionados e sincronizados automaticamente;
o build não executa Python. A validação npm rejeita arquivo ausente ou obsoleto
antes de substituir as cópias geradas. COGs, manifesto científico e GeoJSON
original permanecem inalterados.

Verificação focada dos cálculos:

```bash
incendio/.venv/bin/python -m unittest incendio.risco_anual_v4.test_resumos
cd frontend
npm test
npm run test:sync
npm run build
```

Checkpoints locais em `incendio/resultados/risco_professor_v4` vinculam cada
setor aos hashes dos mapas, relatórios, limite e versão do contrato de importação.
Uma retomada confere o hash do COG e reutiliza os agregados locais por setor.
Para alterar regras de cálculo, incrementar a versão do contrato no importador.

O importador confere máscaras e valores em toda a área na primeira execução,
soma a cobertura dos setores e agregados, e recalcula três grupos diretamente
das entradas. A máscara atual possui **172.340.796 pixels**, distribuídos em
**208 setores** e **6.393 grupos** por ano. Os 416 COGs dos dois anos totalizam
aproximadamente 3,57 GB (3,33 GiB); o maior setor tem menos de 15 MiB.

A geração usa staging; somente o produto auditado substitui o diretório ativo.
O produto anterior é movido para backup local antes da troca. Uma falha na
troca tenta restaurar esse backup. Não remover caches/backups para resolver
uma interrupção sem conferir o estado da geração.

O script npm `sync-products.mjs` inclui os setores de **2025 e 2026** no
modo local, padrão também na Vercel. O GitHub fornece os 416 COGs; o build não
executa importação científica e não precisa das entradas brutas.

Para compilar sem rasters de nenhum ano, use `RISK_RASTER_MODE=aggregated`.
A origem externa opcional `RISK_RASTER_BASE_URL` aplica-se aos dois anos,
em subdiretórios `2025/` e `2026/`.
`deployment.json`, gerado separadamente do manifesto, registra a distribuição
de cada ano. O build inclui Risco v4/2025 e v4/2026 nas duas resoluções e
Clima v1/2025.

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
