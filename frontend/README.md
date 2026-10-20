# Frontend — Risco professor v4 de 2025/2026 e Clima de 2025

O site abre em Random Forest, cenário AB30C com clima suavizado e treino com
MapBiomas Fogo. Random Forest e XGBoost de **2025 e 2026** são disponibilizados.
O seletor **Ano do risco** abre em 2026. Ao trocar, o mapa, a consulta,
o período de treino e a avaliação acompanham o ano escolhido. Produtos já
carregados ficam em memória; leitores raster são recriados para impedir mistura
de setores entre anos. A seleção antiga é limpa; o modelo escolhido permanece.
Não há seletor de cenários nem carregamento dos setores da v2.

## Ler e consultar o mapa

A cor representa o índice percentil recebido, de 0 a 100 sem %. As classes
são fixas: Muito baixo [0,50), Baixo [50,70), Moderado [70,90), Alto [90,95)
e Muito alto [95,100]. Percentil não é chance de incêndio.

Até zoom 8,5: grupos de 5 km, com cor pela classe da média dos percentis.
O clique compara médias dos modelos e a proporção dos pixels em cada classe.

A partir de zoom 8,5: o raster é lido por setores COG. Enquanto afastado,
usa overviews por média; ao aproximar, usa os dados originais de cerca de 30 m.
O clique **sempre consulta a imagem original**, retornando linha, coluna,
centro, contorno e valores dos dois modelos. A seleção permanece ao trocar modelo.

A banda percentual recebida já está multiplicada por 100. Random Forest tem
calibração temporal recebida; XGBoost tem correção de amostragem e não é calibrado.
Os dois valores são rotulados distintamente e não são previsão operacional.

Para 2025: treino 2016–2024 e clima de 2024. Para 2026: treino 2016–2025,
clima de 2025. Ambos usam 13 preditores. Avaliações históricas de
2023–2025 são recebidas do professor e correspondem à variante exibida e
ao nível 30m_fogo. Não há avaliação observada de 2026 na entrega.

## Raster no navegador

GeoTIFF.js roda em Web Worker, com até quatro tarefas concorrentes, leitores
de até 32 setores e LRU de até 128 MiB de blocos decodificados. As coordenadas
Web Mercator de cada linha de tile são convertidas para latitude antes de
amostrar a grade original EPSG:4326; não há interpolação linear incorreta
entre as latitudes extremas do tile.

Requisições obsoletas são canceladas. COGs permitem HTTP Range; se o servidor
não oferecer Range, a leitura integral é limitada a um setor pequeno, nunca
ao GeoTIFF do estado inteiro. Os setores atuais têm menos de 15 MiB cada.

O worker é emitido como módulo ES para permitir os decodificadores carregados
sob demanda do GeoTIFF.js. A exclusão de MapLibre do prebundle Vite permanece.

## Clima e cicatrizes

A aba Clima mantém os 365 dias de 2025 e inicia em 25/08/2025. Estatísticas são
espaciais por dia; não são extremos horários. A duração de acumulação da
precipitação continua não documentada.

As cicatrizes de 2025 ficam inicialmente ocultas no Risco de 2026. Quando
ativadas, os dois anos e a diferença temporal são mostrados. Essa sobreposição
não valida a previsão de 2026 e não conta incêndios confirmados.

## Executar e compilar

~~~bash
# Na raiz: preparar os setores locais uma vez.
python3 -m venv incendio/.venv  # apenas se o ambiente ainda não existir
incendio/.venv/bin/pip install -r incendio/risco_anual_v4/requirements.txt
incendio/.venv/bin/python incendio/importar_risco_professor_v4.py

cd frontend
npm install
npm run dev
npm run build
npm run preview
~~~

Predev/prebuild conferem e sincronizam somente Risco v4/2025, Risco v4/2026 e Clima v1/2025.
COGs em setores, public e dist são gerados e ignorados pelo Git. Código,
manifesto, índice e GeoJSON agregado são versionados. Consulte
[geração e proveniência](../incendio/PRODUTOS_WEB.md).

A v2 está preservada em `archive/risk-v2-before-professor-v4`.
Esta atualização não configura hospedagem, backend ou deploy.
