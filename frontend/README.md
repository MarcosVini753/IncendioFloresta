# Frontend — Risco v6 e Clima de 2025

React + MapLibre + GeoTIFF.js. Abre no **Random Forest F30C de 2026**, sem clima,
com média dos percentis como resumo. 2025 também está disponível. Random Forest e XGBoost são selecionáveis localmente, com comparação dos
resultados no painel. A troca preserva câmera, seleção e resumo. O arquivo de
altitude não é uma camada da interface.

## Leitura do mapa

- Até zoom 8,5: grupos de 5 km. Nove resumos: média, moda, mediana, concentração
  >=90, P75, média por área, raridade local, raridade estadual e CDF do valor médio.
- A partir de 8,5: setores raster progressivos. O seletor de resumo é desativado,
  mas sua escolha é preservada para o retorno ao agregado.
- O clique no raster consulta sempre o pixel Float32 original, não uma overview.
  Mostra linha/coluna, centro, índice e probabilidade calibrada recebida.
- Percentil: escala 0–100 sem `%`, posição relativa entre os pixels do ano.
  Banda de valor: probabilidade calibrada RF ou escore XGBoost corrigido por
  amostragem, sem calibração. Ambos já percentuais, apresentados separadamente.
- Classes: [0,50), [50,70), [70,90), [90,95), [95,100]. Concentração tem escala
  própria contínua de 0–100% dos pixels válidos, não de chance de fogo.
- O painel mostra composição, contagens, fórmula, variáveis, memória de cálculo,
  precisão e proveniência. Quantis são exatos, sem interpolação. Moda mostra
  classe/proporção e sinaliza empate ou ausência de maioria absoluta.
- Comparação anual usa somente médias dos percentis, cada ano com seu próprio
  ranking. Não indica aumento absoluto do risco. Trocar ano preserva o resumo,
  limpa seleção e recria leitores para não misturar setores.
- Falha nas estatísticas adicionais preserva média/moda/concentração. Um resumo
  indisponível volta à média com aviso e opção de tentar novamente.

A cobertura v6 segue a máscara recebida sobre o Acre IBGE 2024. Os 22 municípios
simplificados recebidos também fornecem as divisas de referência, compartilhadas
com a aba Clima; trocar esse contorno não amplia dados observados nem sua grade.
NoData é ausência de estimativa, não risco zero.

## Executar e compilar

```bash
npm install
npm run dev
npm test
npm run test:sync
npm run build
npm run preview
```

`predev` e `prebuild` verificam/sincronizam os produtos canônicos em
`incendio/produtos/risco/v6/{2025,2026}` e `incendio/produtos/clima/v1/2025`.
São 222 setores de quatro bandas Float32 por ano, gerados dos GeoTIFFs completos.
O build nunca executa Python ou modelos. Public/dist são gerados e ignorados.
A sincronização valida os dois anos antes de substituir as cópias geradas.

Modos raster:

- `RISK_RASTER_MODE=local` (padrão): inclui setores versionados nos dois anos.
- `RISK_RASTER_MODE=aggregated`: exclui setores por escolha explícita.
- `RISK_RASTER_MODE=remote`, com `RISK_RASTER_BASE_URL=https://…/v6`:
  setores externos em `<base>/<ano>/sectors/…`; exige HTTP público e CORS.

O worker suporta HTTP Range. Sem Range, lê somente um setor de no máximo
1024² × 4 Float32, nunca o GeoTIFF completo do estado. Mantém quatro transferências
simultâneas, LRU de até 32 setores e teto de 128 MiB para blocos decodificados.
Pan/zoom cancela trabalhos obsoletos. Tiles Web Mercator são convertidos para a
grade EPSG:4326 antes da amostragem. As cores são aplicadas depois da leitura.
A exclusão de MapLibre do prebundle do Vite é preservada para WSL/Windows.

Links preservam ano, modelo, câmera e resumo. `model=xgboost` seleciona XGBoost;
valores desconhecidos selecionam Random Forest. `mode=compare` continua ignorado;
não há mapa de diferenças entre modelos nesta atualização.

## Clima e avaliações

Clima e cicatrizes de 2025 são produtos observados independentes, com calendário
diário preservado. As cicatrizes ficam inicialmente ocultas no risco; ativá-las
em 2026 mostra aviso temporal. Sua origem/cobertura não é a mesma da avaliação
MapBiomas Fogo de 30 m. O risco F30C não utiliza clima.

A avaliação mostra os mapas completos RandomForest_F30C e XGBoost_F30C de 2023–2025 contra
`30m_fogo`, recebidos do professor, sem substituir por métricas amostrais.
Não há avaliação observada de 2026 nem contagem de incêndios confirmados.

Veja [contratos e preparação](../incendio/PRODUTOS_WEB.md).
