import type { SummaryMethod } from './riskAggregation'

interface TechnicalExplanation {
  definition: string
  equation: string
  symbols: [string, string][]
  procedure: string[]
  interpretation: string
  limitations: string
}

export const AGGREGATION_HELP: Record<SummaryMethod, TechnicalExplanation> = {
  mean: {
    definition: 'Média aritmética dos índices percentis recebidos de todos os pixels válidos do grupo. Cada observação recebe peso 1/n.',
    equation: 'R_média = (1/n) Σᵢ rᵢ = (Σc n_c × μ_c) / n',
    symbols: [['rᵢ', 'Índice percentil estadual do pixel i, de 0 a 100.'], ['n', 'Quantidade de pixels válidos do grupo.'], ['n_c e μ_c', 'Quantidade de pixels e média dos índices dentro da classe c.']],
    procedure: ['Somar os índices de todos os pixels válidos, preservando inclusive índices iguais a zero.', 'Dividir essa soma por n. A forma por classes é equivalente porque cada média de classe é ponderada por sua contagem.', 'Aplicar os cortes 50, 70, 90 e 95 ao resultado para escolher a cor do resumo.'],
    interpretation: 'O resultado é a posição estadual média dos pixels. O grupo não é novamente ranqueado entre os demais grupos de 5 km.',
    limitations: 'Misturas de pixels baixos e muito altos podem produzir uma média moderada. A média não identifica a classe mais frequente, a maioria dos pixels nem a proporção de área em cada classe.',
  },
  mode: {
    definition: 'Moda categórica: escolhe a classe de percentil com a maior contagem de pixels. Não procura o valor numérico de índice que mais se repete.',
    equation: 'c* = arg max_c n_c; D = 100 × n_c* / n',
    symbols: [['n_c', 'Contagem de pixels válidos classificados na faixa c.'], ['c*', 'Classe selecionada; em empate, a classe de menor índice.'], ['D', 'Proporção de pixels da classe selecionada, em %.']],
    procedure: ['Classificar os índices nas cinco faixas fixas e contar os pixels de cada faixa.', 'Selecionar a maior contagem. Se mais de uma classe tiver essa contagem, desempatar pela classe mais baixa.', 'Colorir diretamente pela categoria selecionada e informar sua proporção. Não atribuir um índice fictício, como o ponto médio da faixa.'],
    interpretation: 'Essa cor coincide com a classe da maior quantidade possível de pixels do grupo quando se permite apenas uma cor por grupo.',
    limitations: 'Classe mais frequente não significa maioria absoluta: maioria exige n_c > n/2. Um grupo com máximo de 50% ou menos é sinalizado como misto. O resultado também depende das faixas escolhidas, que têm larguras diferentes.',
  },
  median: {
    definition: 'Quantil exato de ordem q = 0,5 dos índices dos pixels do grupo, usando a inversa da distribuição empírica (inverted_cdf).',
    equation: 'r_(1) ≤ … ≤ r_(n); k = ceil(0,5 × n); R_mediana = r_(k)',
    symbols: [['r_(k)', 'Índice do pixel na posição k da sequência ordenada, com posições começando em 1.'], ['ceil(x)', 'Menor inteiro maior ou igual a x: arredondamento para cima.'], ['q', 'Fração da distribuição dentro do grupo; não é um limiar do ranking estadual.']],
    procedure: ['Considerar os índices originais dos pixels válidos do grupo, sem usar as versões reduzidas do raster.', 'Localizar a estatística de ordem k por partição dos valores em arquivo temporário; isso dá o mesmo valor que ordenar e consultar a posição k.', 'Preservar o índice observado nesse pixel, sem interpolar entre observações. Quando n é par, essa convenção seleciona o central inferior, em vez de calcular a média dos dois centrais.'],
    interpretation: 'Representa um valor central da distribuição espacial. Pela convenção adotada, pelo menos metade dos índices é menor ou igual à mediana. Empates podem fazer essa parcela ultrapassar 50%.',
    limitations: 'Outras convenções de mediana podem dar um resultado diferente, especialmente em grupos pequenos. O valor é exato em relação aos pixels recebidos e à convenção adotada; não informa sozinho a proporção de pixels Muito alto.',
  },
  concentration: {
    definition: 'Fração dos pixels válidos cujo índice estadual é maior ou igual a 90, reunindo as classes Alto e Muito alto.',
    equation: 'C₉₀ = (100/n) Σᵢ 1(rᵢ ≥ 90) = 100 × (n_Alto + n_Muito_alto) / n',
    symbols: [['1(condição)', 'Indicadora: vale 1 quando a condição é verdadeira e 0 caso contrário.'], ['n_Alto + n_Muito_alto', 'Pixels nos intervalos [90,95) e [95,100], incluindo o limite 90.'], ['C₉₀', 'Porcentagem dos pixels válidos do grupo, não porcentagem de chance de incêndio.']],
    procedure: ['Somar as contagens de Alto e Muito alto, sem alterar os índices dos pixels.', 'Dividir pelo total de pixels válidos do grupo e multiplicar por 100.', 'Aplicar a legenda contínua própria de cobertura de 0% a 100%, sem reutilizar as classes de percentil para esse número.'],
    interpretation: 'Descreve a concentração espacial de pixels altos. A contagem aproxima a fração da área porque os pixels têm áreas locais muito semelhantes.',
    limitations: 'A proporção considera somente a área válida e usa contagens, não a soma exata das áreas geodésicas. O limite 90 é relativo ao ranking daquele ano/modelo; não é um limiar físico absoluto de ocorrência de fogo.',
  },
  p75: {
    definition: 'Quantil exato de ordem q = 0,75 dos índices do grupo, com a mesma convenção inverted_cdf da mediana.',
    equation: 'r_(1) ≤ … ≤ r_(n); k = ceil(0,75 × n); R_P75 = r_(k)',
    symbols: [['q = 0,75', 'Posição relativa dentro da lista de pixels do grupo.'], ['k', 'Posição inteira, começando em 1, obtida por arredondamento para cima.'], ['r_(k)', 'Índice estadual original do pixel nessa posição.']],
    procedure: ['Reunir os índices válidos na resolução original e calcular k = ceil(0,75 × n).', 'Usar partição para encontrar o valor da posição k, sem interpolação e sem estimá-lo por um histograma.', 'Classificar o índice retornado nos cortes usuais para colorir este resumo analítico.'],
    interpretation: 'Pelo menos 75% dos índices são menores ou iguais ao P75; com empates, essa proporção pode ser maior. Um P75 de 98 não significa que 75% da área tem risco Muito alto: significa que o quartil superior foi localizado no índice estadual 98.',
    limitations: 'Privilegia a parte superior da distribuição e pode intensificar a cor de grupos mistos. Não identifica necessariamente a maioria nem mede probabilidade de incêndio.',
  },
  area_mean: {
    definition: 'Média dos índices ponderada pela área geodésica de cada pixel nativo. O peso de um pixel é sua área dividida pela área válida total do grupo.',
    equation: 'A = Σᵢ aᵢ; wᵢ = aᵢ/A; R_área = Σᵢ wᵢ rᵢ = Σᵢ(aᵢ rᵢ)/A',
    symbols: [['aᵢ', 'Área em m² do quadrilátero dos quatro cantos do pixel sobre o elipsoide WGS84.'], ['A', 'Soma das áreas dos pixels válidos atribuídos ao grupo.'], ['wᵢ', 'Peso normalizado por área; a soma dos pesos é 1.']],
    procedure: ['Obter os quatro cantos de cada pixel da grade geográfica EPSG:4326 e calcular a área geodésica WGS84.', 'Somar área × índice e somar as áreas válidas. O exportador aproveita que pixels da mesma linha têm a mesma área nessa grade.', 'Dividir as duas somas. O peso vem dos pixels nativos, não da área do polígono visual recortado.'],
    interpretation: 'Um pixel de área maior recebe influência proporcionalmente maior. Se as áreas forem iguais, o resultado coincide exatamente com a média aritmética.',
    limitations: 'Em um grupo de 5 km as áreas são quase iguais, por isso a mudança costuma ser muito pequena. Essa ponderação não elimina a mistura entre classes nem transforma o resumo em um novo ranking.',
  },
  local_rarity: {
    definition: 'Média ponderada em que cada classe ocupada dentro do grupo recebe o mesmo peso total, independentemente de quantos pixels ela contém.',
    equation: 'wᵢ = 1/n_c(i); O = {c: n_c > 0}; K = |O|; R_local = Σᵢ(wᵢrᵢ)/Σᵢwᵢ = (1/K) Σc∈O μ_c',
    symbols: [['c(i)', 'Classe do pixel i.'], ['O e K', 'Conjunto e quantidade de classes que possuem pelo menos um pixel no grupo.'], ['μ_c', 'Média dos índices dos pixels da classe c; uma classe vazia não recebe média zero.']],
    procedure: ['Calcular a média dos índices dentro de cada classe ocupada.', 'Dar a cada pixel peso inverso à contagem local de sua classe. Assim, a soma dos pesos por classe é 1 e o peso normalizado por classe é 1/K.', 'Calcular a média simples das K médias de classe. Classes vazias ficam fora da soma e do denominador.'],
    interpretation: 'Equilibra a influência matemática das classes presentes. Uma classe rara no grupo pode pesar tanto quanto uma classe que ocupa a maior parte dele.',
    limitations: 'Esse equilíbrio altera a representação da população de pixels. A medida pode subir ou cair: se Muito alto for a classe dominante, ela perderá influência relativa. É um índice experimental, sem correção ou calibração de probabilidade.',
  },
  state_rarity: {
    definition: 'Média dos índices com pesos inversos às frequências das classes no conjunto de pixels válidos do Acre, específicas de ano e modelo.',
    equation: 'f_c = N_c/N; wᵢ = 1/f_c(i); Z = Σc(n_c/f_c); R_estado = [Σc(n_c μ_c/f_c)] / Z',
    symbols: [['N e N_c', 'Total estadual de pixels válidos e contagem estadual da classe c.'], ['f_c', 'Frequência estadual como fração entre 0 e 1.'], ['n_c/f_c e Z', 'Peso total da classe dentro do grupo e soma de todos esses pesos.']],
    procedure: ['Calcular f_c a partir de todos os pixels estaduais daquele ano/modelo, nunca somente da viewport.', 'Atribuir peso 1/f_c a cada pixel de uma classe presente. Dentro do grupo, o peso total dessa classe é n_c/f_c.', 'Somar média de classe × peso total de classe e dividir por Z. Classes sem pixels no grupo não contribuem.'],
    interpretation: 'Classes raras no estado recebem mais influência por pixel. Isso é diferente da raridade local: os pesos estaduais são os mesmos para todos os grupos do mesmo ano/modelo.',
    limitations: 'As frequências já refletem os cortes de percentil, aproximadamente 50%, 20%, 20%, 5% e 5%. Dar maior peso às classes raras é uma escolha de destaque, não uma correção neutra da distribuição nem uma nova probabilidade.',
  },
  state_cdf: {
    definition: 'Avalia o valor médio original do modelo no grupo perante a distribuição empírica dos valores de todos os pixels estaduais.',
    equation: 's̄_g = (1/n) Σᵢ∈g sᵢ; F̂_estado(t) = (1/N) Σⱼ∈estado 1(sⱼ ≤ t); R_CDF = 100 × F̂_estado(s̄_g)',
    symbols: [['sᵢ e s̄_g', 'Valor recebido na banda 1 do pixel e média desse valor no grupo, ambos na escala percentual original.'], ['N', 'Todos os pixels válidos do estado, no mesmo ano e modelo.'], ['≤ e F̂', 'Contagem inclusiva de empates e função de distribuição empírica, sem ajuste a uma distribuição teórica.']],
    procedure: ['Usar a média da banda 1 já publicada para o grupo. Essa banda já está em escala percentual: não multiplicá-la novamente por 100.', 'Contar, entre todos os pixels estaduais, quantos têm valor menor ou igual a essa média. A consulta é feita pela busca ordenada dos limiares durante a leitura dos setores.', 'Dividir a contagem por N e multiplicar por 100. A referência continua sendo a população de pixels, não os grupos de 5 km.'],
    interpretation: 'O resultado expressa a parcela da população estadual de pixels cujo valor é menor ou igual ao valor médio do grupo. Não é a proporção de pixels altos dentro do grupo.',
    limitations: 'A média atual faz média(100 × F_hist(sᵢ)); esta alternativa faz 100 × F̂_estado(média(sᵢ)). Mudam a ordem das operações e a convenção de empates: a função recebida usa pontos médios de intervalos de histograma; aqui a CDF exata inclui todos os empates com ≤. Não é uma correção automática da média atual.',
  },
}
