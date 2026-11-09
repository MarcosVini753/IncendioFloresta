# Produtos científicos ativos — v6

O site importa mapas finais; não executa modelos. A entrega recebida e os dados
brutos ficam locais, ignorados pelo Git.

- `importar_risco_professor_v6.py`: importa Random Forest e XGBoost F30C, sem clima,
  de 2025/2026. Não treina, prevê nem reaplica a calibração.
- `risco_anual_v6/`: requisitos, exportador dos nove resumos e testes focados.
- `produtos/risco/v6/<ano>/`: contrato 6.0, agregado, contorno IBGE 2024,
  índice, estatísticas derivadas e 222 setores COG Float32 versionados por ano.
- `produtos/clima/v1/2025/`: observações diárias e cicatrizes independentes,
  preservadas. Sua cobertura e resolução não foram ampliadas pela troca do risco.
- `exportar_clima_2025.py`: reprodução do produto observado, sem alteração nesta entrega.

Os importadores e estudos v4 são históricos e não alimentam a aplicação atual.
A versão anterior está na branch `archive/risk-v4-before-professor-v6`.
GeoTIFFs recebidos, SQLite, modelos, checkpoints e caches não são versionados.

Os insumos observados necessários ao exportador de Clima podem ser guardados
em `dados_locais/clima_2025/`, ou indicados com `--sources-root`. A cicatriz
original foi preservada nessa pasta antes de remover a entrega v4. Os rasters
brutos de umidade e precipitação não estavam mais no pacote v4; continuam
necessários apenas para regenerar o clima, não para executar o site pronto.

## Reproduzir os produtos

```bash
incendio/.venv/bin/pip install -r incendio/risco_anual_v6/requirements.txt
incendio/.venv/bin/python incendio/importar_risco_professor_v6.py --year 2025
incendio/.venv/bin/python incendio/risco_anual_v6/exportar_resumos.py --year 2025
incendio/.venv/bin/python incendio/importar_risco_professor_v6.py --year 2026
incendio/.venv/bin/python incendio/risco_anual_v6/exportar_resumos.py --year 2026
incendio/.venv/bin/python -m unittest discover -s incendio/risco_anual_v6 -p 'test_*.py'
```

Python >=3.11; Rasterio/GDAL com COG, NumPy, PyProj e Shapely. `--source-root`
e `--reports-root` permitem localizar os GeoTIFFs e relatórios em outra pasta;
os municípios recebidos permanecem na localização da entrega original.
A preparação do frontend usa apenas os produtos prontos, sem Python.

Veja [contrato, ciência e reprodução](PRODUTOS_WEB.md).
