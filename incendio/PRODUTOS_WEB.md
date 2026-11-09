# Produtos web — Risco v6 de 2025 e 2026

## Origem e semântica

Importação dos GeoTIFFs `risco_30m_<RandomForest|XGBoost>_F30C_<ano>.tif` em
`entrega_professor_v6/mapas_geotiff/mapas_geotiff/`. Relatórios em
`entrega_professor_v6/2_resultados/`. São resultados recebidos: nenhum treino,
previsão, correção de prior ou calibração é executado novamente.

Cenário F30C: 11 preditores de uso do solo, distâncias até água e estrada,
altitude, histórico de fogo de 30 m, desmatamento e frações de agropecuária.
**Sem clima.** O ano de uso do solo é o anterior ao mapa. Treino 2016–2024 para
2025 e 2016–2025 para 2026, semente 42, amostragem 1:19 com correção recebida.
O manifesto registra os coeficientes de Platt temporal do Random Forest.
O XGBoost tem correção de amostragem recebida e não tem calibração temporal.

- Banda 1 original: probabilidade anual calibrada RF ou escore XGBoost não
  calibrado, ambos em escala percentual. Não multiplicar
  novamente por 100. Calibração não garante frequência correta em anos atípicos.
- Banda 2: índice percentil estadual recebido em Float32, entre 0 e 100. Não é
  uma probabilidade e não recebe `%`. Não recalcular o ranking para a viewport.
- NoData −9999: excluído; zero continua válido. Ambas as bandas têm a mesma máscara.

A máscara recebida foi ampliada para o Acre do IBGE 2024: **185.661.783 pixels**.
O contorno web é a dissolução dos 22 municípios simplificados recebidos. Ele é
referência cartográfica, não substitui a máscara dos rasters. Lacunas de cobertura
continuam sem estimativa. Não são preenchidas por vizinhança nem por risco zero.

## Contrato 6.0 e publicação

Cada `incendio/produtos/risco/v6/<ano>/` contém:

- `manifest.json`: cenário F30C, dois modelos, ausência de clima, treino, calibração,
  território, hashes das fontes e avaliações históricas `30m_fogo`.
- `grid.geojson`: 6.875 grupos UTM 19S de 5 km; geometria EPSG:4326 e IDs estáveis
  `AC-5KM-E…N…`. Centro representativo é a média dos centros dos pixels válidos.
- `boundary.geojson`: contorno derivado dos municípios IBGE 2024 recebidos.
- `index.json`: grade original 27.341 × 14.942, EPSG:4326, setores alinhados,
  janelas, bboxes, bytes, contagens e quatro bandas na ordem valor/percentil RF, valor/percentil XGBoost.
- `sectors/AC-V6-RxxxCxxx.tif`: 222 COGs de até 1024², quatro bandas Float32,
  sem perdas e com overviews por média. Os COGs inteiros arredondados recebidos
  não são usados para preparar esses setores.
- `aggregation-stats.json`: contrato derivado 1.0,
  `product: risk_v6_aggregation_stats`, vinculado ao ano, identidade e hashes
  do manifesto, grade, índice, setores e exportador.

Os campos científicos são `value_random_forest`, `percentile_random_forest`
e os campos equivalentes `value_xgboost`, `percentile_xgboost`, com cinco
proporções `share_<modelo>_<classe>` por modelo. A máscara define os
pixels participantes. Grupos são definidos pelo centro do pixel reprojetado
para EPSG:31979 e floor(X/5000), floor(Y/5000). O recorte visual não altera os pesos.

## Nove resumos, sem alterar as previsões

Média, moda e concentração usam média/proporções do GeoJSON. O produto derivado
acrescenta mediana/P75 exatos, média por área geodésica WGS84, médias por classe,
ponderações por raridade local/estadual e CDF empírica estadual da média da banda 1.

Quantis: inversa da CDF empírica, posição ceil(q*n), sem interpolação. Moda:
empate pela classe mais baixa. Concentração: fração com índice >=90. Frequências
estaduais são calculadas novamente para cada ano, sobre a cobertura v6 inteira.
CDF: contagem exata de valores da banda 1 <= média do grupo, dividida por N.
Não confundir com a média dos percentis nem com ranking entre grupos.

O exportador lê resolução original por setores, acumula Float64 e usa arquivo
memmap temporário para quantis com RAM limitada. Os campos originais não mudam.
Ele audita médias, classes, cobertura e quantis por releitura independente.
Arquivos são substituídos por rename após auditoria; checkpoints de importação
são vinculados aos hashes das entradas, código e referência territorial.

## Avaliações e observações

Avaliações publicadas: RandomForest_F30C e XGBoost_F30C, mapas completos de 2023–2025,
nível `30m_fogo`, fornecidas pelo professor. Não misturar esses resultados
com validação amostral/rolante nem com rótulos MODIS. Não há avaliação observada
para 2026. Pixels queimados não são contagens de incêndios confirmados.

Clima/cicatrizes de 2025 permanecem no contrato anterior e com sua fonte/cobertura
originais. A sobreposição em 2026 possui aviso de diferença temporal. O risco v6
não usa o clima mostrado nessa aba. Os GeoTIFFs XGBoost F30C de 2023–2026 já
estão disponíveis na pasta de entrada, junto dos mapas Random Forest. Os dois modelos de 2025/2026 foram integrados ao contrato, aos setores e aos
resumos. A seleção muda mapa, painel, explicações e avaliações históricas, sem
novas previsões. Cada modelo/ano tem frequências e CDF estaduais próprias.

O `altitude_acre_ibge2024.tif` é um insumo local, não uma camada publicada.
O arquivo recebido tem CRS EPSG:4674 e dimensões 27.324 × 14.964, diferentes dos
mapas de risco EPSG:4326 com 27.341 × 14.942 pixels. Os metadados não declaram
unidade vertical nem NoData. Seu uso na visualização foi adiado até validar esses
aspectos e a correspondência espacial. Não associar os arquivos por linha/coluna
nem presumir que esse GeoTIFF seja exatamente o insumo de altitude usado no treino.

Após a reorganização dos arquivos recebidos, mudou somente o caminho padrão
`--source-root` do importador. Os produtos existentes preservam o hash do código
executado na geração original; não houve recálculo por causa dessa mudança de caminho.

## Distribuição e histórico

O pacote recebido, rasters completos, SQLite, caches e checkpoints ficam ignorados.
Os produtos web e setores são versionados. A sincronização npm inclui somente
risco v6 de 2025/2026 e clima de 2025. A branch de arquivo preserva a v4; não há
reescrita do histórico Git nem exclusão dos insumos locais.
