# Incêndios Florestais — Acre

Aplicação React + MapLibre para explorar dois produtos de naturezas distintas:

- suscetibilidade histórica experimental, calculada por quatro modelos científicos;
- focos de calor observados pelo Programa Queimadas/INPE, como sobreposição independente.

O mapa não apresenta previsão operacional, perigo diário nem alerta. Os escores de
suscetibilidade são valores relativos entre 0 e 1 e não probabilidades calibradas.

## Estrutura

- `incendio/`: pipeline científico e cópia canônica dos produtos web;
- `frontend/`: interface e sincronização automática do produto canônico;
- `scripts/prepare_inpe_hotspots.py`: preparação dos focos INPE do Acre;
- `data/raw/`: dados-fonte do INPE versionados para esta entrega.

Consulte [incendio/README.md](incendio/README.md) para reproduzir o produto e
[frontend/README.md](frontend/README.md) para executar e validar a interface.
