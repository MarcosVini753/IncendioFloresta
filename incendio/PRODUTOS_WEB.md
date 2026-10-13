# Produtos web — entrega do professor v2

## Ambiente e geração

O código recebido foi isolado em risco_anual_v2, preservando os pipelines
anteriores e a pasta original entrega_professor_v2. Dados brutos, SQLite,
Parquet, Joblib, imagens, ambientes e checkpoints ficam locais e ignorados.
Somente código, configuração, parâmetros portáveis e produtos web são versionados.

Na raiz, preparar uma vez um ambiente Python 3.11:

~~~bash
uv venv --python 3.11 incendio/risco_anual_v2/.venv
uv pip install --python incendio/risco_anual_v2/.venv/bin/python -r incendio/risco_anual_v2/requirements.txt
incendio/risco_anual_v2/.venv/bin/python incendio/exportar_risco_professor_v2.py
incendio/risco_anual_v2/.venv/bin/python incendio/exportar_risco_professor_v2.py --validate-only
~~~

XGBoost 3.2.0 é executado em CPU. Rasterio 1.4.4 é usado porque 1.5.2 exige
Python 3.12 ou superior. Versões efetivas e backend são registrados.
A configuração contém caminhos relativos para os insumos locais; não usar
nomes de arquivo para deduzir o período das bandas.

## Protocolo

- Previsão anual experimental de 2025, treino de 2007–2024, semente 42.
- Seis preditores: vegetação categórica, distâncias à estrada e à água,
  altitude, umidade média anual e precipitação acumulada anual.
- Clima defasado em um ano, interpolado por método bilinear: mapa de 2025 usa 2024.
- Quatro modelos: Random Forest, GradBoost, Regressão Logística e XGBoost.
- Cenários: todos, todos_regional, razao_1x19 e todos_historico.
- Regional usa o corte UTM científico x < 337100 m para Oeste.
- Histórico acrescenta anos desde última queima, histórico decaído e
  queima no ano anterior, sem acessar cicatrizes do ano-alvo.
- Regional e histórico reutilizam os parâmetros de todos, como no pacote recebido.
- Parâmetros próprios de todos e razao_1x19 são conferidos por impressão
  da tabela, preditores, espaço de busca, amostragem e protocolo. Divergências
  científicas refazem somente o ajuste afetado, com validação por ano no mapa inteiro.
- O escore de 1:19 recebe a correção de amostragem do professor. Essa correção
  não demonstra calibração; manter a semântica relative_score.

A paisagem mantém insumos de 2003–2013. A divisão regional não é administrativa.
O produto não é previsão operacional nem reprodução integral da tese.

## Contrato e auditoria

O produto ativo usa contrato 2.0 em produtos/risco/v2/2025, com manifesto e
malha agregada, além de manifesto, índice e setores da grade científica.
Cada célula contém 16 propriedades score_<cenario>_<modelo> em [0,1] e
16 percentile_<cenario>_<modelo> em [0,100].

Percentis são calculados sobre as 307.410 células estaduais de cada par,
após juntar as regiões, com rank médio nos empates, conforme o código recebido.
Não são probabilidades nem percentuais de área queimada.

A malha visual de 0,28° contém 212 células AC-RxxCxx recortadas pelo Acre.
Agrega por média aritmética tanto escores quanto percentis científicos,
preservados para consulta. A cor usa o **máximo percentil nativo** de cada
setor: 16 propriedades adicionais `max_percentile_<cenario>_<modelo>`.
O manifesto distingue `aggregation: mean` dos dados e `color_aggregation: max`,
com `color_property_prefix: max_`, da visualização. Isso destaca a célula-fonte
de maior risco, não indica que todo o setor tenha aquele risco e não calcula
um novo ranking visual. A grade original mantém IDs AC-Y<Y>-X<X>,
cantos reais em UTM 19S reprojetados e dimensões aproximadas de 893 × 598 m.

A geração confere domínios, cobertura, IDs únicos, médias e máximos agregados/nativos.
Somente as 16 combinações completas podem ser publicadas. Arquivos são
gerados em staging e auditados antes do rename para o diretório canônico.
Uma versão anterior do produto fica em backup local durante a substituição.
Uma interrupção entre renames pode exigir restaurar esse backup; não removê-lo
nem reaproveitar staging sem verificar o estado.

Para atualizar somente as cores de um produto v2 já publicado, sem treinar
modelos nem modificar os setores nativos:

~~~bash
incendio/risco_anual_v2/.venv/bin/python incendio/exportar_risco_professor_v2.py --refresh-display-maxima
~~~

O comando confere todos os setores antes de gravar o GeoJSON e o manifesto
agregados, registra `color_updated_at` e preserva as médias, previsões e métricas.

## Retomada e avaliação

O cache em resultados/risco_professor_v2 guarda a base e checkpoints por
cenário/modelo/escopo, com ordem das células, impressão da tabela, hashes,
preditores, períodos, parâmetros, correção, versões e backend.
Reexecutar o mesmo comando retoma previsões e seleções já concluídas.
Uma seleção interrompida antes de finalizar seus candidatos é refeita.

A avaliação de 2025 é recalculada nas células científicas; o manifesto compara
as métricas com as recebidas e registra diferenças. Não copiar métricas antigas
para previsões novas. Relatórios de 2017–2024 são preservados como evidência
recebida separada; não foram reprocessados nem usados para selecionar pelo teste
de 2025. O campo pr_auc corresponde à precisão média (AP).

O inventário tem 39 células científicas positivas em 2025. Os 59 pixels
de cicatrizes do raster representam outra unidade, não incêndios confirmados.

## Observações e entrega

Os oito insumos da nova pasta tiveram hashes idênticos aos da versão anterior.
Clima e cicatrizes permanecem em produtos/clima/v1/2025: 365 dias, médias
espaciais ponderadas e extremos espaciais. Se os hashes mudarem, o exportador
regenera o produto observado antes da publicação. Não afirmar chuva de 24 horas.

A branch archive/risk-2025-before-professor-v2 preserva o site anterior.
O pipeline legado e o produto risco/v1 continuam disponíveis para reprodução,
mas só v2 e clima ativo são sincronizados para o novo site. Não alterar Perigo.

O processamento usa a sessão tmux risk-professor-v2 e export.log no cache.
A finalização usa risk-professor-v2-delivery, delivery.log e delivery.json.
Ela só integra e envia a main depois da auditoria, builds, HTTP e conferência
breve do navegador. Se a main ou a cópia preparada mudarem durante o cálculo,
a integração para sem sobrescrever alterações concorrentes.
