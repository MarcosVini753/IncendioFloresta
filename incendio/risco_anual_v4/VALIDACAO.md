# Conferência da integração v4 — 19/10/2026

## Publicação dos setores de 2025 — 27/10/2026

- Incluídos os 208 COGs de 2025 já existentes, sem treinamento ou recálculo
  de previsões. Cada SHA-256 corresponde ao checkpoint auditado do importador.
- Conferidos IDs, arquivos/tamanhos do índice, janelas, geotransformação,
  EPSG:4326, quatro bandas Float32 e NoData -9999 de todos os setores de 2025.
  Cobertura: 172.340.796 pixels válidos; 1.784.951.449 bytes.
- O modo local padrão da Vercel inclui 416 setores, 208 por ano. Os modos
  agregado e remoto também se aplicam aos dois anos.
- Oito testes de sincronização aprovados, incluindo setor de 2025 ausente
  sem substituir as cópias geradas, publicação remota por ano e retorno ao
  modo agregado sem remover os dados canônicos.
- TypeScript e build com `VERCEL=1` aprovados. Conferidos os 416 COGs no
  `dist` por nomes e tamanhos do índice, metadados idênticos aos canônicos e
  `deployment.json` local nos dois anos. Produtos históricos fora do build.

## Ampliação para 2025 e seletor anual

- Importados os GeoTIFFs finais próprios de 2025, sem treino ou previsão local:
  treino 2016–2024, clima de 2024 e calibração recebida correspondente ao ano.
- Auditoria integral das máscaras e dos domínios, COGs sem perda e recálculo
  independente de três grupos aprovados pelo importador.
- 2025: 172.340.796 pixels, 6.393 grupos de 5 km e 208 setores. IDs únicos,
  contagens e domínios conferidos; valores anuais distintos dos de 2026.
- TypeScript e build aprovados; os quatro arquivos públicos e os 208 setores
  de cada ano foram conferidos no dist contra as cópias canônicas.
- A interface inicia em 2026. A troca limpa a seleção anterior e recria os
  leitores raster com URLs do ano escolhido, mantendo o modelo selecionado.
- Chrome local: troca 2026 → 2025 → 2026, seleção agregada e pixel original
  dos dois modelos aprovadas. O pixel linha 7.492/coluna 13.670 foi comparado
  com os TIFFs de cada ano; nenhum erro JavaScript não tratado.
- HTTP 200/tamanhos dos 416 setores conferidos e leitura parcial HTTP 206
  disponível. Aviso temporal das cicatrizes apenas em 2026 e extremos do
  calendário climático preservados. A conferência aguarda o carregamento do
  estilo/worker antes de clicar, evitando o clique prematuro do primeiro ensaio.

## Conferência inicial de 2026

Entrada: os dois GeoTIFFs finais de 2026, Random Forest e XGBoost AB30C com
clima suavizado, treinados com MapBiomas Fogo. Não houve novo treinamento,
previsão, calibração ou cálculo de percentis estaduais.

## Produto científico

- 172.340.796 pixels válidos; máscaras idênticas nos dois modelos e bandas.
- Todos os valores válidos finitos no domínio [0,100]; NoData preservado.
- 208 setores COG de quatro bandas, reabertos e comparados integralmente
  aos Float32 de entrada na primeira geração, sem perda de valores.
- 6.393 grupos de 5 km; cobertura somada idêntica aos setores.
- Médias e proporções de três grupos recalculadas diretamente dos GeoTIFFs.
- Reexecução concluída reutilizando os 208 COGs por checkpoint, com hashes
  de setores e de estatísticas locais; produto anterior guardado em backup.
- Hash do importador no manifesto conferido contra o código versionado.

## Frontend e arquivos públicos

- TypeScript e build de produção aprovados. O Vite conserva o aviso de bundle
  principal acima de 500 kB; isso não impediu a compilação ou a navegação.
- Manifesto, índice, grade e limite no dist iguais à cópia canônica.
- HTTP 200 e tamanho de arquivo conferidos para os 208 setores.
- Leitura parcial HTTP 206 verificada no preview.
- Leitura integral HTTP 200 testada em três setores pequenos: valores
  Float32 idênticos aos originais em dois pixels de fronteira de setor;
  um pixel sem dados retornou null. Cada setor foi baixado uma vez.
- Manifesto de ano inválido rejeitado pela interface; nova tentativa carregou
  o produto válido. Falha HTTP 503 no setor foi reportada e a consulta seguinte
  recuperou os valores do pixel original.
- Chrome local: troca dos dois modelos, seleção agregada, distribuição de
  classes, transição raster, clique, pan rápido e retorno ao zoom estadual.
- Render da resolução original de aproximadamente 30 m conferido em zoom
  próximo, com consulta de pixel e sem erros JavaScript não tratados.
- Pixel de linha 7492 e coluna 13670 consultado no navegador e comparado aos
  dois GeoTIFFs: percentis e valores exibidos correspondem aos originais,
  considerando a precisão de apresentação.
- Cicatrizes de 2025 inicialmente ocultas e aviso temporal ao ativá-las;
  calendário climático nos extremos de 2025 e retorno ao Risco preservando
  a escolha do modelo.
- Nenhum erro JavaScript não tratado na conferência breve do navegador.
- Dependência transitiva source-map-js atualizada para a correção compatível;
  a instalação npm terminou com zero vulnerabilidades reportadas.

Não foi executada uma suíte extensa de automação de navegador nem o pipeline
científico de treino da entrega. A avaliação de 2026 permanece indisponível;
as tabelas históricas exibidas são as recebidas do professor.

Para repetir a conferência breve, com o build servido por npm run preview:

~~~bash
incendio/.venv/bin/python frontend/scripts/smoke-professor-v4.py --url http://127.0.0.1:4173
~~~

O script usa Playwright/Chromium e Rasterio locais. Na publicação atual os
setores de 2025 e 2026 são versionados: 208 por ano. O build padrão inclui
30 m nos dois anos, além das respectivas malhas agregadas.
