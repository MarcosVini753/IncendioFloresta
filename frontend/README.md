# Frontend — suscetibilidade experimental do Acre

Interface React + TypeScript + MapLibre para visualizar a suscetibilidade histórica
experimental e, de forma independente, os focos de calor reais do INPE.

Na branch `feature/historical-climate-scars-2015`, a aba **Clima e cicatrizes ·
2015** acrescenta 365 datas históricas. O seletor alterna entre umidade relativa
e precipitação; o slider muda o dia, e o toggle exibe cicatrizes observadas no
mesmo dia. Um clique na célula mostra mínimo, média espacial e máximo, além da
quantidade de pixels climáticos válidos. Setores sem cobertura ficam cinza.
Os marcadores vermelhos ajudam a localizar cicatrizes no zoom estadual; ao
aproximar, os polígonos mostram a área dos pixels classificados.

## Produto exibido

O frontend carrega e valida o manifesto e o GeoJSON gerados pelo pipeline científico.
A visualização estadual usa 212 células de aproximadamente `0,28°`, recortadas pelo
limite do Acre. Cada valor é a média das células científicas originais de cerca de
`893 × 598 m` contidas naquele setor.

Os quatro modelos disponíveis são:

- GradBoost, selecionado inicialmente pela melhor validação espacial registrada;
- Random Forest;
- Regressão logística;
- Fuzzy k-NN com `k=29`.

Todos produzem `relative_score` no intervalo `[0, 1]`. Esses escores não são
probabilidades calibradas nem devem orientar decisões operacionais. Perigo diário e
Alerta não são exibidos nesta branch.

## Sincronização do produto

A única cópia versionada fica em:

```text
incendio/produtos/suscetibilidade/v1/
```

Os scripts `predev` e `prebuild` copiam automaticamente esse diretório para
`frontend/public/data/susceptibility/`. A cópia pública é gerada e ignorada pelo Git.
Na branch climática, eles também copiam `incendio/produtos/clima/` para
`frontend/public/data/climate/`.

## Executar localmente

```bash
cd frontend
npm install
npm run dev
```

Para validar a compilação e confirmar que o produto entrou em `dist`:

```bash
npm run build
find dist/data/susceptibility -type f
find dist/data/climate/v1/2015 -type f
```

Na branch `experiment/native-susceptibility-grid`, execute também:

```bash
npm test
```

Essa branch mantém a camada agregada abaixo do zoom `8,5`. A partir desse nível,
carrega os setores que intersectam a viewport e uma margem de pré-busca, cancela
requisições superadas por novos movimentos e mantém um cache LRU de até 32 setores.
Somente as células dos setores visíveis entram na fonte ativa do MapLibre; ao afastar,
o mapa retorna automaticamente à representação agregada. Não há deploy dedicado para
o experimento nesta etapa.

## Focos de calor do INPE

O conversor escolhe o CSV diário mais recente e atualiza o GeoJSON versionado:

```bash
python3 scripts/prepare_inpe_hotspots.py
```

Os focos são detecções orbitais, não incêndios confirmados. Data de referência,
toggle, clustering e popup permanecem independentes do modelo de suscetibilidade.
Os focos de 2026 não aparecem na aba histórica de clima de 2015.

## Verificar a seção de 2015

1. Abra **Clima e cicatrizes · 2015** e escolha 01/01, 25/08 e 31/12 no slider.
2. Alterne umidade e precipitação; consulte uma célula e seus três valores espaciais.
3. Ligue e desligue as cicatrizes. Dias sem registro exibem contagem zero.
4. Confirme HTTP 200 para `manifest.json`, `grid.geojson`, `boundary.geojson`,
   `humidity.json`, `precipitation.json` e `scars.geojson` em `/data/climate/v1/2015/`.

## Aceite manual

1. O mapa abre com GradBoost e permite trocar instantaneamente entre quatro modelos.
2. Não há controles ativos de Perigo ou Alerta.
3. Uma célula selecionada mostra os quatro escores, a média e a contagem de fontes.
4. A legenda permanece fixa de 0 a 1.
5. Os focos INPE podem ser ocultados, agrupados e inspecionados sem alterar o produto.
6. Manifesto, GeoJSON e limite respondem com HTTP 200 e o console não apresenta erros.

Ao conectar o repositório à Vercel, use `frontend` como **Root Directory**.
