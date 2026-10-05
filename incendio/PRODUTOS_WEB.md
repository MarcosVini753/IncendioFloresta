# Produtos web — Risco e Clima de 2025

## Ambiente e fontes

O pacote recebido em incednido/ continua local e ignorado. Código anual
foi integrado em risco_anual/, isolado do pipeline legado e do Perigo.
O JSON de configuração documenta caminhos relativos dos TIFFs e da
planilha; ajuste-os se os insumos estiverem em outra pasta.

```bash
cd incendio
python3 -m venv .venv
.venv/bin/python -m pip install -r risco_anual/requirements.txt
.venv/bin/python exportar_risco_2025.py
.venv/bin/python exportar_clima_2025.py
.venv/bin/python exportar_risco_2025.py --validate-only
.venv/bin/python exportar_clima_2025.py --validate-only
.venv/bin/python -m unittest discover -s tests -v
```

Os parâmetros recebidos foram selecionados com Python 3.11.9,
scikit-learn 1.9.0 e XGBoost 3.2.0. A geração registra as versões efetivas;
não oculta diferenças de ambiente. Impressão da tabela de treinamento,
preditores, semente, corte, folds e espaço de busca devem coincidir antes
de reutilizar os vencedores. Divergências acionam a mesma seleção agrupada
por ano, somente para o modelo/escopo afetado.

## Protocolo de risco anual

- Ano-alvo 2025; treinamento 2007–2024, nunca cicatrizes de 2025.
- Semente 42; balanceamento 1:1 separado por ano e região.
- Preditores: vegetação, distância à estrada, distância à água, altitude,
  umidade média anual e precipitação acumulada anual.
- Defasagem de um ano: previsão 2025 usa clima 2024.
- Cinco modelos: Random Forest, GradBoost, Regressão Logística, Fuzzy k-NN
  exato e XGBoost. O k é selecionado por escopo; não é fixado em 29.
- Cenários: Acre inteiro e Oeste–Leste (x UTM < 337100 m = Oeste).
  O corte não é administrativo. Padrão: Random Forest regional.

Resultado experimental, relativo em [0,1] e não calibrado. Não representa
perda financeira, previsão operacional ou reprodução integral da tese.
Paisagem baseada em insumos 2003–2013. Modelos regionais podem apresentar
descontinuidade no corte.

O manifesto separa CV balanceada agrupada por ano, avaliações históricas
recebidas de 2016, avaliação rolante recebida de 2017–2024 e métricas
recalculadas de 2025 no território completo. Não comparar diretamente
PR-AUC de CV balanceada com PR-AUC territorial.

Oito combinações modelo/cenário reproduziram exatamente PR-AUC e ROC-AUC
recebidas de 2025. XGBoost reproduziu os dados e parâmetros, mas suas duas
combinações tiveram métricas diferentes após retreinamento neste ambiente.
O manifesto registra ambas, seus deltas e o ambiente. Não se promete
reprodução bit a bit. Multithreading/ordem de somas podem afetar o resultado
segundo a [FAQ oficial do XGBoost](https://xgboost.readthedocs.io/en/release_3.1.0/faq.html);
isso é uma explicação possível, não uma causa comprovada neste caso.

Em 2025 há apenas 39 células científicas positivas no alvo recebido.
Não é uma contagem de incêndios nem prova completude das observações.
As fontes anuais e bandas são conferidas; a completude do levantamento
é uma limitação científica que não pode ser garantida pelo código.

## Contrato, geração e retomada

Produtos canônicos:

- produtos/risco/v1/2025/aggregated: manifesto, 212 polígonos recortados
  pelo limite versionado do Acre e limite.
- produtos/risco/v1/2025/native_sharded_grid: manifesto, índice e 212
  setores, totalizando 307.410 IDs científicos únicos.
- produtos/clima/v1/2025: manifesto, grade, limite, matrizes diárias
  de umidade/precipitação e cicatrizes.

Geometrias armazenam dez propriedades score_<cenario>_<modelo>,
declaradas no manifesto. Agregação aritmética mean, IDs AC-RxxCxx,
contagem de fontes e centroide representativo. Na grade original,
IDs AC-Y<Y>-X<X>, cantos reais reprojetados de EPSG:31979 e agregação none.
O frontend consome exclusivamente 2025.

Checkpoints por modelo/escopo em resultados/risco_2025/checkpoints
registram parâmetros, impressão da tabela, hashes de fontes e ordem,
períodos, preditores, versões e backend. Reexecute o mesmo comando
para retomar. Checkpoints incompatíveis ou inválidos são recalculados.
Nenhum lançamento parcial é permitido.

O produto é escrito e auditado em pasta temporária antes de substituir
o ativo. Se já existir produto, ele é movido para 2025-previous;
preserve/mova esse backup local antes de uma terceira geração.
Não o inclua no commit. Os dois renames não constituem uma transação:
interrupção no intervalo pode exigir restaurar o backup.

## Clima e cicatrizes

Arquivos novos chamados 2016_2026 contêm bandas de 2016–2025.
Datas são lidas das descrições das bandas, nunca inferidas do nome.
O produto 2025 possui 365 dias e matrizes de 365 × 212 × 3.

Estatísticas espaciais por dia: mínimo/máximo entre pixels válidos
intersectantes e média ponderada pela área geodésica de interseção.
Sem cobertura, os três valores são null. Pixels climáticos de 0,1°:
não há detalhamento climático na grade de 893 × 598 m.
O período de acumulação da precipitação não está documentado.

Cicatrizes usam a banda anual 2025, com valores positivos como dia do ano,
recortadas pelo limite do Acre. Cicatriz não é foco orbital pontual nem
um incêndio confirmado individualmente.

## Versionamento e sincronização

Versionar código, documentação, requisitos, parâmetros portáveis, métricas
compactas e produtos públicos. TIFF, XLSX, Parquet, Joblib, PNG, SQLite,
caches, ambientes e Zone.Identifier ficam locais. Pacote bruto recebido,
PDF da tese e artefatos locais de Perigo não entram nos commits.

Npm dev/build sincronizam as cópias canônicas para pastas geradas e ignoradas.
Produtos antigos permanecem como legado para regressão, mas não são
copiados ao build ativo. Site anterior preservado na branch
archive/risk-2016-before-2025. Perigo intocado; sem novo deploy.
Postbuild remove somente dist/data/danger, nunca os arquivos locais originais.
