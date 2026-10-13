# Incêndios Florestais — Acre

Aplicação React + MapLibre para explorar resultados de modelos e observações de 2025.

- Risco anual experimental da entrega do professor v2: quatro modelos e quatro cenários.
- Clima diário e cicatrizes observadas de 2025: calendário de 365 datas.
- Padrão inicial: Random Forest com histórico de queimadas.
- Mapa colorido pelo índice percentil de 0 a 100: cada célula grande usa o maior percentil entre suas células menores; médias continuam disponíveis no clique.

Percentil é posição relativa no ranking, não porcentagem de chance de incêndio.
Os escores também não são probabilidades calibradas. Treino de 2007–2024, clima
de 2024 e, no cenário com histórico, apenas queimadas anteriores a 2025.
O clima e as cicatrizes exibidos são observações de 2025, com cobertura limitada.
Perigo, Alerta e INPE não fazem parte desta entrega.

A versão anterior foi preservada em archive/risk-2025-before-professor-v2.

## Estrutura

- incendio/risco_anual_v2/: código científico isolado, configuração e parâmetros recebidos portáveis.
- incendio/produtos/risco/v2/2025/: produto canônico agregado e setores científicos.
- incendio/produtos/clima/v1/2025/: produto observado mantido após conferência de hashes.
- frontend/: interface e sincronização das únicas cópias canônicas ativas.
- entrega_professor_v2/ e incednido/: insumos recebidos locais e ignorados.
- Os pipelines anteriores e os artefatos locais de Perigo permanecem preservados.

Veja [geração e proveniência](incendio/PRODUTOS_WEB.md) e [execução do frontend](frontend/README.md).
