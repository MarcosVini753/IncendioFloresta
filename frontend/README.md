# Frontend — Risco professor v2 e Clima de 2025

O site abre em Random Forest no cenário Todas + histórico de queimadas.
São quatro modelos (Random Forest, GradBoost, Regressão Logística e XGBoost)
e quatro cenários (Todas as células, Oeste–Leste, Amostra 1:19 e Todas +
histórico de queimadas). O Fuzzy não integra a v2.

## Como ler o mapa

A cor e o valor principal mostram o índice percentil estadual, de 0 a 100,
sem símbolo de porcentagem. Percentil 95 indica posição elevada no ranking,
não 95% de chance de incêndio. No clique, o escore aparece separadamente,
em escala percentual e com precisão adaptativa para valores pequenos.
Nenhuma das duas escalas é uma probabilidade calibrada ou previsão operacional.

Na malha agregada de 212 células, escores e percentis são médias das células
científicas, sem recalcular o ranking sobre a malha visual. No zoom 8,5,
entram setores da grade original de 307.410 células, com margem de um setor,
cancelamento de requisições e cache LRU de 32 setores. O painel compara os
quatro modelos do cenário selecionado. Trocas de modelo/cenário são locais.

Treino de 2007–2024 e clima de 2024, com interpolação bilinear. O cenário
histórico acrescenta somente informações de queimadas anteriores a 2025.
O cenário 1:19 usa a correção de amostragem do código recebido.

## Avaliação e observações

A avaliação de 2025 é recalculada no território completo, antes da agregação,
para o modelo/cenário selecionado. Exibe detecção no topo de 10%, AUC-ROC,
precisão média (AP) e outros cortes. O campo pr_auc foi calculado como AP.
Relatórios recebidos de 2017–2024 ficam em uma seção identificada separadamente;
não foram recalculados nesta entrega nem são apresentados como equivalentes
ao teste de 2025. O padrão Random Forest histórico decorre da seleção histórica
desse cenário, não da escolha do melhor resultado no próprio ano de teste.

Cicatrizes observadas · 2025 são uma sobreposição anual independente,
inicialmente ativa no Risco, com marcadores roxos e contornos ao aproximar.
O clique apresenta a data e a célula correspondente quando disponível.
Falhas de carregamento permitem tentar novamente sem derrubar o mapa.

As 39 células científicas positivas e os 59 pixels de cicatriz são unidades
espaciais diferentes; nenhuma contagem equivale a incêndios confirmados.
Ausência de registro não comprova ausência de fogo.

Clima e cicatrizes · 2025 mantém 365 dias, inicialmente 25/08/2025.
Mínimo, média e máximo climáticos são estatísticas espaciais, não extremos
horários. A duração de acumulação da chuva não está documentada.

## Executar

O produto canônico v2 deve estar completo; não há fallback silencioso para v1.
Consulte [PRODUTOS_WEB.md](../incendio/PRODUTOS_WEB.md).

~~~bash
cd frontend
npm install
npm run dev
npm run build
npm run preview
~~~

Predev/prebuild sincronizam somente risco/v2/2025 e clima/v1/2025.
Produtos gerados em public e dist não são versionados. A exclusão do MapLibre
do prebundle do Vite permanece. Perigo não é incluído no dist e seus arquivos
locais não são alterados.

## Conferência breve

Verificar os 16 pares, valores da célula nas duas resoluções, avaliação,
toggle de cicatrizes e extremos do calendário climático. O script
scripts/smoke-professor-v2.py realiza esse percurso com dados reais e limite
de execução; scripts/smoke-2025.py pertence à versão anterior arquivada.

A versão anterior está em archive/risk-2025-before-professor-v2.
