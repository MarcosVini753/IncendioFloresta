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
Nenhum commit novo, push ou deploy foi executado nesta substituição.
