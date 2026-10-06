# Frontend — Risco e Clima de 2025

O site abre em **Risco anual experimental — 2025**, com **Random Forest**
no cenário **Oeste–Leste**. Também oferece GradBoost, Regressão Logística,
Fuzzy k-NN e XGBoost. Os modelos e cenários Acre inteiro/regional podem ser
trocados sem novas requisições. Escores relativos em [0,1], exibidos como
0–100% com uma casa decimal no painel, nos popups e na legenda; não probabilidades
calibradas ou previsão operacional.

Treino 2007–2024; seis preditores; clima defasado. O mapa de 2025 usa clima
anual de 2024. O painel compara os cinco escores do cenário selecionado.

O painel **Como o modelo se saiu em 2025** acompanha o modelo e cenário
ativos. Mostra quantas das 39 células positivas do inventário aparecem nos
10% de células científicas com maiores escores, AUC-ROC e precisão média
(AP, calculada como `average_precision_score` e armazenada em `pr_auc`).
Os cortes de 1%, 5%, 10% e 20% podem ser expandidos. É o teste territorial
de 2025 fora do treino 2007–2024, anterior à agregação; permanece igual ao
selecionar uma célula ou mudar o zoom. CV balanceada e avaliações recebidas
de outros anos não são misturadas a estes resultados. O loader rejeita
métricas incompletas, inválidas ou incompatíveis com a cobertura.

O controle **Cicatrizes observadas · 2025**, ativo inicialmente no Risco,
mostra os 59 pixels classificados de todo o ano. A cor roxa distingue as
observações da escala do modelo. Marcadores no zoom estadual dão lugar
aos polígonos do raster a partir do zoom 8,5, sobre a grade original.
O clique mostra a data registrada e seleciona a célula de Risco
correspondente, quando disponível. A sobreposição tem estado independente
do filtro diário da aba Clima. Ela carrega apenas manifesto e cicatrizes;
falha de rede mantém o Risco disponível e permite tentar novamente.
As 39 células científicas positivas e os 59 pixels do raster são unidades
diferentes, não contagens de incêndios confirmados. O inventário é limitado.

Em zoom menor que 8,5 são 212 células de 0,28°. Ao aproximar, setores da
grade original são carregados pela viewport, com margem de um setor,
cancelamento de requisições obsoletas e cache LRU de 32 setores.

A aba **Clima e cicatrizes · 2025** possui 365 datas, inicialmente 25/08/2025.
Umidade e precipitação são observadas em 2025. Mínimo, média e máximo são
estatísticas espaciais, não extremos horários. A duração de acumulação da
precipitação não está documentada. Sem dado climático, a célula fica cinza.
Sem cicatriz em um dia não significa ausência comprovada de fogo.
Ao selecionar uma célula, sua série anual mostra as três estatísticas reais.

## Executar

Gere antes os produtos canônicos seguindo [PRODUTOS_WEB.md](../incendio/PRODUTOS_WEB.md).

```bash
cd frontend
npm install
npm run dev
npm test
npm run build
npm run preview
```

Predev/prebuild verificam ambas as origens antes de substituir as cópias
geradas em public/data/risk/v1/2025 e public/data/climate/v1/2025.
Não copiam os anos antigos nem alteram os arquivos de Perigo.
Postbuild exclui apenas a cópia gerada de Perigo em dist, pois Vite copia
public/ integralmente. Os arquivos locais originais ficam intactos.
O produto canônico é a única cópia versionada. A exclusão de MapLibre do
prebundle Vite permanece por compatibilidade WSL/Windows.

## Aceite

- Conferir os cinco modelos, os dois cenários e o painel de uma célula.
- Conferir a avaliação do par selecionado e os quatro cortes de prioridade.
- Ocultar/exibir cicatrizes anuais, clicar num marcador e num pixel na grade original.
- Conferir independência dos controles de cicatrizes no Risco e no Clima.
- Aproximar até a grade nativa, arrastar rapidamente e retornar à grade estadual.
- Conferir clima e cicatrizes em 01/01, 25/08 e 31/12/2025.
- Conferir ausência de Perigo, Alerta e INPE na interface.
- Verificar HTTP 200 dos manifestos, grade agregada, índice, setores e matrizes.
- Conferir ausência de erros da aplicação no console.

O site anterior foi preservado em archive/risk-2016-before-2025.

## Smoke de navegador

Com o preview em 127.0.0.1:4173, instale as dependências de teste no Python:

```bash
../incendio/.venv/bin/python -m pip install -r scripts/requirements-browser.txt
../incendio/.venv/bin/python -m playwright install chromium
../incendio/.venv/bin/python scripts/smoke-2025.py
```

O teste usa dados reais, troca os dez pares modelo/cenário, seleciona células,
verifica grade original, pan/zoom, extremos do calendário e série climática.
Confere os cliques nas cicatrizes nas duas resoluções, a recuperação de uma
falha HTTP da sobreposição e o layout de avaliação no celular.
Confere HTTP 200 de todos os setores e ausência de exceções JavaScript.
