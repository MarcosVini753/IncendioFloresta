# Estudo de infraestrutura — 26/10/2026

Entregas em `estudo-servidor-risco-v4-2026-10-26.pdf` e `.docx`.
Os dois formatos são gerados do mesmo conteúdo, com cotações públicas e
premissas separadas de medições. Não há treinamento ou contratação neste diretório.
PDF, Word e `resultados_calculo.json` são cópias geradas, mantidas localmente e
ignoradas pelo Git. O relatório completo em Markdown, as fontes, premissas e
scripts são versionados para consulta e reprodução.

- `conteudo_estudo.md`: texto-fonte, com marcadores preenchidos pelo gerador.
- `premissas_e_cotacoes.json`: preços, fontes e hipóteses editáveis.
- `calcular_cenarios.py`: memória de cálculo, usando somente biblioteca padrão.
- `gerar_documentos.py`: produção do PDF e Word.
- `resultados_calculo.json`: resultados numéricos gerados.
- `estudo-servidor-risco-v4-2026-10-26.md`: texto completo preenchido.

Para conferir as contas sem instalar bibliotecas:

```bash
python3 docs/infraestrutura/calcular_cenarios.py
```

Para gerar novamente os documentos num ambiente separado:

```bash
python3 -m venv /tmp/infra-risco-documentos-venv
/tmp/infra-risco-documentos-venv/bin/pip install -r docs/infraestrutura/requirements-documentos.txt
/tmp/infra-risco-documentos-venv/bin/python docs/infraestrutura/gerar_documentos.py
```

O gerador consulta as tabelas da entrega recebida e o manifesto de 2026 para
conferir as contagens. Manter essas evidências disponíveis. O texto é um
retrato datado: mudar as premissas financeiras não atualiza automaticamente
as descrições científicas, a disponibilidade de fontes ou os preços citados.

Limites da verificação: contas recalculadas, arquivo Word conferido
estruturalmente e PDF conferido por extração de texto, limites de página e
amostras renderizadas. Não foi feito benchmark dos hardwares, teste de carga
da aplicação, treinamento de modelos ou validação visual do Word em um editor.
