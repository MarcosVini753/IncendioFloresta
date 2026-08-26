# Frontend — Protótipo v0.1

Protótipo interativo para validar a experiência de visualização espacial e temporal do sistema de monitoramento de incêndios florestais no Acre.

## Escopo desta versão

- React + TypeScript + Vite.
- Mapa interativo com MapLibre GL JS.
- Mesmo mapa alternando entre as camadas de Risco e Perigo.
- Risco tratado como camada estática.
- Perigo com navegação temporal por slider e botões anterior/próximo.
- Série temporal sincronizada com a data selecionada.
- Clique nos pontos demonstrativos para visualizar coordenadas e índice.
- Alerta reservado para uma etapa futura.
- Dados locais simulados; nenhum valor deve ser usado para decisão operacional.

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

## Publicação na Vercel

Ao conectar este repositório à Vercel, configure `frontend` como **Root Directory**. A definição final de API, banco de dados e infraestrutura WebGIS fica fora do escopo deste protótipo.

## Próximas etapas

1. Validar layout e fluxo com o orientador.
2. Refinar a camada demonstrativa para representar melhor células/grades.
3. Experimentar um GeoTIFF/COG pequeno em uma prova técnica separada.
4. Definir o contrato de dados somente quando o frontend e o pipeline estiverem mais claros.
