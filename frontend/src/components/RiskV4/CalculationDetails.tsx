import { AGGREGATION_HELP } from '../../data/riskAggregationHelp'
import { summaryDefinition, summarize, type AggregationStats, type SummaryMethod } from '../../data/riskAggregation'
import { RISK_DISPLAY_CLASSES } from '../../data/riskDisplayPalette'
import type { RiskV4Cell, RiskV4Model } from '../../types/riskV4'

const number = (n: number, digits = 6) => n.toLocaleString('pt-BR', { maximumFractionDigits: digits })
const fixed = (n: number) => n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function MethodExplanation({ method }: { method: SummaryMethod }) {
  const help = AGGREGATION_HELP[method]
  return <div className="aggregation-method-explanation">
    <p>{help.definition}</p>
    <div className="aggregation-equation" role="math" aria-label={help.equation}><code>{help.equation}</code></div>
    <dl className="aggregation-symbols">
      {help.symbols.map(([symbol, definition]) => <div key={symbol}><dt>{symbol}</dt><dd>{definition}</dd></div>)}
    </dl>
    <h4>Procedimento aplicado</h4>
    <ol>{help.procedure.map((step) => <li key={step}>{step}</li>)}</ol>
    <h4>Interpretação do resultado</h4><p>{help.interpretation}</p>
    <h4>Limites desta interpretação</h4><p>{help.limitations}</p>
  </div>
}

export function Calculation({ cell, model, method, stats, year }: {
  cell: RiskV4Cell; model: RiskV4Model; method: SummaryMethod; stats: AggregationStats | null; year: 2025 | 2026
}) {
  const definition = summaryDefinition(method), result = summarize(cell, model, method, stats)
  const group = stats?.groups[cell.id], extra = group?.models[model]
  const n = cell.n_source_pixels
  const occupied = result.counts.filter((v) => v > 0).length
  const classSum = extra ? extra.class_means.reduce<number>((sum, mean, i) => sum + (mean ?? 0) * extra.class_counts[i], 0) : null
  const classMeansSum = extra ? extra.class_means.reduce<number>((sum, mean) => sum + (mean ?? 0), 0) : null
  const isRarity = method === 'local_rarity' || method === 'state_rarity'
  const weights = extra && isRarity ? extra.class_counts.map((count, i) => !count ? 0 : method === 'local_rarity' ? 1 / count : 1 / stats!.state_frequencies[model][i]) : []
  const totalWeight = weights.reduce((sum, w, i) => sum + w * extra!.class_counts[i], 0)
  const weightedSum = weights.reduce((sum, w, i) => sum + w * extra!.class_counts[i] * (extra!.class_means[i] ?? 0), 0)
  const ranges = RISK_DISPLAY_CLASSES.map((c, i) => `${c.label}: [${c.lower}, ${c.upper}${i === 4 ? ']' : ')'}`)

  return <details className="aggregation-calculation">
    <summary>Como este resultado foi calculado?</summary>
    <p>{definition.description}</p>
    <dl className="aggregation-context">
      <div><dt>Área</dt><dd>{cell.id}</dd></div>
      <div><dt>Modelo e ano</dt><dd>{model === 'random_forest' ? 'Random Forest' : 'XGBoost'} · {year}</dd></div>
      <div><dt>Pixels válidos do grupo (n)</dt><dd>{number(n, 0)}</dd></div>
      {stats && <div><dt>Pixels válidos do estado (N)</dt><dd>{number(stats.counts.source_pixels, 0)}</dd></div>}
    </dl>

    <details className="aggregation-technical-method">
      <summary>Definição técnica, fórmula e procedimento</summary>
      <MethodExplanation method={method} />
    </details>

    <details className="aggregation-worked-example">
      <summary>Memória de cálculo desta área</summary>
      <p>Os valores abaixo pertencem ao grupo, ano e modelo selecionados. O resultado exibido no mapa é {method === 'mode'
        ? `${RISK_DISPLAY_CLASSES[result.classIndex!].label}, com ${fixed(result.dominantShare * 100)}% dos pixels.`
        : result.value === null ? 'indisponível neste momento.' : `${fixed(result.value)}${method === 'concentration' ? '% dos pixels.' : ' pontos do índice de resumo.'}`}</p>

      {method === 'mean' && <>
        <p>Cada um dos {number(n, 0)} pixels tem peso 1/n = {number(1 / n, 12)}. A soma dos índices, reconstituída da média publicada, é {number(cell[`percentile_${model}`] * n, 8)}.</p>
        <code>{number(cell[`percentile_${model}`] * n, 8)} / {number(n, 0)} = {number(cell[`percentile_${model}`], 8)}</code>
        {extra && <p>A soma também pode ser conferida por classes: Σ n_c μ_c = {number(classSum!, 8)}. As médias por classe estão na tabela abaixo; classes vazias não acrescentam pixels à soma.</p>}
      </>}

      {method === 'mode' && <>
        <p>As contagens, da menor para a maior classe, são ({result.counts.map((v) => number(v, 0)).join('; ')}). O máximo é {number(Math.max(...result.counts), 0)}.</p>
        <code>D = 100 × {number(Math.max(...result.counts), 0)} / {number(n, 0)} = {fixed(result.dominantShare * 100)}%</code>
        <p>{result.mixed ? `Nenhuma classe ultrapassa n/2 = ${number(n / 2)} pixels; por isso o grupo é sinalizado como misto.` : `A classe selecionada supera n/2 = ${number(n / 2)} pixels e constitui maioria absoluta.`}</p>
        <p>{result.tied ? `As classes ${RISK_DISPLAY_CLASSES.filter((_, i) => result.counts[i] === Math.max(...result.counts)).map((c) => c.label).join(' e ')} estão empatadas. A convenção seleciona a menor classe.` : 'Não há empate na maior contagem.'} A cor corresponde à categoria, sem criar um percentil numérico para ela.</p>
      </>}

      {(method === 'median' || method === 'p75') && <>
        <p>Para q = {method === 'median' ? '0,5' : '0,75'}, a posição na sequência ordenada é:</p>
        <code>k = ceil({method === 'median' ? '0,5' : '0,75'} × {number(n, 0)}) = {number(Math.ceil(n * (method === 'median' ? .5 : .75)), 0)}</code>
        <p>O índice do pixel dessa posição é {result.value === null ? 'indisponível' : number(result.value, 8)}. A posição começa em 1; no vetor computacional corresponde ao índice k − 1. Não se faz média entre posições nem interpolação.</p>
        {method === 'median' && <p>{n % 2 === 0 ? `Como n é par, foi selecionado o central inferior, na posição ${number(n / 2, 0)}; o central seguinte não entra em uma média.` : 'Como n é ímpar, a posição corresponde ao pixel central da lista.'}</p>}
        <p>O parâmetro q ordena pixels dentro deste grupo; o valor retornado continua sendo um índice estadual. São duas referências distintas.</p>
      </>}

      {method === 'concentration' && <>
        <p>Há {number(result.counts[3], 0)} pixels em Alto e {number(result.counts[4], 0)} em Muito alto. São {number(result.counts[3] + result.counts[4], 0)} pixels com índice ≥90, dentro dos {number(n, 0)} válidos.</p>
        <code>C₉₀ = 100 × ({number(result.counts[3], 0)} + {number(result.counts[4], 0)}) / {number(n, 0)} = {fixed(result.concentration)}%</code>
        <p>Esse resultado informa a fração válida do grupo nas duas classes superiores. A legenda é de cobertura, não a escala de percentis 50/70/90/95.</p>
      </>}

      {method === 'area_mean' && group && result.value !== null && <>
        <p>A soma das áreas geodésicas válidas é A = {number(group.valid_area_m2, 6)} m², aproximadamente {number(group.valid_area_m2 / 1e6, 6)} km².</p>
        <code>Σ aᵢrᵢ / A = {number(result.value * group.valid_area_m2, 6)} / {number(group.valid_area_m2, 6)} = {number(result.value, 8)}</code>
        <p>O numerador mostrado é reconstituído a partir do resumo armazenado e da área total para permitir conferência. A geração original somou área × índice pixel a pixel.</p>
        <p>Em comparação, a média com pesos iguais é {number(cell[`percentile_${model}`], 8)}. A diferença deste grupo é {number(result.value - cell[`percentile_${model}`], 10)} ponto do índice. A área válida não é fixada em 25 km² nem calculada como n × 900 m².</p>
      </>}

      {extra && (method === 'mean' || isRarity) && <div className="aggregation-table-scroll" tabIndex={0} role="region" aria-label="Tabela de valores usados na memória de cálculo">
        <table className="aggregation-formula-table"><caption>{isRarity ? 'Pesos e contribuições para este resumo' : 'Decomposição da média por classe'}</caption>
          <thead><tr><th scope="col">Classe</th><th scope="col">n_c</th><th scope="col">μ_c</th>
            {method === 'state_rarity' && <th scope="col">f_c estadual</th>}
            {isRarity ? <><th scope="col">Peso/pixel</th><th scope="col">Peso total da classe</th><th scope="col">Contribuição no índice</th></> : <th scope="col">n_c × μ_c</th>}
          </tr></thead><tbody>{RISK_DISPLAY_CLASSES.map((c, i) => {
            const count = extra.class_counts[i], mean = extra.class_means[i]
            return <tr key={c.id}><th scope="row">{c.label}</th><td>{number(count, 0)}</td><td>{mean === null ? 'Sem pixels' : number(mean, 8)}</td>
              {method === 'state_rarity' && <td>{number(stats!.state_frequencies[model][i], 10)} ({number(stats!.state_frequencies[model][i] * 100, 6)}%)</td>}
              {isRarity ? <><td>{count ? number(weights[i], 12) : 'Não participa'}</td><td>{number(count * weights[i], 6)} ({number(100 * count * weights[i] / totalWeight, 4)}% do peso)</td><td>{number(count * weights[i] * (mean ?? 0) / totalWeight, 8)}</td></> : <td>{number(count * (mean ?? 0), 8)}</td>}
            </tr>
          })}</tbody>
        </table>
      </div>}
      {isRarity && extra && <small>A tabela pode ser rolada horizontalmente para consultar todos os pesos e contribuições.</small>}

      {method === 'local_rarity' && extra && <>
        <p>K = {occupied} classes ocupadas. A soma das médias dessas classes é {number(classMeansSum!, 8)}. Cada classe tem {fixed(100 / occupied)}% do peso normalizado, mesmo que ocupe outra proporção da área.</p>
        <code>R_local = ({extra.class_means.filter((v): v is number => v !== null).map((v) => number(v, 8)).join(' + ')}) / {occupied} = {number(result.value!, 8)}</code>
      </>}

      {method === 'state_rarity' && extra && <>
        <p>As frequências f_c da tabela são calculadas sobre {number(stats!.counts.source_pixels, 0)} pixels de {year}, modelo {model === 'random_forest' ? 'Random Forest' : 'XGBoost'}. São frações, não somente contagens da área selecionada.</p>
        <code>Z = Σ n_c/f_c = {number(totalWeight, 8)}{'\n'}Σ n_c μ_c/f_c = {number(weightedSum, 8)}{'\n'}R_estado = {number(weightedSum, 8)} / {number(totalWeight, 8)} = {number(result.value!, 8)}</code>
      </>}

      {method === 'state_cdf' && extra && stats && <>
        <p>O valor médio recebido na banda 1 deste grupo é s̄_g = {number(cell[`value_${model}`], 10)}%. A contagem estadual com valor ≤ s̄_g é {number(extra.state_cdf_count_le, 0)}, de um total de {number(stats.counts.source_pixels, 0)} pixels válidos.</p>
        <code>R_CDF = 100 × {number(extra.state_cdf_count_le, 0)} / {number(stats.counts.source_pixels, 0)} = {number(extra.state_cdf, 8)}</code>
        <p>Para comparação, a média dos índices recebidos é {number(cell[`percentile_${model}`], 8)}. A diferença não deve ser interpretada como uma correção dessa média: mudam a operação aplicada e o tratamento de empates.</p>
      </>}
      {isRarity && <p>As porcentagens de peso da tabela são influência matemática na fórmula; não são porcentagens de área nem probabilidades. Classes vazias não recebem média zero e ficam fora da ponderação.</p>}
      <p className="aggregation-precision-note">Os números intermediários são formatados para leitura. Recalcular com valores arredondados pode produzir pequenas diferenças. A formatação de duas casas do resultado não altera o valor usado para classificar a cor.</p>
    </details>

    <details className="aggregation-common-method">
      <summary>Origem dos dados, NoData e formação dos grupos</summary>
      <h4>Índice e valor do modelo são variáveis distintas</h4>
      <p>A banda 1 recebida contém o valor do modelo em escala percentual; a banda 2 contém o índice percentil estadual, rᵢ, entre 0 e 100. Os resumos operam sobre rᵢ, exceto a CDF estadual, que consulta a distribuição dos valores da banda 1. Não se multiplica a banda 1 novamente por 100.</p>
      <p>O professor construiu o índice com um histograma de 28.000 intervalos no logito, entre −20 e 8, largura 0,001. A posição de um pixel usa o ponto médio da massa de seu intervalo:</p>
      <p>O logito é ln(p/(1 − p)), em que p é a saída interna na escala 0–1, antes de gravar a porcentagem da banda 1. A rotina protege o logaritmo limitando p a [10⁻¹², 1 − 10⁻¹²] e limita o número do intervalo aos extremos do histograma.</p>
      <code>rᵢ = 100 × (B_b + 0,5 × H_b) / N</code>
      <p>H_b é a contagem do intervalo do pixel e B_b é a contagem acumulada dos intervalos inferiores. Pixels do mesmo intervalo recebem o mesmo índice. Esse índice é preservado; o navegador não recalcula o ranking nem ajusta uma distribuição teórica.</p>
      <h4>Máscara válida e suporte espacial</h4>
      <p>NoData = −9999 é excluído das somas, contagens, quantis e pesos. Zero é um valor válido e continua no cálculo. As máscaras das quatro bandas dos COGs devem coincidir; valores não finitos ou fora de [0,100] invalidam a geração, em vez de virarem zero.</p>
      <p>O centro de cada pixel é reprojetado de EPSG:4326 para EPSG:31979 (UTM 19S). O grupo é definido por floor(X/5000) e floor(Y/5000). Um pixel que cruza uma borda é atribuído integralmente ao grupo de seu centro. O recorte cartográfico do polígono serve à visualização; os pesos se baseiam nos pixels científicos válidos.</p>
      <p>Grupos nas bordas ou com máscara parcial podem conter menos pixels. Todas as médias e proporções usam o n válido daquele grupo, não uma quantidade fixa de pixels nem a área nominal do quadrado.</p>
      <h4>Resolução e precisão numérica</h4>
      <p>O exportador lê os pixels nativos de aproximadamente 30 m, armazenados em Float32, e acumula as somas em Float64. Os quantis preservam o valor do pixel da posição escolhida. As versões reduzidas do raster (overviews) não entram nesses cálculos; a consulta individual no mapa também usa o pixel original.</p>
      <p>Ao trocar de resumo, são usados os mesmos pixels e o mesmo modelo. O navegador consulta estatísticas previamente geradas; não treina, prevê ou recalibra modelos.</p>
    </details>

    <details className="aggregation-color-method">
      <summary>Como este resumo determina a cor?</summary>
      {method === 'concentration' ? <p>A cor vem da fração C₉₀ na escala contínua de cobertura: 0%, 25%, 50%, 75% e 100%. Os cortes de percentil não são aplicados a essa porcentagem.</p>
        : method === 'mode' ? <p>A categoria escolhida pela maior contagem determina diretamente a cor. As faixas abaixo definem as classes dos pixels que foram contados; não se calcula um percentil numérico para a moda.</p>
          : <p>O resultado numérico, antes do arredondamento de exibição, é comparado com os cortes fixos abaixo. Isso produz a classe deste resumo. Para ponderações experimentais, a aplicação desses cortes é uma regra visual, não um ranking estadual recalculado.</p>}
      {method !== 'concentration' && <ul>{ranges.map((range) => <li key={range}>{range}</li>)}</ul>}
      <p>A notação [a,b) inclui o limite inferior e exclui o superior; o último intervalo inclui 100. As comparações entre modelos e entre anos continuam usando exclusivamente médias dos percentis.</p>
    </details>

    <details className="aggregation-provenance">
      <summary>Proveniência e referências para reprodução</summary>
      {stats ? <>
        <p>Produto derivado: contrato {stats.schema_version}, ano {stats.year}; {number(stats.counts.groups, 0)} grupos e {number(stats.counts.source_pixels, 0)} pixels válidos por modelo. A identidade abaixo vincula os resumos ao produto científico recebido.</p>
        <code>{stats.source_identity}</code>
        <dl className="aggregation-input-hashes">{Object.entries(stats.input_sha256).map(([name, hash]) => <div key={name}><dt>{name} · SHA-256</dt><dd><code>{hash}</code></dd></div>)}</dl>
        <p><a href={`/data/risk/v4/${year}/aggregation-stats.json`} target="_blank" rel="noreferrer">Abrir o JSON de estatísticas de {year}</a>. Ele também registra os hashes dos setores e do exportador executado.</p>
      </> : <p>As estatísticas adicionais não estão disponíveis. Média, moda e concentração usam os valores e proporções da grade publicada; seus exemplos continuam disponíveis acima.</p>}
      <p>As definições e a auditoria vinculam cada resumo ao ano e ao modelo. Esses resumos descrevem resultados recebidos; não constituem uma nova validação da capacidade de prever queimadas.</p>
      <ul>
        <li><a href="https://numpy.org/doc/stable/reference/generated/numpy.quantile.html" target="_blank" rel="noreferrer">NumPy: quantis e convenção inverted_cdf</a></li>
        <li><a href="https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/quantile.htm" target="_blank" rel="noreferrer">NIST: definições e convenções de quantis</a></li>
        <li><a href="https://scikit-learn.org/stable/modules/calibration.html" target="_blank" rel="noreferrer">Scikit-learn: calibração e curvas de confiabilidade</a></li>
      </ul>
    </details>
  </details>
}
