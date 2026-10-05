# Incêndios Florestais — Acre

Aplicação React + MapLibre para explorar dois produtos de naturezas distintas:

- risco anual experimental de 2025, com cinco modelos e cenários Acre inteiro/Oeste–Leste;
- clima diário e cicatrizes observadas de 2025, com 365 datas.

O mapa não apresenta previsão operacional, perigo diário nem alerta. Os escores de
risco são valores relativos entre 0 e 1 e não probabilidades calibradas.
O mapa anual usa treino 2007–2024 e clima de 2024; a seção climática exibe 2025.
O site anterior está preservado em `archive/risk-2016-before-2025`.

## Estrutura

- `incendio/`: pipeline científico e cópia canônica dos produtos web;
- `frontend/`: interface e sincronização automática do produto canônico;
- `incendio/risco_anual/`: novo pipeline anual isolado, parâmetros e proveniência;
- `incednido/`: pacote bruto local e ignorado, não publicado;
- `data/raw/`: dados legados, sem sobreposição INPE ativa nesta entrega.

Consulte [incendio/PRODUTOS_WEB.md](incendio/PRODUTOS_WEB.md) para reproduzir os produtos e
[frontend/README.md](frontend/README.md) para executar e validar a interface.
