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

## Build na Vercel e distribuição dos pixels de 30 m

Os setores dos dois anos somam aproximadamente **3,4 GiB** e são ignorados pelo
Git. Portanto um checkout limpo não os contém: não é um erro do Node ou do ano
2025. Não execute o importador científico no build da Vercel nem adicione esses
arquivos grandes ao Git para contornar o problema.

A sincronização aceita estas variáveis de ambiente (definidas antes de `npm run
build`, por exemplo nas configurações do projeto na Vercel):

| Modo | Configuração | Resultado |
| --- | --- | --- |
| Local | `RISK_RASTER_MODE=local` | Confere todos os setores e inclui-os em `public` e `dist`; falha se algum estiver ausente ou truncado. Padrão fora da Vercel. |
| Agregado | `RISK_RASTER_MODE=aggregated` | Publica metadados, grupos de 5 km e Clima; não inclui TIFFs e informa no site a indisponibilidade de 30 m. Padrão com `VERCEL=1`, sem URL externa. |
| Externo | `RISK_RASTER_BASE_URL=https://seu-host.example/risk/v4/` | Habilita os pixels originais via URL externa; não copia TIFFs para o build. Seleciona `remote` automaticamente. |

Para testar localmente o mesmo build agregado da Vercel:

~~~bash
cd frontend
RISK_RASTER_MODE=aggregated npm run build
~~~

Para habilitar o raster completo, **primeiro publique os setores existentes** em
um armazenamento estático escolhido. Preserve a estrutura:

~~~text
https://seu-host.example/risk/v4/2025/sectors/AC-V4-R000C000.tif
https://seu-host.example/risk/v4/2026/sectors/AC-V4-R000C000.tif
...todos os setores de cada index.json
~~~

Configure `RISK_RASTER_BASE_URL` com o prefixo **anterior ao ano**, público, sem
credenciais, query ou fragmento. O servidor deve permitir CORS para o domínio do
site e requisições GET com `Range` (idealmente responder 206). Se responder 200,
o worker admite apenas a leitura integral limitada a um setor do tamanho declarado
no índice. Não são usadas URLs privadas nem chaves no navegador. O build remoto
não verifica a disponibilidade da origem externa; confira as URLs e CORS após o
upload. Nenhum upload, novo serviço de hospedagem ou deploy é feito pelo script.

Cada sincronização gera `deployment.json` por ano, separado do manifesto
científico, registrando o modo e a URL raster. O loader valida essa configuração;
o modo agregado não cria worker raster, solicita TIFFs ou oculta a malha ao
aproximar. Modelos, anos, valores e produtos científicos não são modificados.
Para voltar ao modo completo local, execute `npm run dev` sem essas variáveis.

Validação focada: `npm run test:sync` verifica checkout sem setores, URL externa,
inclusão local e configuração inválida; `npm test -- src/data/riskV4.test.ts`
verifica o contrato de publicação e o carregamento agregado.

A v2 está preservada em `archive/risk-v2-before-professor-v4`.
Esta atualização não cria hospedagem, backend nem upload automático dos COGs.
