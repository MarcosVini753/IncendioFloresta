# Incêndios Florestais — Acre

Aplicação React + MapLibre para explorar o Risco anual experimental de **2025 e 2026**
da entrega do professor v4 e observações históricas de **2025**.

- Dois modelos: **Random Forest** (inicial) e XGBoost.
- Cenário recebido: AB30C, treinado com MapBiomas Fogo, com clima suavizado.
- Seletor de ano: 2026 inicialmente, com alternância para 2025.
- Risco 2025: treino 2016–2024 e clima de 2024. Risco 2026: treino 2016–2025 e clima de 2025. Nenhum treino ou previsão é executado pelo site.
- Mapa afastado: grupos de 5 km, coloridos pela classe da média dos percentis.
- Zoom a partir de 8,5: raster progressivo de aproximadamente 30 m; clique sempre consulta o pixel original.
- Random Forest tem calibração temporal recebida; XGBoost tem correção de amostragem e não é calibrado.
- Percentil é posição relativa no ranking, sem símbolo de porcentagem. A saída percentual do modelo aparece separadamente.
- Avaliações de 2023–2025 são relatórios recebidos, contra MapBiomas Fogo em 30 m. Não há avaliação observada de 2026 na entrega.
- Clima diário e cicatrizes de 2025 continuam independentes. As cicatrizes ficam ocultas inicialmente no Risco de 2026.
- Perigo, Alerta e INPE não fazem parte desta entrega.

A versão v2 foi preservada em `archive/risk-v2-before-professor-v4`.

## Preparar e executar

Os dois GeoTIFFs finais de cada ano ficam em `entrega_professor_v4/mapas_geotiff`.
O pacote recebido e os setores de 2025 permanecem locais e ignorados pelo Git.
Os **208 setores de 2026 são versionados**, totalizando cerca de 1,67 GiB.

~~~bash
python3 -m venv incendio/.venv  # apenas se o ambiente ainda não existir
incendio/.venv/bin/pip install -r incendio/risco_anual_v4/requirements.txt
incendio/.venv/bin/python incendio/importar_risco_professor_v4.py --year 2025
incendio/.venv/bin/python incendio/importar_risco_professor_v4.py --year 2026
cd frontend
npm install
npm run dev
~~~

O importador só prepara resultados já calculados. Confere integralmente
máscaras, domínios e cobertura; grava 208 setores COG sem alterar os valores
e agrega 172.340.796 pixels em 6.393 grupos de 5 km. Checkpoints permitem
retomada. O produto ativo só é substituído após a auditoria.

O checkout inclui tudo que o frontend precisa: `npm install` e `npm run build`
não executam Python nem precisam dos GeoTIFFs brutos. O build publica **2026 em
30 m** e mantém **2025 apenas agregado**, inclusive na Vercel. Os setores de
2025 não são enviados, mesmo quando existem localmente.

Os pipelines e produtos históricos de INPE, Perigo, Suscetibilidade e Risco v1/v2
foram retirados da versão atual. O importador v4, o exportador do clima utilizado,
as referências cartográficas e os produtos ativos permanecem. Produtos históricos
locais são ignorados; o código removido pode ser recuperado pelo Git.

Para a Vercel, mantenha `RISK_RASTER_MODE=local` ou remova a variável para usar
esse padrão. Remova uma eventual `RISK_RASTER_BASE_URL` se quiser os setores
incluídos no próprio site. O modo `aggregated` permanece disponível como opção
explícita para compilar sem rasters. Arquivos em `public` e `dist` são cópias
geradas e não são versionados.

A limpeza reduz o conteúdo atual enviado e compilado; **não reescreve o histórico
Git** nem remove deployments anteriores da Vercel.

Veja [produtos e proveniência](incendio/PRODUTOS_WEB.md) e
[frontend e publicação](frontend/README.md).
