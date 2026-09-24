# Frontend — suscetibilidade e perigo histórico do Acre

Interface React + TypeScript + MapLibre para visualizar a suscetibilidade experimental,
o perigo diário reconstituído para 2015 e, de forma independente, focos reais do INPE.

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
probabilidades calibradas nem devem orientar decisões operacionais. O modo Perigo é
uma reconstituição histórica, não uma previsão atual. Alerta permanece indisponível.
O manifesto anual também identifica os 44 preditores, as 196.455 amostras de treino
e a busca exata `NearestNeighbors` usada pelo Fuzzy k-NN; o loader rejeita produto
sem essa proveniência.

No Perigo, o slider percorre exatamente os 365 dias de 2015 e começa em 25/08/2015.
As quatro matrizes anuais são carregadas na entrada do modo; depois disso, data e
modelo mudam localmente. A série exibe a célula selecionada ou a média estadual.

## Sincronização do produto

A única cópia versionada fica em:

```text
incendio/produtos/suscetibilidade/v1/
incendio/produtos/perigo/v1/2015/
```

Os scripts `predev` e `prebuild` copiam automaticamente ambos os produtos para
`frontend/public/data/{susceptibility,danger}/`. As cópias são geradas e ignoradas.
Enquanto os checkpoints Fuzzy k-NN ainda estão sendo calculados, o produto de Perigo
canônico não existe: `npm run dev` e `npm run build` continuam funcionando para
Suscetibilidade, e o modo histórico informa que seus arquivos ainda não estão
disponíveis. Depois que o exportador terminar, reinicie o dev server ou execute
`node scripts/sync-scientific-products.mjs` dentro de `frontend` para copiar o produto.

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
find dist/data/danger -type f
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

## Aceite manual

1. O mapa abre com GradBoost e permite trocar instantaneamente entre quatro modelos.
2. Perigo histórico abre em 25/08/2015, tem 365 posições e nunca ativa a grade nativa.
3. Uma célula selecionada mostra os quatro escores, a média e a contagem de fontes.
4. A legenda permanece fixa de 0 a 1.
5. Os focos INPE podem ser ocultados, agrupados e inspecionados sem alterar o produto.
6. Manifesto, GeoJSON e limite respondem com HTTP 200 e o console não apresenta erros.
7. No Perigo, focos iniciam ocultos; ao ativá-los, as duas datas e o aviso temporal aparecem.

Ao conectar o repositório à Vercel, use `frontend` como **Root Directory**.
