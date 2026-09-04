# Frontend — Protótipo v0.2

Protótipo interativo para validar a experiência de visualização espacial e temporal do sistema de monitoramento de incêndios florestais no Acre.

## Escopo desta versão

- React + TypeScript + Vite.
- Mapa interativo com MapLibre GL JS.
- Mesmo mapa alternando entre as camadas de Risco e Perigo.
- Risco tratado como camada estática.
- Perigo com navegação temporal por slider e botões anterior/próximo.
- Série temporal sincronizada com a data selecionada.
- Sobreposição independente dos focos de calor do Programa Queimadas/INPE.
- Agrupamento dos focos em zoom distante e expansão do grupo ao clicar.
- Popup dos focos com data/hora, satélite, município, bioma e variáveis associadas.
- Clique nas células demonstrativas para visualizar coordenadas e índice.
- Alerta reservado para uma etapa futura.
- Risco e Perigo usam dados simulados e não devem orientar decisões operacionais.
- Os focos do INPE são detecções orbitais, não incêndios confirmados.

## Preparar os focos do INPE

A partir da raiz do repositório:

```bash
python3 scripts/prepare_inpe_hotspots.py
```

Se o ambiente disponibilizar o alias `python` para Python 3, ele também pode ser usado. O conversor seleciona o `focos_diario_br_*.csv` mais recente em `data/raw/inpe/`, filtra o Acre e grava `frontend/public/data/inpe/focos_ac.geojson`.

O arquivo versionado nesta entrega é um recorte de **04/08/2026**. A interface mantém essa data visível e não sincroniza os focos com o slider demonstrativo de Perigo.

## Executar localmente

```bash
cd frontend
npm install
npm run dev
```

Para validar o build:

```bash
npm run build
npm run preview
```

Durante o aceite manual, confirme:

1. Risco e Perigo continuam alternando normalmente.
2. O controle **Focos de calor — INPE** exibe `04/08/2026 · 62 focos no Acre`.
3. O controle oculta e reexibe pontos, agrupamentos e a legenda específica.
4. Clicar em um agrupamento aproxima o mapa.
5. Clicar em um foco individual abre os atributos do INPE.
6. Alternar Risco/Perigo mantém a sobreposição ativa.
7. O console do navegador não apresenta erros.

## Publicação na Vercel

Ao conectar este repositório à Vercel, configure `frontend` como **Root Directory**. A definição final de API, banco de dados e infraestrutura WebGIS fica fora do escopo deste protótipo.

## Próximas etapas

1. Validar layout e fluxo com o orientador.
2. Refinar a camada demonstrativa para representar melhor células/grades.
3. Experimentar um GeoTIFF/COG pequeno em uma prova técnica separada.
4. Definir o contrato de dados somente quando o frontend e o pipeline estiverem mais claros.
