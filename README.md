# Incêndios Florestais — Acre

Aplicação React + MapLibre para explorar produtos de naturezas distintas:

- suscetibilidade histórica experimental, calculada por quatro modelos científicos;
- perigo diário de 2015 como reconstituição histórica em grade agregada;
- focos de calor observados pelo Programa Queimadas/INPE, como sobreposição independente.

O mapa não apresenta previsão operacional nem Alerta. Tanto a suscetibilidade quanto
o perigo histórico usam escores relativos entre 0 e 1, não probabilidades calibradas.

## Estrutura

- `incendio/`: pipeline científico e cópia canônica dos produtos web;
- `frontend/`: interface e sincronização automática do produto canônico;
- `scripts/prepare_inpe_hotspots.py`: preparação dos focos INPE do Acre;
- `data/raw/`: dados-fonte do INPE versionados para esta entrega.

Consulte [incendio/README.md](incendio/README.md) para reproduzir o produto e
[frontend/README.md](frontend/README.md) para executar e validar a interface.
