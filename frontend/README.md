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
Essa transição só é habilitada quando os setores estão disponíveis na publicação.
Sem eles, a malha de 5 km permanece em todos os níveis de zoom, com aviso visível;
o clique retorna médias, nunca um pixel apresentado como original.

A banda percentual recebida já está multiplicada por 100. Random Forest tem
calibração temporal recebida; XGBoost tem correção de amostragem e não é calibrado.
Os dois valores são rotulados distintamente e não são previsão operacional.

Para 2025: treino 2016–2024 e clima de 2024. Para 2026: treino 2016–2025,
clima de 2025. Ambos usam 13 preditores. Avaliações históricas de
2023–2025 são recebidas do professor e correspondem à variante exibida e
ao nível 30m_fogo. Não há avaliação observada de 2026 na entrega.

## Contornos dos municípios do Acre

A interface exibe, **por padrão**, as divisas dos 22 municípios do Acre sobre o
mapa de risco anual e o mapa histórico de clima. A opção **Divisas municipais**
nas barras de controles permite ocultar ou restaurar o traçado sem recarregar os
modelos; a preferência é mantida ao trocar de aba.

A camada é carregada localmente de
`frontend/public/data/reference/acre-municipalities.geojson` (aproximadamente
30 KiB). Foi preparada a partir dos polígonos publicados pelo projeto
[br-geojson](https://github.com/henriquemalvar/br-geojson), que utiliza a
[API de Malhas do IBGE](https://servicodados.ibge.gov.br/api/docs/malhas)
em resolução simplificada. A
[Malha Municipal do IBGE](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html)
é a referência territorial. O GeoJSON contém o nome e o código IBGE de cada
município. Trata-se de uma **referência cartográfica simplificada** para
visualização web, não de limites jurídicos de precisão cadastral nem de uma
máscara de cálculo dos modelos científicos.

O traçado não altera `grid.geojson`, GeoTIFFs, COGs, percentis,
cobertura NoData, unidades administrativas dos relatórios ou a camada original
de limites estaduais. Uma diferença entre o contorno municipal e o contorno
estadual usado nos produtos científicos pode ocorrer porque as fontes foram
simplificadas e produzidas em momentos diferentes. A busca por município
continua levando à sede urbana, não à média do município.

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
# Opcional, na raiz: regenerar setores a partir dos mapas finais recebidos.
python3 -m venv incendio/.venv  # apenas se o ambiente ainda não existir
incendio/.venv/bin/pip install -r incendio/risco_anual_v4/requirements.txt
incendio/.venv/bin/python incendio/importar_risco_professor_v4.py --year 2025
incendio/.venv/bin/python incendio/importar_risco_professor_v4.py --year 2026

cd frontend
npm install
npm run dev
npm run build
npm run preview
~~~

Predev/prebuild conferem e sincronizam somente Risco v4/2025, Risco v4/2026 e Clima v1/2025.
Os COGs de 2025 e 2026 são versionados; as cópias public/dist continuam
ignoradas. Código, manifesto, índice e GeoJSON agregado são versionados. Consulte
[geração e proveniência](../incendio/PRODUTOS_WEB.md).

## Build na Vercel e distribuição dos pixels de 30 m

O GitHub inclui **208 COGs de cada ano**, 416 arquivos de 2025 e 2026,
aproximadamente 3,57 GB (3,33 GiB) ao todo, com menos de 15 MiB por arquivo.
O checkout fornece tudo para publicar o detalhe de 30 m dos dois anos sem
treinamento nem geração científica no build.

A comparação anual, a consulta agregada e o Clima de 2025 continuam disponíveis.
Ao aproximar o mapa em qualquer ano, a publicação padrão permite consultar
os pixels originais.

| Modo dos dois anos | Configuração antes do build | Resultado |
| --- | --- | --- |
| Local, padrão também na Vercel | Sem variáveis, ou `RISK_RASTER_MODE=local` | Inclui os setores versionados de 2025 e 2026. |
| Apenas agregado | `RISK_RASTER_MODE=aggregated` | Não copia TIFFs de nenhum ano. |
| Origem externa | `RISK_RASTER_BASE_URL=https://seu-host.example/risk/v4/` | Busca os setores em `2025/` e `2026/` na origem externa; não copia TIFFs. |

Se o painel da Vercel tiver `RISK_RASTER_MODE=aggregated`, remova a variável ou
troque para `local` para habilitar os setores incluídos. Remova
`RISK_RASTER_BASE_URL` ao usar o modo local. URLs externas precisam ser públicas,
sem credenciais/query/fragmento, com CORS e preferencialmente HTTP Range.

Cada sincronização gera `deployment.json` por ano, sem alterar o manifesto
científico. O ano agregado não cria worker raster, não solicita TIFFs e mantém
a malha visível ao aproximar. O modo local confere presença e tamanho dos COGs
de ambos os anos antes de tocar nas cópias geradas.

Verificações focadas: `npm run test:sync`, `npm test` e `npm run build`.
Os testes de sincronização conferem os dois anos na publicação padrão da Vercel
e falha antes de substituir as cópias quando falta um setor de 2025.
A exceção do MapLibre no prebundle do Vite permanece.

## Código mantido

A árvore atual contém a interface v4, seus controles, comparação anual,
referências municipais, Clima e produtos ativos. Componentes e loaders dos
protótipos antigos foram removidos. O código anterior continua recuperável pelo
histórico Git e pelas branches de arquivo, sem reescrever commits remotos.
