# Frontend — Risco e Clima de 2025

O site abre em **Risco anual experimental — 2025**, com **Random Forest**
no cenário **Oeste–Leste**. Também oferece GradBoost, Regressão Logística,
Fuzzy k-NN e XGBoost. Os modelos e cenários Acre inteiro/regional podem ser
trocados sem novas requisições. Escores relativos em [0,1], não probabilidades
calibradas ou previsão operacional.

Treino 2007–2024; seis preditores; clima defasado. O mapa de 2025 usa clima
anual de 2024. O painel compara os cinco escores do cenário selecionado.

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
Confere HTTP 200 de todos os setores e ausência de exceções JavaScript.
