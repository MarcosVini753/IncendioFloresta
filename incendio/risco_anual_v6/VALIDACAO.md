# Validação da importação v6 — 04/11/2026

Resultados importados, sem treinamento, previsão, correção de prior ou calibração
executados localmente. Apenas preparação geográfica e estatística dos resultados.

| Ano | Pixels válidos | Grupos de 5 km | Setores de duas bandas Float32 |
| --- | ---: | ---: | ---: |
| 2025 | 185.661.783 | 6.875 | 222 |
| 2026 | 185.661.783 | 6.875 | 222 |

O importador percorreu integralmente as duas bandas, conferiu máscaras e domínio
[0,100] e comparou todos os valores de cada COG gerado com a janela original.
Três grupos por ano tiveram médias e classes recalculadas por outra leitura.
O exportador dos resumos conferiu cobertura, médias e composição de todos os
grupos, além de quantis por releitura independente em grupos pequenos e grupos
atravessados por setores. Os IDs auditados estão no JSON derivado de cada ano.

Exemplo RF/2026, `AC-5KM-E105N1773`, com 28.560 pixels:

| Método | Resultado |
| --- | ---: |
| Média dos percentis | 86,98490649 |
| Moda | Muito alto — 49,32773109% |
| Mediana | 94,470703125 |
| P75 | 98,50530243 |
| Concentração >=90 | 58,44187675% |
| Média por área | 86,98476127 |
| Raridade local | 83,87652609 |
| Raridade estadual | 93,66108360 |
| CDF estadual do valor médio | 98,28536334 |

Esses valores são da v6; não substituem os números históricos dos estudos v4.

Verificações concluídas:

- Cinco testes Python: quantis, grupos pequenos, raridade, NoData/zero,
  máscaras incompatíveis, domínio e COG sem perda de precisão.
- 25 testes Vitest: contratos, dois anos, resumos, proveniência, HTTP,
  setores de duas bandas e referências municipais.
- Nove testes Node de sincronização, incluindo arquivos ausentes, estatísticas
  desatualizadas, modo local/externo/agregado e preservação das cópias anteriores
  quando o preflight falha.
- TypeScript e `npm run build`, incluindo o ciclo prebuild/postbuild.
- 454 arquivos do risco retornaram HTTP 200 na prévia local: dez arquivos
  de metadados/grades/resumos e 444 setores, com tamanhos conferidos.
- Manifestos, grades, índices e resumos no dist são idênticos aos canônicos.
  Risco v4 ausente de public/dist; Clima de 2025 presente e seus produtos
  canônicos sem alterações.
- Chromium: nove métodos, comparação anual pela média, troca de ano,
  persistência do resumo, links antigos com XGBoost/comparação ignorados,
  Clima, aviso temporal das cicatrizes e transição para o raster de 30 m.
- Faixa norte de 2025 consultável; pan rápido e retorno ao agregado preservando
  P75; abertura padrão em 2026/média; tela de 390 px sem overflow horizontal.
- Consulta nativa com HTTP Range e com resposta integral HTTP 200 de um setor:
  pixel Y11608/X19431 de 2026 igual ao GeoTIFF original, probabilidade
  2,1333231925964355% e índice 95,56269836425781. Nenhum erro JavaScript não tratado.

Os setores somam 1.755.407.302 bytes. GeoTIFFs recebidos, caches e checkpoints
permanecem locais e ignorados. A v4 foi preservada na branch
`archive/risk-v4-before-professor-v6` e seus produtos locais foram movidos para
`incendio/resultados/risco_professor_v4/archived-web-products-before-v6`.
Na preparação inicial não houve commit, push ou deploy automático. Os commits
locais foram solicitados posteriormente; isso não publica o site.

## Atualizações dos arquivos recebidos

O caminho padrão de entrada foi atualizado para
`entrega_professor_v6/mapas_geotiff/mapas_geotiff`. A alteração é de localização,
sem mudança nas fórmulas ou nos produtos gerados; seus hashes registram a versão
do importador usada originalmente.

Os mapas XGBoost F30C de 2023–2026 foram recebidos posteriormente. Sua
integração de 2025/2026 está registrada na seção a seguir; 2023/2024 permanecem
somente como fontes locais e avaliações históricas.
O GeoTIFF de altitude fica fora da visualização até validar suas unidades,
NoData e correspondência com a grade científica. Não foi adicionado como camada.


## Integração XGBoost — 09/11/2026

Os produtos ativos de 2025/2026 passam a conter Random Forest e XGBoost F30C,
com 185.661.783 pixels por modelo/ano, 6.875 grupos e 222 setores por ano.
Cada COG tem quatro bandas Float32: valor/percentil RF, valor/percentil XGBoost.
As máscaras e valores foram comparados integralmente com os dois GeoTIFFs
originais, sem reexecutar modelos nem reaplicar a correção de prior ou calibração.
Os valores e os nove resumos RF foram comparados aos produtos anteriores em
todos os grupos dos dois anos e permaneceram idênticos.

Auditoria independente de XGBoost no grupo AC-5KM-E105N1773 (28.560 pixels),
diretamente dos GeoTIFFs originais:

| Ano | Média dos percentis | Mediana | P75 | Concentração >=90 |
| --- | ---: | ---: | ---: | ---: |
| 2025 | 87,58593042 | 94,31383514 | 98,58039856 | 58,83053221% |
| 2026 | 87,47408115 | 95,07712555 | 98,95400238 | 58,66596639% |

O XGBoost é identificado como escore corrigido por amostragem, sem calibração
temporal. O Random Forest continua padrão, com calibração temporal recebida.
Cada modelo tem suas próprias estatísticas estaduais, painel e avaliação.
A altitude continua fora da visualização e os produtos de Clima não mudaram.


Validação desta integração: cinco testes Python, 26 testes Vitest, nove testes
Node de sincronização, TypeScript e build aprovados. Os 454 arquivos do risco
retornaram HTTP 200; os quatro valores de cada pixel consultado conferiram com
os GeoTIFFs originais em 2025/2026, inclusive com resposta HTTP 200 de um setor
inteiro sem Range. Chromium conferiu dois modelos × nove resumos, preservação
da seleção, troca local sem requisições JSON adicionais, comparação anual pela
média, links e consulta nativa. Nenhum erro JavaScript não tratado foi observado.
Os setores dos dois anos somam 4.296.060.793 bytes; o maior tem 15.378.968 bytes,
abaixo do limite de leitura integral de 32 MiB do worker. Os produtos canônicos
de Clima não foram modificados. Não houve commit, push ou deploy automático
nesta integração.
