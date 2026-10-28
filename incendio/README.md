# Produtos científicos da aplicação v4

Esta pasta contém o código e os produtos necessários ao site atual:

- `importar_risco_professor_v4.py`: importa os mapas finais recebidos de
  Random Forest e XGBoost, sem treinar ou recalibrar modelos.
- `risco_anual_v4/`: requisitos, geometria do clima e registro das validações.
- `exportar_clima_2025.py`: prepara o clima e as cicatrizes usados no site,
  sem depender dos pipelines históricos.
- `produtos/risco/v4/2025/`: resultados agregados e metadados.
- `produtos/risco/v4/2026/`: resultados agregados, metadados e os 208 COGs
  versionados para visualizar os pixels de 30 m.
- `produtos/clima/v1/2025/`: produto observado ativo, preservado apesar da
  versão de contrato diferente.
- `recursos/limite_acre.geojson`: referência cartográfica.

Códigos anteriores podem ser recuperados pelo histórico Git e branches de
arquivo. Dados brutos, resultados locais, ambientes e caches não são enviados.

## Usar os produtos prontos

O frontend não precisa executar Python para compilar ou visualizar os produtos
versionados. Na pasta frontend, execute npm install e npm run dev/build.
2026 tem detalhe de 30 m; 2025 permanece agregado.

## Reproduzir a importação

~~~bash
python3 -m venv incendio/.venv
incendio/.venv/bin/pip install -r incendio/risco_anual_v4/requirements.txt
incendio/.venv/bin/python incendio/importar_risco_professor_v4.py --year 2026
~~~

Requer GeoTIFFs e relatórios recebidos, mantidos localmente. O importador
confere cobertura, valores e agregações e permite retomada por checkpoint.
Para conferir o clima pronto sem ler rasters brutos:

~~~bash
incendio/.venv/bin/python incendio/exportar_clima_2025.py --validate-only
~~~

Veja [contratos, dados e proveniência](PRODUTOS_WEB.md).
