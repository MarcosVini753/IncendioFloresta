# Incêndios Florestais — Acre

Aplicação React + MapLibre para o **Risco anual experimental v6 de 2025 e 2026**,
com **Random Forest**, cenário **F30C, sem clima**, e observações históricas de 2025.

- Abre em 2026 com média dos percentis; 2025 permanece disponível.
- Treino recebido: 2016–2024 para 2025 e 2016–2025 para 2026. São 11 preditores
  de paisagem e histórico de fogo, sem variáveis climáticas.
- Cobertura científica: **185.661.783 pixels por ano**, recortados originalmente
  pelo IBGE 2024, com pequenas lacunas NoData. Lacunas não são risco zero.
- Visão agregada: **6.875 grupos de 5 km**, com nove resumos selecionáveis,
  composição das classes e explicações técnicas. Mediana e P75 são exatos.
- A partir do zoom 8,5: raster progressivo de aproximadamente 30 m; o clique
  consulta sempre os valores Float32 originais, inclusive quando a imagem é reduzida.
- O índice percentil é posição relativa, sem %. A banda 1 é a probabilidade anual
  calibrada recebida, já em porcentagem, mostrada separadamente. Anos atípicos
  podem ser superestimados ou subestimados; não é um sistema operacional de alertas.
- A comparação anual usa somente médias dos percentis, cada ano com seu próprio ranking.
- Avaliações de 2023–2025: relatórios recebidos contra MapBiomas Fogo de 30 m,
  no mapa completo, separados das validações amostrais. Não há avaliação observada de 2026.
- Clima e cicatrizes de 2025 são independentes e preservados. As cicatrizes ficam
  inicialmente ocultas no risco; quando ativadas em 2026, há aviso temporal.
- O produto web ativo contém somente Random Forest. Os GeoTIFFs XGBoost F30C
  já estão disponíveis localmente; sua integração ao site permanece pendente.
  Perigo, Alerta e INPE continuam fora do produto ativo.

O GeoTIFF de altitude recebido permanece local e fora da visualização. Seu uso
foi adiado até conferir unidades, ausência de dados e correspondência espacial
com a grade dos mapas de risco; não será adicionado como camada explicativa agora.

A versão anterior está preservada em `archive/risk-v4-before-professor-v6`.

## Executar o site

O checkout contém os produtos web prontos, incluindo os setores Float32 dos dois
anos. **Nenhum treinamento, previsão ou calibração é executado pelo site ou build.**

```bash
cd frontend
npm install
npm run dev
# ou: npm run build
```

`predev`/`prebuild` sincronizam exclusivamente Risco v6 e Clima de 2025. `public`
e `dist` são cópias geradas e ignoradas. O modo raster padrão é `local`; os modos
`remote` e `aggregated` continuam disponíveis por configuração explícita.

## Reproduzir a preparação local

O pacote `entrega_professor_v6/` permanece local e ignorado. A importação usa
somente os GeoTIFFs completos Float32 e os relatórios; não usa os COGs recebidos
com índices inteiros e probabilidades arredondadas.

```bash
python3 -m venv incendio/.venv  # se o ambiente ainda não existir
incendio/.venv/bin/pip install -r incendio/risco_anual_v6/requirements.txt
incendio/.venv/bin/python incendio/importar_risco_professor_v6.py --year 2025
incendio/.venv/bin/python incendio/risco_anual_v6/exportar_resumos.py --year 2025
incendio/.venv/bin/python incendio/importar_risco_professor_v6.py --year 2026
incendio/.venv/bin/python incendio/risco_anual_v6/exportar_resumos.py --year 2026
```

O importador verifica todos os pixels, preserva máscara e valores e permite
retomada por checkpoints com hashes. Cada ano tem 222 setores de duas bandas
Float32; apenas os produtos v6 são distribuídos no site. Artefatos anteriores
permanecem recuperáveis pela branch de arquivo e pelo histórico, sem reescrita.

Veja [contratos e proveniência](incendio/PRODUTOS_WEB.md),
[frontend e publicação](frontend/README.md) e
[preparação científica](incendio/README.md).

## Planejamento de infraestrutura

O [estudo de contratação versus servidor próprio](docs/infraestrutura/estudo-servidor-risco-v4-2026-10-26.md)
compara publicação direta dos COGs (opção B) e servidor de mapas (opção C),
separando retreino anual, aplicação dos modelos e exposição dos resultados.
Inclui dimensionamento, custos de três anos, limites das estimativas e
[memória de cálculo reproduzível](docs/infraestrutura/calcular_cenarios.py).

O estudo considera que não há equipamento institucional disponível.
Veja [fontes e instruções para gerar PDF e Word](docs/infraestrutura/LEIA-ME.md).

## Representatividade dos grupos de 5 km

O [estudo da agregação espacial](incendio/risco_anual_v4/analises/representatividade/relatorio.md)
é uma análise histórica da v4: compara média, classe predominante, mediana e concentração de pixels altos. Os números daquele relatório não descrevem os novos mapas v6. Inclui figuras, resumos estatísticos e instruções para
reproduzir a análise e gerar o PDF localmente.
