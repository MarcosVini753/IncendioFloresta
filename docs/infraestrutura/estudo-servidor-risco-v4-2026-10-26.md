# Servidor para o Risco anual do Acre

## Nuvem ou equipamento próprio?

Estudo de custo-benefício para executar o ciclo completo da entrega do professor v4: buscar os dados, preparar as informações, treinar Random Forest e XGBoost, calcular os mapas e publicá-los na internet.

Data-base das consultas: **26 de outubro de 2026**. Instalação própria considerada em Rio Branco, Acre. Não há equipamento institucional disponível. Horizonte de comparação: **1, 3 e 5 anos**, com valores constantes de hoje.

> Recomendação inicial: contratar processamento temporário na nuvem e começar pela opção B, que publica os arquivos do mapa diretamente. Para uma atualização anual, comprar uma GPU e manter um servidor ligado o ano inteiro não apresenta o melhor custo-benefício nas premissas deste estudo.

| Alternativa | Referência de custo | Leitura correta |
| --- | --- | --- |
| Nuvem + B | R$ 877,76/ano | Infraestrutura do ciclo anual e publicação; trabalho técnico separado |
| Nuvem + C | R$ 2.778,56/ano | Mesma ciência + VPS de mapas como entrada para piloto |
| Próprio sem GPU | R$ 23.862,44 iniciais | Inclui instalação e reserva; operação anual adicional |
| Próprio com GPU | R$ 29.722,73 iniciais | Configuração cotada com 64 GB, SSD de 2 TB e GPU de 16 GB |

A opção C acrescenta um serviço que prepara as imagens dos mapas no servidor. Pode melhorar o atendimento de dispositivos limitados e permitir novas consultas, mas custa mais e exige manutenção. Não precisa de GPU para servir mapas já calculados.

**Como ler este documento:** preços consultados são diferentes de provisões de orçamento; tempos de processamento são diferentes de medições. Todos esses casos são identificados. Os números não são uma proposta comercial, uma promessa de desempenho nem um contrato de disponibilidade.

O orçamento não pressupõe computador, nobreak, internet de hospedagem ou cópia de segurança institucional já disponíveis. Na nuvem, a máquina temporária executa todo o cálculo; não depende de GPU do usuário. Um dispositivo simples para administrar as contas não é dimensionado como servidor.

<!-- pagebreak -->

## 1. O que estamos comparando

O trabalho pesado acontece uma vez por ano. O atendimento ao público acontece durante o ano inteiro. Essa diferença é a principal razão para não usar uma máquina cara de cálculo como servidor permanente sem necessidade.

| Etapa | Quando acontece | Principal recurso |
| --- | --- | --- |
| Buscar e conferir os dados | Uma atualização anual e eventuais correções | Internet, disco e CPU |
| Preparar grade e atributos | Primeira implantação e atualizações anuais | CPU, RAM e SSD |
| Refazer o treinamento e a avaliação necessária | Anualmente | CPU, RAM e, opcionalmente, GPU NVIDIA |
| Aplicar os dois modelos no Acre | Anualmente | GPU/CPU e leitura de dados |
| Preparar GeoJSON e setores COG | Após o cálculo | CPU e SSD |
| Hospedar o site e entregar mapas | Continuamente | Internet, armazenamento e, na C, CPU |

**Escopo científico:** cenário AB30C com clima suavizado, dois modelos, um mapa anual novo. O produto observado de Clima permanece separado. Não estão incluídos Perigo diário, INPE, novos modelos, processamento de outros estados ou execução de todos os experimentos antigos a cada ano.

Refazer o treino significa ajustar novamente os modelos com os anos disponíveis anteriores ao ano-alvo. Não significa obrigatoriamente repetir toda a busca de parâmetros e toda a avaliação histórica desde o início. A decisão de conservar parâmetros ou pesquisar novos precisa ser científica, documentada e refletida no orçamento.

**Três tipos de informação usados:**

- **Conferido no repositório:** dimensões, número de pixels, preditores, amostras, árvores e produtos atuais.
- **Informado pelo professor:** duração de aproximadamente 7 e 4 horas em duas rodadas, num i9 com RTX 4060 e 16 GB. Não é medição desta análise nem duração de um único mapa anual.
- **Premissa de planejamento:** horas reservadas na nuvem, consumo elétrico, internet, visitas e horas técnicas. São substituíveis após um piloto.

Não foi treinado um modelo neste estudo. Não foram contratados serviços, realizados pagamentos ou executado teste de carga público.

<!-- pagebreak -->

## 2. O caminho dos dados, sem complicar

Pense em uma ficha para cada localização. Ela reúne as características que os modelos usam para aprender com os anos anteriores e depois estimar o risco do ano escolhido.

| Informações usadas | O que representam |
| --- | --- |
| Paisagem e clima: 6 preditores | Vegetação, distância da água, distância de estradas, altitude, umidade média anual e precipitação acumulada anual |
| Histórico: 4 preditores | Tempo desde a queima, histórico com maior peso para eventos recentes, queima anterior e contexto de fogo na vizinhança |
| Mudança da paisagem: 3 preditores | Desmatamento recente, proporção de desmatamento e proporção de agropecuária no entorno |

O modelo aprende a relacionar essas informações ao rótulo de área queimada do MapBiomas Fogo. Um pixel queimado não equivale a um incêndio confirmado: um evento pode atingir muitos pixels.

No produto de 2026, o treino usa 2016–2025 e o clima utilizado no mapa é de 2025. O produto de 2025 usa treino até 2024 e clima de 2024. Para o ano Y, histórico de fogo e demais informações anuais devem respeitar a defasagem prevista no código.

O clima é interpolado para poder ser combinado com a grade de 30 m. Isso não transforma uma observação climática mais grosseira em uma medição real a cada 30 m.

O fluxo proposto para o servidor é:

1. Verificar se os insumos necessários ao ano-alvo foram publicados e estão completos.
2. Baixar recortes, registrar fontes e hashes, preparar os atributos e amostras.
3. Refazer o treino; atualizar a avaliação e a calibração temporal sem informação futura.
4. Aplicar os modelos e produzir os GeoTIFFs numéricos.
5. Gerar os grupos de 5 km, os COGs detalhados e os manifestos.
6. Conferir o produto e só então substituir a versão pública.

O site mostra valores já calculados. Ele não executa o treinamento a cada clique. A cor representa o **índice percentil**, de 0 a 100 sem sinal de porcentagem; o painel também apresenta o valor do modelo. Random Forest tem calibração temporal recebida; XGBoost é corrigido por amostragem e não calibrado. Percentil não é chance de incêndio.

<!-- pagebreak -->

## 3. Qual é o tamanho real do problema?

O manifesto atual registra **172.340.796 pixels válidos**. O retângulo completo tem 27.341 colunas por 14.942 linhas, incluindo posições sem dados. Essas duas contagens não podem ser confundidas.

Para treinar, o código amostra 10% dos pixels positivos de cada ano e até 19 negativos por positivo mantido. A tabela recebida de 2016–2025 soma **43.092.640 exemplos de treinamento**. Não é correto calcular a memória do treino como se todos os 172 milhões de pixels de todos os anos fossem usados simultaneamente.

| Estrutura | Conta | Tamanho aproximado |
| --- | --- | --- |
| Uma matriz anual, 13 preditores | 172.340.796 × 13 × 4 bytes | 8,35 GiB |
| Mesma matriz com as 17 colunas preparadas pelo armazém | 172.340.796 × 17 × 4 bytes | 10,91 GiB |
| Amostras recebidas, 13 preditores ativos | 43.092.640 × 13 × 4 bytes | 2,09 GiB |
| Amostras com as 17 colunas preparadas | 43.092.640 × 17 × 4 bytes | 2,73 GiB |
| Bloco de 8 milhões de pixels, 13 preditores | 8.000.000 × 13 × 4 bytes | 0,39 GiB |

GiB é uma unidade de memória; 1 GiB corresponde a 1.073.741.824 bytes. Os valores acima são só as matrizes numéricas. Árvores, rótulos, cópias temporárias, bibliotecas e o sistema operacional também consomem memória.

O código calcula em blocos e usa arquivos em disco para não precisar manter tudo na RAM. Para compra, **32 GB são uma configuração a testar; 64 GB dão folga**, principalmente se a mesma máquina hospedar mapas. A rodada relatada com 16 GB não prova que qualquer servidor de 16 GB suportará todas as etapas simultaneamente.

Há um limite de memória configurado de **11 GiB por processo monitorado**. Comprar 64 GB não remove esse limite. Uma eventual alteração dele, dos blocos ou do paralelismo exige teste; o limite também não é um teto para a RAM total da máquina nem para a VRAM da placa.

Os setores web dos dois anos atuais somam cerca de **3,57 GB decimais, ou 3,33 GiB**, em 416 arquivos. Reservar 50 GB para produtos públicos é suficiente para vários anos no tamanho atual; caches científicos e cópias históricas precisam de espaço separado.

<!-- pagebreak -->

## 4. Complexidade: por que o cálculo pode levar horas?

Os parâmetros vencedores recebidos para o cenário exposto são Random Forest com **200 árvores e profundidade máxima 14**, e XGBoost com **400 árvores e profundidade máxima 4**. A validação testa também outras configurações; o mapa usa as vencedoras registradas, não todas elas ao mesmo tempo.

Para entender o custo da aplicação, conte aproximadamente as perguntas percorridas nas árvores:

> Trabalho de aplicação ≈ pixels × repetições climáticas × soma de (árvores × profundidade).

A versão suavizada calcula 16 perturbações climáticas e tira a média. O comando atual também gera a versão não suavizada: se ambas estiverem faltando, são **17 aplicações por modelo**. Não são 17 treinos novos.

Conta do caminho completo atual para um ano:

**172.340.796 × 17 × [(200 × 14) + (400 × 4)] = 12.891.091.540.800 visitas potenciais a nós.**

São cerca de **12,89 trilhões de visitas potenciais**. É uma aproximação superior por profundidade máxima, não uma contagem de FLOPs: algumas árvores encerram caminhos antes. Não se deve dividir esse número pelos “TFLOPs” anunciados de uma placa para prever a duração.

Se apenas a suavizada fosse gerada, seriam cerca de 12,13 trilhões, uma economia teórica de 5,9% nessa parcela. Isso exigiria ajuste explícito do fluxo, não apenas comprar hardware. Este estudo mantém a conta de 17 aplicações.

No treinamento por histogramas, o trabalho depende dos exemplos M, preditores F, árvores T, profundidade D e quantidade de configurações e divisões testadas. Uma aproximação útil é O(M × F × T × D), multiplicada pelos ajustes de validação; construção de histogramas e quantização acrescentam outras parcelas. Não é uma fórmula de tempo exato.

Preparar os atributos e importar os mapas exige percorrer muitos dados: em grande parte, cresce com a quantidade de pixels. O agrupamento do importador também ordena identificadores dentro de cada bloco. Leitura, projeção e compressão podem dominar etapas mesmo com uma GPU rápida.

**O que faz crescer o custo:** mais modelos e anos de saída; uma região maior; mais perturbações; árvores maiores; refazer toda a busca de parâmetros. Metade do tamanho de pixel em cada direção pode quadruplicar o número de pixels para a mesma área.

<!-- pagebreak -->

## 5. Como comparar os hardwares sem inventar um benchmark

Uma CPU com o dobro de núcleos não garante a metade do tempo. Parte do processo depende de disco, memória, rede e trechos que não usam todos os núcleos. Uma GPU mais forte não acelera automaticamente o download, o GeoJSON ou a compressão de arquivos.

| Perfil possível | Recursos | Uso mais adequado |
| --- | --- | --- |
| Próprio sem GPU dedicada | Ryzen 9 7900, 12 núcleos / 24 threads, 64 GB, SSD NVMe | Menor investimento próprio entre as duas configurações cotadas; tolerar execução mais longa |
| Próprio com GPU | Mesma base + RTX 5060 Ti de 16 GB | Mais experimentos e menor espera no cálculo; precisa de teste com CUDA |
| Nuvem temporária, referência principal | RTX 6000 Ada, 48 GB de VRAM, até 167 GB de RAM e 10 vCPU na oferta consultada | Muita folga de memória; alugar só durante o trabalho |
| Nuvem temporária econômica | RTX 3090, 24 GB de VRAM, até 125 GB de RAM e 16 vCPU na oferta consultada | Alternativa de preço; escolher pelo tempo e custo do mesmo job |
| Nuvem sem GPU | 16 vCPU dedicadas, 64 GiB de RAM | Evitar dependência de CUDA; medir se a execução mais longa compensa |

As quantidades de RAM/vCPU e os preços na nuvem variam por oferta e região. vCPU não é sinônimo de núcleo físico. Uma oferta barata com pouca CPU ou SSD lento pode ser ruim para este pipeline. Não foi medido o desempenho desses perfis.

O cálculo abaixo mostra apenas **o tempo da parcela de percorrer árvores**, se o equipamento atingisse cada taxa. A taxa é uma hipótese, não uma capacidade atribuída a alguma placa:

| Taxa efetiva hipotética | Conta aplicada | Só árvores |
| --- | --- | --- |
| 100.000.000 visitas/s | 12,89 trilhões / taxa / 3.600 | 35,81 h |
| 300.000.000 visitas/s | 12,89 trilhões / taxa / 3.600 | 11,94 h |
| 600.000.000 visitas/s | 12,89 trilhões / taxa / 3.600 | 5,97 h |
| 1.000.000.000 visitas/s | 12,89 trilhões / taxa / 3.600 | 3,58 h |

A diferença entre 35,81 e 3,58 horas é consequência das taxas supostas, não uma promessa “CPU versus GPU”. Somam-se treinamento, preparação, rede e importação. O relato do professor refere-se a outro conjunto de tarefas e não valida essas taxas.

Para o orçamento, reservamos **48 horas de máquina GPU por ano** e, no cenário próprio sem GPU, **96 horas**. São tetos de planejamento substituíveis, não duração calculada. Há sensibilidades de 12 a 720 horas adiante. Mais de uma GPU, placas de 80 GB ou servidores rack não se justificam antes do piloto. [T1, T3, T4]

<!-- pagebreak -->

## 6. Opções B e C: o que muda no atendimento ao público

### Opção B — arquivos prontos, lidos no navegador

O servidor publica os arquivos do site, o resumo de 5 km e os setores numéricos COG. O computador do visitante baixa os trechos necessários, lê os números e aplica as cores. A consulta detalhada recupera o pixel original.

**Fluxo:** cálculo anual → produtos validados → armazenamento público/CDN → navegador com GeoTIFF.js e MapLibre.

É a alternativa mais próxima do código atual. Precisa de HTTPS, leitura parcial HTTP Range, cache e autorização CORS entre os domínios. Mantém uma parcela de processamento no dispositivo do usuário; não transfere o treino para ele.

### Opção C — imagens preparadas por um servidor de mapas

Depois do mesmo cálculo anual, um serviço como TiTiler lê os COGs, reprojeta, aplica as cores e entrega pequenas imagens prontas. Uma rota de consulta devolve os números originais quando a pessoa clica.

**Fluxo:** cálculo anual → COGs → serviço de mapas → cache/CDN → navegador com MapLibre.

A interface tende a precisar de menos leitura raster local. Em troca, surgem serviço Python permanente, proteção, monitoramento e capacidade de CPU para as requisições. É preciso adaptar o frontend e a consulta de pixels; esse backend **ainda não está implementado no site atual**. [T2]

| Critério | B | C |
| --- | --- | --- |
| Treinamento e mapas anuais | Iguais | Iguais |
| Quem prepara a imagem detalhada | Navegador | Servidor de mapas |
| GPU para atender visitas | Não | Não |
| Serviço dinâmico permanente | Não é necessário | Sim |
| Mudança no código atual | Configuração e publicação | Integração de tiles e consulta numérica |
| Ponto de atenção | Memória e desempenho do visitante | CPU, latência, cache e segurança da API |

“Servidor encarregado de tudo” não precisa significar uma máquina única e ligada o ano inteiro. Na nuvem, um projeto pode ter uma máquina temporária de cálculo e serviços pequenos de publicação. Também avaliamos a alternativa literal: um equipamento próprio executando o cálculo e hospedando tudo continuamente.

<!-- pagebreak -->

## 7. Cotação do computador próprio

Valores à vista consultados em varejistas, sem compromisso de estoque. Referências H1–H7 estão ao final com links. As demais linhas são provisões explícitas, não ofertas. Não se trata de uma pesquisa formal com três propostas por item.

| Item | Valor de referência | Natureza / fonte |
| --- | --- | --- |
| CPU Ryzen 9 7900, 12 núcleos / 24 threads | R$ 1.899,99 | Consultado [H1] |
| Placa-mãe Asus Prime B650M-R, AM5 | R$ 1.099,99 | Consultado [H2] |
| RAM Corsair 64 GB (2 × 32), DDR5-5600 | R$ 5.099,99 | Consultado [H3] |
| SSD Kingston NV3 2 TB, NVMe | R$ 2.079,99 | Consultado [H4] |
| Fonte MSI 650 W, 80 Plus Gold | R$ 359,99 | Consultado [H5] |
| Cooler de CPU; versão WOF sem cooler presumido | R$ 250,00 | Provisão |
| Gabinete ventilado e ventoinhas | R$ 350,00 | Provisão |
| RTX 5060 Ti, 16 GB, PCYes | R$ 5.095,90 | Consultado; marketplace [H6] |

As duas configurações usam a mesma base. **Próprio CPU** usa o vídeo integrado para administração e executa os modelos na CPU; **Próprio GPU** acrescenta a RTX 5060 Ti de 16 GB. A placa não é necessária para hospedar COGs ou tiles já produzidos.

A RAM de 64 GB foi cotada por folga operacional, não por ser requisito mínimo. A oferta específica ficou alta. Vale pedir propostas de kits equivalentes homologados para a placa-mãe e de uma opção de 32 GB. Um kit de 32 GB só deve substituir esta linha após medir o pico do processo completo.

O SSD de 2 TB tem folga frente aos 120 GB livres sugeridos pelo professor. Um SSD de 1 TB pode ser suficiente se caches forem controlados; reduzir a capacidade pode economizar dinheiro. Não se presume que o armazenamento precise dobrar a cada atualização.

Esta é uma **workstation em torre**, não um servidor de datacenter com memória ECC, gerenciamento remoto dedicado, fonte redundante e garantia de atendimento no local. Solicitar uma proposta montada de especificação equivalente, com nota fiscal e garantia, e comparar o preço final com a soma das peças. Esse tipo de proposta não foi obtido neste estudo.

Antes de comprar: conferir lista de memória compatível, BIOS, alimentação e comprimento da GPU, ventilação, resistência do SSD e garantia do vendedor. Memória e GPU devem funcionar estáveis, sem overclock exigido para atingir o objetivo.

<!-- pagebreak -->

## 8. O que falta além do computador

Como não há equipamento institucional, não podemos esconder os custos de instalação e continuidade. Os itens abaixo são incluídos na comparação própria; o nobreak tem referência de catálogo, não estoque confirmado.

| Item | Valor de referência | Natureza / fonte |
| --- | --- | --- |
| Disco externo de backup, 2 TB | R$ 900,00 | Provisão |
| Nobreak senoidal TS Shara 2200 VA, ref. 4452 | R$ 2.360,00 | Catálogo; reconfirmar [H7] |
| Roteador, cabos e acessórios de rede | R$ 600,00 | Provisão |
| Monitor básico, teclado e mouse para instalação | R$ 650,00 | Provisão |
| Montagem e verificação física | R$ 400,00 | Provisão |
| Adequação elétrica e aterramento: reserva | R$ 500,00 | Provisão |
| Climatização e instalação: reserva | R$ 3.000,00 | Provisão |
| Fretes para Rio Branco: reserva sem CEP cotado | R$ 1.200,00 | Provisão |

| Compra própria | Subtotal | Reserva de 15% | Total inicial |
| --- | --- | --- | --- |
| CPU, sem GPU dedicada | R$ 20.749,95 | R$ 3.112,49 | R$ 23.862,44 |
| GPU, base + RTX 5060 Ti | R$ 25.845,85 | R$ 3.876,88 | R$ 29.722,73 |

A reserva de 15% cobre variação de preço e imprevistos de compra. Não é uma cobrança de imposto adicional sobre preços de varejo já apresentados com tributos. Frete foi provisionado, não calculado com CEP. Se o ambiente já tiver climatização ou rede adequada, remover apenas os itens comprovadamente dispensáveis e recalcular.

Para manter o site ligado: provisão de **R$ 250/mês para internet e acesso público**, incluindo a necessidade de verificar IPv4/IPv6, CGNAT e autorização contratual para hospedar. Não é uma oferta de operadora; depende de endereço e contratação. Sem isso, o servidor pode funcionar localmente, mas não estar acessível pela internet.

Para energia, usamos **R$ 1,10/kWh como valor de planejamento**, não a tarifa homologada nem uma conta medida. Potência base total: 100 W na B e 120 W na C, incluindo rede e perdas; em cálculo, 250 W sem GPU e 350 W com GPU. Não confundir TDP ou potência nominal da fonte com consumo real.

Há provisão conservadora de climatização incremental de 300 W médios por 8 horas diárias. Na B com GPU: [(0,100 × 8.760) + (0,350 − 0,100) × 48 + (0,300 × 8 × 365)] × 1,10 = **R$ 1.940,40/ano**. Dimensionamento térmico e elétrico devem ser verificados no local.

O nobreak dá tempo para desligamento seguro; não garante horas de operação sem rede. O armazenamento público e a cópia de segurança são diferentes: disco espelhado ou RAID não substitui backup independente. Uma sala, vigilância e acesso físico seguro são presumidos cedidos, sem aluguel; se precisarem ser contratados, acrescentar esses custos.

<!-- pagebreak -->

## 9. Cotação da nuvem para fazer o ciclo completo

Na nuvem, a instituição não precisa comprar um computador científico. Aluga uma máquina para baixar os insumos, preparar os atributos, treinar, avaliar, prever e gerar o produto web; após conferir e salvar tudo, encerra a máquina.

| Recurso e fonte | Preço público consultado | Observação |
| --- | --- | --- |
| GPU RTX 6000 Ada, Runpod [N1] | US$ 0,99/h | Referência do orçamento; CPU/RAM incluídas na oferta, disco separado |
| GPU RTX 3090, Runpod [N1] | US$ 0,50/h | Alternativa para piloto; comparar custo total e disponibilidade |
| GPU A40, Runpod [N1] | US$ 0,59/h | Mais VRAM não significa automaticamente execução mais rápida |
| Disco temporário Runpod [N1] | US$ 0,10/GB-mês | Reserva de 500 GB apenas durante o job |
| Armazenamento R2 Standard [N3] | US$ 0,015/GB-mês | Publicação e arquivo, com franquia usada na conta |
| Backup B2 independente [N4] | US$ 6,95/TB-mês | Segunda cópia fora do armazenamento principal |
| VPS para a C, DigitalOcean [N2] | US$ 24/mês | 2 vCPU compartilhadas e 4 GiB; ponto inicial, não capacidade comprovada |

Usamos dólar orçamentário de **R$ 6,00**, acrescido de **10% de margem de câmbio e encargos**: fator efetivo de **R$ 6,60 por US$ 1**. Não é cotação PTAX nem alíquota exata de IOF ou de tributos. A fatura real e as regras de contratação precisam ser conferidas.

O preço de GPU não inclui uma promessa de tempo, SLA ou localização no Brasil. Confirmar região, classe da oferta, disco, velocidade de CPU, regras de transferência e elegibilidade da conta. Este estudo usa tarifas públicas não promocionais; não depende de bolsa ou crédito acadêmico.

Conta da rodada anual de referência:

**GPU:** 48 × US$ 0,99 = US$ 47,52.

**Disco temporário:** 500 × US$ 0,10 × 48/720 = US$ 3,33.

**Total de processamento e disco:** US$ 50,85 × R$ 6,60 = **R$ 335,63/ano**. O rateio de 720 horas é uma aproximação orçamentária; conferir a granularidade da fatura.

A alternativa de CPU dedicada com 64 GiB e 16 vCPU custa US$ 0,75/h na referência N2. Reservar 96 horas daria US$ 72 só de máquina; disco extra é adicional. Não sabemos ainda se precisaria de 96 horas. Não confundir essa máquina com a VPS pequena usada apenas para servir mapas.

<!-- pagebreak -->

## 10. Quanto custa manter a publicação?

O arquivo principal na nuvem considera 300 GB: referência de 50 GB públicos e 250 GB de dados, modelos, metadados e versões úteis. Há outra cópia de 250 GB em fornecedor independente. São envelopes de retenção, não espaço ocupado medido hoje. Caches regeneráveis expiram; guardar indefinidamente todo intermediário exige mais espaço.

| Parcela da opção B na nuvem | Conta | Valor anual |
| --- | --- | --- |
| Arquivo e produtos, R2 | (300 − 10) × US$ 0,015 × 12 × 6,60 | R$ 344,52 |
| Backup independente, B2 | 250 × US$ 0,00695 × 12 × 6,60 | R$ 137,61 |
| Domínio | Provisão, não preço confirmado | R$ 60,00 |
| Rodada anual GPU + disco | Conta da seção anterior | R$ 335,63 |
| Frontend estático | Plano sem Functions, dentro dos limites [N5] | R$ 0,00 |
| Total B de referência | Sem leituras excedentes e sem trabalho técnico | R$ 877,76 |

Na C, acrescentamos **R$ 1.900,80/ano** para a VPS de mapas, chegando a **R$ 2.778,56/ano**. Configuração do serviço pode ser reconstruída a partir do código; os produtos e metadados entram no backup já reservado. Uma segunda VPS de alta disponibilidade, atendimento gerenciado e proteção paga não estão incluídos.

As franquias de leitura do R2 cobrem o cenário baixo, mas não tornam o serviço ilimitado. O frontend gratuito depende de termos e limites vigentes. Se a instituição exigir contrato pago de frontend de US$ 20/mês, acrescentar **R$ 1.584/ano**. Cloudflare Workers/Functions ou outros serviços extras não são gratuitos por estarem ao lado do R2.

No equipamento próprio, as despesas anuais incluem energia, R$ 3.000 de internet, R$ 137,61 de backup externo, R$ 60 de domínio e R$ 600 de reserva para peças, bateria e manutenção física. A reserva não é um desembolso garantido todo ano; evita assumir manutenção zero.

Neste uso anual, manter a máquina e o ambiente disponíveis todos os dias pesa mais que a eletricidade das poucas horas de cálculo. Por isso a opção CPU e a GPU têm gasto de energia anual parecido nas reservas adotadas.

Para o crescimento, a primeira referência pode ser recalculada aumentando os envelopes de dados e o tráfego. Não foi incluído comprar a cada ano outro servidor. Todos os cenários mantêm um único ciclo anual e publicam os resultados continuamente.

<!-- pagebreak -->

## 11. Comparação de custo em 1, 3 e 5 anos

Primeiro, a conta de **infraestrutura e reservas**, sem valorar o tempo de quem instala e administra. A compra própria já inclui frete provisionado, instalação física e margem de 15%.

| Cenário | Anual | 1 ano | 3 anos | 5 anos |
| --- | --- | --- | --- | --- |
| Nuvem + opção B | R$ 877,76 | R$ 877,76 | R$ 2.633,29 | R$ 4.388,81 |
| Nuvem + opção C | R$ 2.778,56 | R$ 2.778,56 | R$ 8.335,69 | R$ 13.892,81 |
| Próprio CPU + B | R$ 5.740,65 | R$ 29.603,09 | R$ 41.084,39 | R$ 52.565,69 |
| Próprio CPU + C | R$ 5.931,26 | R$ 29.793,70 | R$ 41.656,22 | R$ 53.518,73 |
| Próprio GPU + B | R$ 5.738,01 | R$ 35.460,74 | R$ 46.936,76 | R$ 58.412,78 |
| Próprio GPU + C | R$ 5.929,67 | R$ 35.652,40 | R$ 47.511,75 | R$ 59.371,10 |

As configurações próprias fazem tudo no local e ficam ligadas para hospedar o site. A coluna “CPU” significa sem GPU dedicada, não ausência de processamento. Nas opções de nuvem a máquina científica é encerrada após o uso; o site e os arquivos continuam disponíveis.

A referência GPU própria não está sendo comparada como se entregasse a mesma velocidade da RTX 6000 Ada. As horas são reservas independentes; só o piloto pode medir quantas horas de um equipamento equivalem às do outro. Há folga de 48 horas na nuvem apesar do relato menor do professor.

**Fórmula:** custo em Y anos = compra inicial + Y × despesas anuais. Valores constantes, sem juros, inflação, valorização futura do dólar ou desconto financeiro. Valor de revenda foi adotado como zero. Não se soma depreciação novamente: a compra inteira já está na conta.

Não há aluguel de sala, link de contingência, gerador, SLA contratual ou plantão 24 horas. Uma falha prolongada não tem custo financeiro estimado neste estudo, mas pode ter custo institucional importante. O servidor único próprio é um ponto único de falha, inclusive durante manutenção.

O resultado favorece a nuvem porque o processamento é raro e não existe uma estrutura física disponível. Não é uma conclusão universal de que nuvem sempre custa menos: uma GPU alugada continuamente muda completamente a conta.

<!-- pagebreak -->

## 12. O custo do trabalho de uma pessoa

Nenhum desses cenários dispensa responsabilidade técnica. É necessário atualizar versões, conferir dados, investigar falhas, revisar resultados e testar restauração de backup.

Para não esconder esse custo, usamos **R$ 100/h como referência ilustrativa**, não como cotação de profissional. As horas iniciais consideram adaptar caminhos e ambiente, automatizar o ciclo, configurar segurança e publicar. As horas anuais incluem acompanhamento do job, revisão dos produtos e administração periódica; não são horas de máquina.

| Cenário | Horas técnicas iniciais | Horas técnicas por ano |
| --- | --- | --- |
| Nuvem B | 64 | 28 |
| Nuvem C | 104 | 40 |
| Próprio B, CPU ou GPU | 80 | 40 |
| Próprio C, CPU ou GPU | 120 | 52 |

As diferenças da C incluem integrar e manter o backend de mapas; as do próprio incluem rede e operação local. Montagem física já está no orçamento do hardware e não é cobrada novamente nessas horas. São provisões a revisar com o responsável, não um cronograma fechado.

| Cenário | Implantação técnica | Trabalho / ano | Total 3 anos | Total 5 anos |
| --- | --- | --- | --- | --- |
| Nuvem + opção B | R$ 6.400,00 | R$ 2.800,00 | R$ 17.433,29 | R$ 24.788,81 |
| Nuvem + opção C | R$ 10.400,00 | R$ 4.000,00 | R$ 30.735,69 | R$ 44.292,81 |
| Próprio CPU + B | R$ 8.000,00 | R$ 4.000,00 | R$ 61.084,39 | R$ 80.565,69 |
| Próprio CPU + C | R$ 12.000,00 | R$ 5.200,00 | R$ 69.256,22 | R$ 91.518,73 |
| Próprio GPU + B | R$ 8.000,00 | R$ 4.000,00 | R$ 66.936,76 | R$ 86.412,78 |
| Próprio GPU + C | R$ 12.000,00 | R$ 5.200,00 | R$ 75.111,75 | R$ 97.371,10 |

**Fórmula ampliada:** infraestrutura + horas iniciais × R$ 100 + anos × horas anuais × R$ 100.

Se o trabalho for feito pela própria equipe sem cobrança adicional, use a tabela anterior para a saída de caixa, mas reserve pessoas e tempo. Se for terceirizado, o desembolso real dependerá da proposta. Um SLA com plantão, consultoria científica ou desenvolvimento de novas fontes de clima não deve ser considerado coberto automaticamente por essas horas.

<!-- pagebreak -->

## 13. Público desconhecido: três cenários de acesso

Não há previsão de visitas. Por isso os números abaixo são **simulações**, não medições do site nem promessa de quantos usuários a máquina suporta.

Hipótese B: 150 MB e 500 leituras de arquivos por visita. Hipótese C: 20 MB por visita, 100 tiles, cache com 80% de acerto e 0,05 segundo de CPU por tile não atendido pelo cache. São referências substituíveis por medição. O basemap externo pode ter consumo, termos e custos próprios; não está quantificado.

| Visitas / mês | B: transferência | C: transferência | C: CPU estimada |
| --- | --- | --- | --- |
| 1.000 | 150 GB/mês | 20 GB/mês | 0,28 h/mês |
| 10.000 | 1.500 GB/mês | 200 GB/mês | 2,78 h/mês |
| 100.000 | 15.000 GB/mês | 2.000 GB/mês | 27,78 h/mês |

Na B, 1.000 visitas geram 500 mil leituras; 10.000 geram 5 milhões; 100.000 geram 50 milhões. A franquia mensal é de 10 milhões. Sem cache de CDN, o maior cenário produziria 40 milhões excedentes × US$ 0,36 × 6,60 = **R$ 95,04/mês** de leituras. Outras operações, como muitas gravações, são separadas. [N3]

Na C, a conta de CPU é: visitas × 100 tiles × 20% sem cache × 0,05 s / 3.600. A média mensal pode parecer pequena e ainda haver congestionamento em um evento: 20 pessoas pedindo 100 tiles quase ao mesmo tempo exigem muito mais que a média.

A VPS de 4 GiB/2 vCPU é apenas uma entrada para piloto. Se picos, memória ou latência não passarem no teste, uma VPS de 8 GiB/4 vCPU a US$ 48/mês adiciona **R$ 1.900,80/ano** à referência C. Não há capacidade comprovada para 100 mil visitas numa única VPS pequena. [N2]

Para servidor próprio, 150 GB enviados num mês equivalem a só 0,46 Mbit/s em média, mas um download de 150 MB num link de upload de 20 Mbit/s leva pelo menos 60 segundos. Dez downloads dividindo esse link podem levar perto de 10 minutos cada. Latência, perdas e tarefas do local pioram isso. Conferir **upload**, não apenas o número anunciado de download.

A decisão deve considerar também tempo de primeira imagem, resposta ao clique e funcionamento em celulares, não somente visitas mensais.

<!-- pagebreak -->

## 14. O que pode mudar a conclusão?

### Se o processamento demorar mais

| Reserva de máquina / ano | Infra anual B | Infra anual C |
| --- | --- | --- |
| 12 h | R$ 626,04 | R$ 2.526,84 |
| 48 h | R$ 877,76 | R$ 2.778,56 |
| 72 h | R$ 1.045,58 | R$ 2.946,38 |
| 168 h | R$ 1.716,84 | R$ 3.617,64 |
| 720 h | R$ 5.576,61 | R$ 7.477,41 |

Cada linha aumenta as horas pagas do job anual e do disco temporário, mantendo publicação, dados e backup iguais. Mesmo uma semana de GPU por ano ainda é um cenário muito diferente de alugar GPU permanentemente.

Uma RTX 6000 Ada de US$ 0,99/h ligada 24 horas por dia custaria **R$ 57.237,84/ano só de máquina**, antes de disco e publicação. Não é a arquitetura recomendada. Deixar 500 GB de volume de rede a US$ 0,07/GB-mês guardados o ano todo acrescentaria **R$ 2.772/ano**, se esse volume for contratado além do arquivo já previsto. Encerrar GPU não significa apagar automaticamente discos cobrados. [N1]

### Se mudarem dólar, energia ou estrutura local

- Dólar-base a R$ 4,80 ou R$ 7,20, com a mesma margem de 10%, leva a nuvem B a cerca de **R$ 714,21** ou **R$ 1.041,31 por ano**. Domínio continua em reais.
- Energia de R$ 0,80 ou R$ 1,40/kWh leva a energia própria B/GPU de R$ 1.411,20 a R$ 2.469,60 por ano. O consumo real precisa ser medido.
- Se já existirem internet e sala climatizada adequadas, podem cair custos próprios. Aqui não foram considerados gratuitos: não há equipamento institucional disponível e as condições do local não foram comprovadas.
- Se toda a compra GPU custasse metade, mantendo a operação, a infraestrutura própria B ainda somaria **R$ 43.551,41 em cinco anos**. É uma sensibilidade matemática, não uma cotação de equipamento mais barato.
- Se novos modelos, regiões ou reprocessamentos se tornarem semanais, a compra pode passar a fazer sentido. O projeto atual não tem essa demanda.

Uma conta simplificada de equilíbrio para GPU própria, em cinco anos, fica na ordem de **1.656–1.727 horas anuais equivalentes de nuvem** nas hipóteses deste estudo. Considera custo de compra diluído, operação local e uma hora local igual ou até duas vezes mais lenta que a nuvem; não inclui trabalho técnico. Sem benchmark a equivalência não é conhecida. Não usar esse número como garantia de retorno.

<!-- pagebreak -->

## 15. O que ainda precisa ser preparado para a rotina anual

O código científico possui comandos e mecanismos de retomada, mas o site atual **importa GeoTIFFs prontos**. Ele não é hoje um serviço que busca automaticamente todos os dados e treina sozinho a cada ano. Essa implantação está prevista nas horas técnicas, não deve ser dada como concluída.

1. **Fechar as fontes:** MapBiomas tem URLs no código; clima aparece em arquivos locais, com caminhos e produtos herdados. Identificar a fonte oficial, credenciais quando houver, licença, metadados e procedimento de atualização climática. Hospedar uma máquina não resolve a ausência do insumo.
2. **Verificar o calendário científico:** só publicar o ano vigente quando os dados defasados exigidos estiverem disponíveis. Mapas anuais podem ser lançados meses depois do encerramento do ano anterior. Em 2026, a Coleção 11 cobre até 2025. Não prometer atualização em 1º de janeiro. [D1, D2]
3. **Portar o ambiente:** substituir caminhos do computador do professor por configuração própria; fixar Python 3.11, XGBoost 3.2.0, GDAL/Rasterio, driver NVIDIA e dependências. Guardar cópia das bases herdadas ainda referenciadas.
4. **Separar tarefas:** cálculo em fila, sem expor portas científicas na internet. Se tudo for local, reservar CPU/RAM ao site, limitar threads e prioridade do treino e usar pastas públicas somente de leitura.
5. **Automatizar com controles:** agendador verifica dados, prepara, treina e gera o produto; registra logs, versões, hashes, tempo, pico de RAM e VRAM. Checkpoint não significa que toda etapa tem retomada fina; uma etapa pode precisar reiniciar inteira.
6. **Publicar por versão:** gerar numa pasta temporária, conferir máscaras e valores, guardar a versão anterior e trocar o endereço ativo somente após aprovação. Falha não deve derrubar o mapa anterior.
7. **Proteger e recuperar:** HTTPS, firewall, chaves fora do frontend, cópias em outro fornecedor/local, acesso com segundo fator e teste de restauração. Na C, não aceitar URL arbitrária para leitura raster: restringir aos produtos autorizados.

O Clima observado de 2025 pode continuar público sem refazer todo seu histórico. Para atualizar também essa aba anualmente, acrescentar aquisição e validação das fontes observadas, não confundir com os arquivos climáticos usados pelo modelo.

<!-- pagebreak -->

## 16. Decisão sugerida e piloto antes de comprar

**Melhor custo-benefício neste momento: nuvem temporária + opção B.** Entrega o ciclo científico completo sem comprar máquina, permite desligar o recurso caro após o job e aproveita a integração já existente do frontend. O custo de administração e adaptação tende a superar o pequeno gasto anual com GPU, por isso padronizar o processo é mais importante que economizar centavos por hora.

**Quando considerar C:** se o teste com dispositivos do público mostrar dificuldade na leitura dos COGs, se houver necessidade de consultas centralizadas ou de controlar a exposição dos rasters. Não escolher C apenas porque “servidor de mapas parece mais profissional”: ela precisa trazer um ganho observável. A B também exige que a distribuição de dados funcione bem.

**Se a compra for obrigatória:** pedir propostas de uma torre com CPU moderna de 8–12 núcleos, 32 GB testados ou 64 GB por folga, SSD de 1–2 TB, backup e nobreak adequado. Para uma rodada anual, começar sem GPU pode ser racional se houver tolerância à espera. Acrescentar a GPU NVIDIA só com resultado de medição ou perspectiva real de uso frequente. Não pagar por rack, duas CPUs, duas GPUs ou centenas de GB de RAM sem necessidade comprovada.

O orçamento próprio cotado é conservador e inclui estrutura que pode não ser toda necessária. Pedir ao menos propostas completas equivalentes e confirmar os itens de RAM, nobreak e climatização antes de qualquer compra. Uma variante enxuta de 32 GB, 1 TB e nobreak menor precisa de **nova cotação**; não foi inventado um preço para ela.

### Piloto de decisão

Reservar até **R$ 500 de infraestrutura**, além das horas técnicas, para um primeiro job controlado na nuvem. Medir os mesmos dados e parâmetros com cache frio e quente. Não executar benchmark de outra modalidade, como imagens geradas por IA ou jogos, para decidir este caso.

- Registrar tempo por etapa, exemplos por segundo, pixels por segundo, RAM, VRAM, disco, bytes transferidos e custo pago. Conferir tolerância numérica e metadados ao mudar CPU/GPU; não exigir identidade binária sem fundamento.
- Extrapolar um teste de bloco: tempo de mapa ≈ 172.340.796 / pixels por segundo, mais abertura e fechamento. Somar os tempos de treino e importação separadamente; uma amostra não mede tudo.
- Para B/C, testar clique e pan em celular e computador, HTTP Range, cache e pequenos picos de concorrência. Registrar latência e erros; escolher tamanho do servidor com esses resultados.
- Aprovar a atualização e a capacidade mínima de publicação antes de encerrar a máquina e expirar discos temporários. Nunca apagar a única cópia de um resultado ou insumo.

**Critério final:** comparar reais por ciclo anual completo e qualidade de atendimento ao público. Para a demanda informada — uma rodada anual, sem estrutura institucional e sem estimativa de público — não há evidência que justifique imobilizar dinheiro num servidor potente próprio agora.

<!-- pagebreak -->

## Referências e rastreabilidade

Consulta pública realizada em 26/10/2026. Preços podem mudar e não incluem compromisso de estoque, frete real ao Acre, contratação institucional, SLA ou regras fiscais particulares. Catálogos com bloqueio ou redirecionamento não foram usados como se fossem confirmação de estoque.

**[H1] Terabyte — Ryzen 9 7900.** R$ 1.899,99 à vista; frete grátis anunciado não inclui Acre. [Abrir fonte](https://www.terabyteshop.com.br/produto/41377/processador-amd-ryzen-9-7900-37ghz-54ghz-turbo-12-cores-24-threads-am5-100-100000590wof).

**[H2] Pichau — Asus Prime B650M-R.** R$ 1.099,99 no PIX. [Abrir fonte](https://www.pichau.com.br/placa-mae-asus-prime-b650m-r-ddr5-socket-am5-m-atx-chipset-amd-b650-prime-b650m-r).

**[H3] Pichau — Corsair Vengeance 64 GB.** R$ 5.099,99 no PIX. Oferta específica, não o menor preço nacional; conferir alternativas equivalentes. [Abrir fonte](https://www.pichau.com.br/memoria-corsair-vengeance-64gb-2x32gb-ddr5-5600mhz-c40-cinza-cmk64gx5m2b5600z40).

**[H4] Pichau — Kingston NV3 2 TB.** R$ 2.079,99 no PIX na página aberta; o resultado de busca ainda mostrava R$ 2.349,99. [Abrir fonte](https://www.pichau.com.br/ssd-kingston-nv3-2tb-m-2-2280-pcie-nvme-leitura-6000mb-s-gravacao-5000mb-s-snv3s-2000g).

**[H5] Pichau — MSI Mag A650GN II.** R$ 359,99 no PIX. [Abrir fonte](https://www.pichau.com.br/fonte-msi-mag-a650gn-ii-650w-80-plus-gold-atx-3-1-preto-306-7zpbz23-ce0).

**[H6] KaBuM — PCYes RTX 5060 Ti 16 GB.** R$ 5.095,90 no PIX; anúncio de marketplace. Conferir vendedor, estoque, garantia e dimensões. [Abrir fonte](https://www.kabum.com.br/produto/1064793/placa-de-video-pcyes-nvidia-geforce-rtx-5060-ti-16gb-gddr7-dlss-ray-tracing-pvrtx5060tib2f16g).

**[H7] KaBuM — catálogo de nobreaks.** Catálogo exibia TS Shara 4452 a R$ 2.360,00. Página individual bloqueou consulta; estoque e valor exigem confirmação. [Abrir fonte](https://www.kabum.com.br/energia/protetor-eletronico/nobreak).

**[N1] Runpod — GPU e armazenamento.** Preços públicos por hora: RTX 6000 Ada US$ 0,99; A40 US$ 0,59; RTX 3090 US$ 0,50. Disco de execução US$ 0,10/GB-mês; rede padrão abaixo de 1 TB US$ 0,07/GB-mês. Disponibilidade, região, categoria e fatura precisam ser conferidas na contratação. [Abrir fonte](https://www.runpod.io/pricing).

**[N2] DigitalOcean — máquinas virtuais.** Basic 4 GiB / 2 vCPU: US$ 24/mês; 8 GiB / 4 vCPU: US$ 48/mês. General Purpose 64 GiB / 16 vCPU: US$ 0,75/h. VPS Basic usa CPU compartilhada; não equivale a núcleos físicos dedicados. [Abrir fonte](https://www.digitalocean.com/pricing/droplets).

**[N3] Cloudflare R2 — preços.** Standard US$ 0,015/GB-mês, 10 GB-mês incluídos; 10 milhões de leituras mensais incluídas; excedente US$ 0,36/milhão; saída direta sem tarifa de tráfego. Considerar arredondamento e outros serviços separadamente. [Abrir fonte](https://developers.cloudflare.com/r2/pricing/).

**[N4] Backblaze B2 — backup independente.** US$ 6,95/TB por 30 dias, sem cobrança de transações; saída incluída até 3 vezes o volume armazenado. Modelo de cálculo usa 1 TB = 1.000 GB e não depende de franquia gratuita. [Abrir fonte](https://www.backblaze.com/cloud-storage/pricing).

**[N5] Cloudflare Pages — arquivos estáticos.** Solicitações de arquivos estáticos sem Functions são gratuitas. Limites de build, tamanho e termos do plano continuam aplicáveis. [Abrir fonte](https://developers.cloudflare.com/pages/functions/pricing/).

**[T1] XGBoost — uso de GPU.** Treinamento e previsão com CUDA; dados quantizados e memória de trabalho disputam VRAM. RAM, VRAM e vCPU não são intercambiáveis. [Abrir fonte](https://xgboost.readthedocs.io/en/release_3.2.0/gpu/index.html).

**[T2] TiTiler — mosaicos dinâmicos.** Servidor lê trechos dos COGs, reprojeta, aplica cores e codifica imagens; acrescenta latência e operação em relação a arquivos estáticos. [Abrir fonte](https://developmentseed.org/titiler/user_guide/dynamic_tiling/).

**[T3] AMD — especificações Ryzen 9 7900.** 12 núcleos, 24 threads, plataforma AM5. TDP não é o consumo medido do computador completo. [Abrir fonte](https://www.amd.com/en/products/processors/desktops/ryzen/7000-series/amd-ryzen-9-7900.html).

**[T4] NVIDIA — família RTX 5060.** RTX 5060 Ti disponível com 8 ou 16 GB. Cotação deste estudo é da variante de 16 GB; resultados de jogos não medem este pipeline. [Abrir fonte](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5060-family/).

**[D1] MapBiomas — downloads de mapas anuais.** Fonte de mapas anuais; a cobertura deve ser conferida antes de programar a atualização. [Abrir fonte](https://brasil.mapbiomas.org/downloads/mapas-para-download-geotiff/).

**[D2] MapBiomas — lançamento da Coleção 11.** A coleção publicada em 2026 cobre até 2025. Atualização anual não garante disponibilidade dos insumos em 1º de janeiro. [Abrir fonte](https://brasil.mapbiomas.org/mapbiomas-lanca-colecao-11-de-cobertura-e-uso-da-terra/).

### Evidências do próprio repositório

| Arquivo | Informação utilizada |
| --- | --- |
| entrega_professor_v4/README.txt | Ambiente, disco livre sugerido e relato de duração no hardware do professor |
| entrega_professor_v4/1_codigo/config_risco_30m_v4_fogo.json | Preditores, amostragem, blocos, suavização, GPU e limite de memória |
| entrega_professor_v4/1_codigo/pipeline/r30_publicos.py | Recortes por leitura remota e preparação de dados públicos |
| entrega_professor_v4/1_codigo/pipeline/r30_atributos.py | Montagem das matrizes e defasagens |
| entrega_professor_v4/1_codigo/pipeline/r30_treino.py | Treino, correção de amostragem, calibração e floresta em lotes |
| entrega_professor_v4/1_codigo/pipeline/r30_avaliacao.py | Aplicação em blocos e 16 perturbações climáticas |
| entrega_professor_v4/2_resultados/treino_MapBiomas_Fogo/tabelas/amostras_30m.csv | Contagem de exemplos de treino |
| entrega_professor_v4/2_resultados/treino_MapBiomas_Fogo/tabelas/banco_vencedores.csv | Árvores e profundidades vencedoras |
| incendio/importar_risco_professor_v4.py | Geração de agregado e COGs sem novo treino |
| incendio/produtos/risco/v4/2025 e /2026 | Manifestos, índices, contagens e tamanhos declarados |
| frontend/src/data/riskRaster.worker.ts e frontend/README.md | Leitura no navegador e opções atuais de distribuição |

Os fontes científicos foram inspecionados como evidência, sem modificar a entrega recebida. Produtos, checkpoints e dados ignorados pelo Git podem continuar necessários: não são descartáveis apenas por não estarem versionados.

### Como atualizar as contas

Editar `premissas_e_cotacoes.json` e executar `python3 docs/infraestrutura/calcular_cenarios.py`. O cálculo usa biblioteca padrão e lê as contagens científicas recebidas. Não executa treinamento, não liga máquinas na nuvem e não altera os produtos do site.

O gerador dos documentos usa python-docx e ReportLab. PDF e Word são produzidos do mesmo conteúdo e dos mesmos cálculos. Arquivos de publicação, preços consultados e fórmulas ficam separados para permitir revisão.

<!-- pagebreak -->

## Glossário rápido

| Termo | Em linguagem simples |
| --- | --- |
| CPU | Processador principal. Faz o trabalho geral, incluindo preparar dados e servir mapas. |
| GPU | Placa capaz de executar muitas operações em paralelo. Pode acelerar os modelos; não é necessária para entregar arquivos prontos. |
| RAM e VRAM | Memória de trabalho da máquina e memória da placa de vídeo. Não são o espaço do SSD. |
| SSD NVMe | Disco rápido para ler e gravar dados. Ele continua guardando arquivos quando a máquina é desligada. |
| vCPU | Unidade de processamento oferecida numa máquina virtual; pode compartilhar um núcleo físico com outros clientes. |
| GeoTIFF e COG | Arquivos com números e sua posição na Terra. O COG é organizado para ler partes pela internet. |
| Tile | Pequena imagem quadrada que, junto com outras, compõe o mapa da tela. |
| Cache | Cópia temporária que evita refazer ou baixar algo repetidamente. Não substitui backup. |
| CDN | Rede de distribuição que aproxima cópias dos arquivos dos visitantes. |
| HTTP Range e CORS | Mecanismos para pedir só partes de um arquivo e permitir sua leitura por um site de outro domínio. |
| Job e checkpoint | Uma tarefa de processamento e um ponto salvo que pode ajudar a retomá-la. |
| Benchmark | Teste medido com dados e tarefas definidos, usado para comparar equipamentos de forma justa. |
| Retenção | Decisão de por quanto tempo guardar arquivos, versões e cópias. |
| TCO | Custo total de possuir e operar uma solução no período, não apenas o preço de compra. |
| SLA | Compromisso contratual de atendimento ou disponibilidade. Não é garantido só porque um site está na nuvem. |

Nenhum dos preços garante por si só a qualidade do resultado científico. Isso depende das fontes, do protocolo, da ausência de informações futuras no treino e da avaliação adequada. Hospedagem confiável faz o resultado chegar ao público; não o transforma automaticamente em previsão operacional validada.
