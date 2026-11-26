# Planejamento Experimental

## 1. Objetivo

Comparar a latência de aplicações com integração simulada a modelos de linguagem de grande porte
(LLMs) nas arquiteturas monolítica e de microsserviços, sob diferentes atrasos de processamento e
níveis de concorrência.

O simulador utiliza `Thread.sleep(delayMs)` e retorna `Resposta simulada para: ` seguida do prompt.
A espera bloqueante representa o atraso, não o consumo computacional de um LLM; não há inferência,
tokenização ou streaming. A comparação abrange as implementações como um todo. O ambiente e a
automação são descritos em [experimental-environment.md](experimental-environment.md). Os resultados
registrados neste documento são preliminares; a coleta oficial ainda não foi iniciada.

## 2. Questão de pesquisa

Como a latência de aplicações com integração simulada a LLMs difere entre as arquiteturas monolítica
e de microsserviços sob diferentes tempos de processamento simulado e níveis de concorrência?

## 3. Hipóteses

- **H1:** A arquitetura de microsserviços tende a apresentar maior latência média que a arquitetura
  monolítica sob condições equivalentes de processamento simulado e concorrência.
- **H2:** O acréscimo relativo de latência da arquitetura de microsserviços tende a diminuir à
  medida que aumenta o tempo de processamento simulado.
- **H3:** A diferença de latência entre as arquiteturas varia em função do nível de concorrência.

As hipóteses utilizam a latência HTTP média da medição. A comunicação entre serviços não é um
fator isolado; não se atribuirá a ela um efeito causal independente da arquitetura.

## 4. Variáveis independentes

| Variável | Níveis | Quantidade |
| --- | --- | ---: |
| Arquitetura | Monolítica e microsserviços | 2 |
| Tempo de processamento simulado | 100, 500 e 2000 ms | 3 |
| Usuários virtuais (VUs) | 1, 10, 50 e 100 | 4 |

## 5. Variáveis dependentes

| Métrica | Unidade | Classificação |
| --- | --- | --- |
| Latência média | ms | Principal |
| Latência p95 | ms | Secundária |
| Throughput | req/s | Secundária |
| Taxa de erros HTTP | % | Secundária |
| Latência mínima, máxima, p50, p90 e p99 | ms | Complementar |
| Total de requisições | Requisições | Complementar |
| Verificações funcionais aprovadas (checks) | % | Controle de qualidade |
| Utilização de CPU do hospedeiro e dos contêineres | % | Complementar |
| Utilização de memória do hospedeiro e dos contêineres | MiB; % | Complementar |

A latência corresponde à métrica `http_req_duration` do k6: tempo de envio, espera e recebimento da
resposta, excluindo resolução DNS, estabelecimento da conexão e espera anterior ao envio
(`http_req_blocked`). Não equivale a `processingTimeMs` retornado pela aplicação nem ao tempo total
de uma iteração. O atraso configurado não é imposto como limite inferior às amostras HTTP.

A latência considera todas as amostras registradas, inclusive requisições com falha. O throughput é
a taxa de `http_reqs` do resumo do k6, incluindo falhas e considerando a duração efetiva da fase. Os
percentis são calculados sobre as amostras HTTP de cada fase.

A taxa de erros (`http_req_failed`) segue a classificação de respostas esperadas do k6. A taxa de
checks aprovados expressa a proporção de verificações bem-sucedidas, não necessariamente a de
requisições inteiramente corretas. Esses indicadores serão interpretados em conjunto com a latência
e o throughput.

## 6. Variáveis controladas

Condições padronizadas, exceto os fatores deliberadamente variados:

- Hardware, sistema operacional, código-fonte, versões das ferramentas e dependências;
- Containerização, limites totais de recursos e JVM padrão, sem ajuste manual de heap;
- Simulador, prompt, método HTTP, corpo da requisição e checks;
- Durações das fases e cooldown, modelo de carga e procedimento de monitoramento.

Como medidas de controle, executar as arquiteturas separadamente, randomizar a ordem e reduzir
atividades concorrentes não essenciais, mantendo as proteções de segurança. CPU, memória,
temperatura, escalonamento e processos de fundo não são rigorosamente constantes; CPU e memória são
monitoradas.

## 7. Delineamento experimental

Será empregado um delineamento fatorial completo 2 × 3 × 4, abrangendo todas as 24 combinações dos
fatores. Cada cenário terá cinco repetições, totalizando 120 execuções oficiais planejadas,
organizadas em cinco blocos completos de 24 cenários.

A unidade experimental é uma execução completa do cenário, não uma requisição, VU ou fase
isolada. A ordem por bloco é definida na seção 9.6.

## 8. Matriz experimental

| ID | Arquitetura | Delay (ms) | VUs |
| --- | --- | --- | --- |
| E01 | Monolítica | 100 | 1 |
| E02 | Monolítica | 100 | 10 |
| E03 | Monolítica | 100 | 50 |
| E04 | Monolítica | 100 | 100 |
| E05 | Monolítica | 500 | 1 |
| E06 | Monolítica | 500 | 10 |
| E07 | Monolítica | 500 | 50 |
| E08 | Monolítica | 500 | 100 |
| E09 | Monolítica | 2000 | 1 |
| E10 | Monolítica | 2000 | 10 |
| E11 | Monolítica | 2000 | 50 |
| E12 | Monolítica | 2000 | 100 |
| E13 | Microsserviços | 100 | 1 |
| E14 | Microsserviços | 100 | 10 |
| E15 | Microsserviços | 100 | 50 |
| E16 | Microsserviços | 100 | 100 |
| E17 | Microsserviços | 500 | 1 |
| E18 | Microsserviços | 500 | 10 |
| E19 | Microsserviços | 500 | 50 |
| E20 | Microsserviços | 500 | 100 |
| E21 | Microsserviços | 2000 | 1 |
| E22 | Microsserviços | 2000 | 10 |
| E23 | Microsserviços | 2000 | 50 |
| E24 | Microsserviços | 2000 | 100 |

## 9. Configuração dos experimentos

| Parâmetro | Valor |
| --- | --- |
| Cenários / repetições / execuções | 24 / 5 / 120 |
| Aquecimento (`warmup`) | 60 segundos |
| Medição (`measurement`) | 60 segundos |
| Intervalo entre execuções (`cooldown`) | 10 segundos |
| Graceful stop do k6 | 30 segundos (padrão observado) |
| Gerador de carga | k6 no hospedeiro Windows |
| Modelo de carga | Fechado, com VUs constantes |
| Interface pública | POST `/chat`, `application/json` |
| Prompt | `Teste de desempenho` |
| CPU e RAM totais por arquitetura | 4 CPUs e 2 GiB |
| Configuração da JVM | Padrão, sem ajuste manual de heap |
| Randomização | Por blocos, semente 42 |
| Monitoramento | psutil e Docker Stats, a cada 10 segundos |
| Exportação | CSV agregado, JSON, CSV bruto e CSV de recursos |

### 9.1. Definição do aquecimento

O aquecimento de 60 s busca reduzir efeitos transitórios de inicialização e da JVM; a escolha em lugar de 30
s baseia-se na seção 9.2. Usa o mesmo atraso e VUs da medição, mas sua análise é separada.

### 9.2. Testes preliminares de estabilização

Foram avaliados quatro cenários, todos com atraso de 100 ms:

| Cenário | Arquitetura | VUs |
| --- | --- | ---: |
| E01 | Monolítica | 1 |
| E04 | Monolítica | 100 |
| E13 | Microsserviços | 1 |
| E16 | Microsserviços | 100 |

Os testes iniciais duraram 120 segundos, com análise de latência média, p95, máxima e número de
requisições em janelas de 30 segundos. O cenário E16 apresentou maior variação inicial, motivando
uma execução complementar de 240 segundos. Observou-se redução progressiva da latência durante
aproximadamente os primeiros 60 segundos, seguida de comportamento relativamente mais estável.

Essas observações não garantem estabilização completa nos demais cenários.

### 9.3. Impacto da exportação temporal

Comparação exploratória E16: três execuções de 120 s sem exportação temporal (A) e três com
exportação (B), na sequência A1, B1, B2, A2, A3 e B3. Os seis CSVs agregados originais de 18/11/2026
foram consultados. A tabela apresenta médias aritméticas por grupo e a variação relativa
`100 × (B − A) / A`, calculada antes do arredondamento.

| Métrica | Grupo A | Grupo B | Variação relativa |
| --- | ---: | ---: | ---: |
| Latência média (ms) | 127,0944 | 128,1825 | +0,8562% |
| Latência p95 (ms) | 203,5239 | 204,1397 | +0,3026% |
| Latência p99 (ms) | 305,2897 | 305,7065 | +0,1365% |
| Throughput (req/s) | 785,4081 | 778,6907 | −0,8553% |

As seis execuções apresentaram 0% de erros HTTP e 100% de checks aprovados. As variações
observadas foram inferiores a 1% em magnitude. A exportação será mantida para a análise temporal.
O teste descritivo, restrito a um cenário e três execuções por grupo, não comprova equivalência
estatística ou ausência de sobrecarga nos demais cenários e não integra a amostra oficial.

### 9.4. Duração da medição

A duração uniforme de 60 segundos favorece a padronização. Nos cenários E09 e E21 (1 VU e 2000 ms),
a quantidade de requisições tende a ser pequena, da ordem de 30 por fase em condições ideais,
desconsiderando custos adicionais e graceful stop. Isso limita a precisão de percentis elevados,
especialmente p99. A duração será mantida, com essa ressalva na interpretação.

### 9.5. Intervalo entre execuções

O cooldown de 10 s após encerrar os contêineres busca liberar recursos e reduzir efeitos residuais,
sem garantir a eliminação de variações térmicas ou interferências externas.

### 9.6. Randomização

Cada bloco contém os 24 cenários em ordem pseudoaleatória. A sequência utiliza uma única instância
de `random.Random(42)` e chamadas sucessivas de `shuffle()` sobre os cenários de cada bloco. A
estratégia reduz a influência sistemática da ordem e permite reproduzir o planejamento considerando
a versão do Python e o CSV preservado (seção 12).

### 9.7. Isolamento e distribuição dos recursos

| Serviço | CPU | Memória | Porta |
| --- | ---: | ---: | --- |
| `monolith` | 4 CPUs | 2 GiB | 8080 (publicada) |
| `chat-service` | 2 CPUs | 1 GiB | 8081 (publicada) |
| `llm-service` | 2 CPUs | 1 GiB | 8082 (interna) |

O monólito invoca o simulador na mesma JVM; nos microsserviços, `chat-service` consulta
`llm-service` por HTTP síncrono. Ambas as interfaces recebem `prompt` e `delayMs` e retornam
`response` e `processingTimeMs`. Os serviços são reiniciados entre execuções, mas permanecem ativos
entre as fases. A igualdade das quotas totais não implica recursos exclusivos; as duas JVMs e a
distribuição fixa de quotas fazem parte da configuração comparada.

### 9.8. Monitoramento de recursos

Uma thread auxiliar coleta CPU e memória do hospedeiro (psutil) e dos contêineres (`docker stats
--no-stream`) durante ambas as fases, a cada 10 s, com timeout Docker de 8 s. Cada ciclo deve conter
o hospedeiro e todos os serviços da arquitetura.

São obrigatórios cinco ciclos completos em 10, 20, 30, 40 e 50 s (tolerância de ±2 s). O ciclo aos
60 s é opcional, preservado quando registrado e excluído das estatísticas por poder coincidir com o
fim da carga. Todo ciclo registrado deve ser íntegro.

O tempo identifica o início do ciclo relativo à thread, não ao início exato do k6. A CPU do host
representa o intervalo entre chamadas do psutil; o Docker fornece uma amostragem curta posterior,
não uma média de 10 s. Falhas do Docker são registradas e permitem novas coletas; falhas fatais são
sinalizadas ao runner. Qualquer erro, ciclo incompleto ou ausência de janela obrigatória invalida a
fase oficial. Detalhes técnicos em `experimental-environment.md`.

### 9.9. Sobrecarga do monitoramento

O teste A/B exploratório no E16 utilizou duas execuções por grupo, na sequência A1, B1, B2 e A2: sem
monitoramento (A) e com monitoramento a cada 10 segundos (B), mantendo os períodos de aquecimento,
medição e cooldown. A tabela apresenta as médias dos indicadores da medição.

| Métrica | Sem monitoramento (A) | Com monitoramento (B) | Variação relativa |
| --- | ---: | ---: | ---: |
| Latência média (ms) | 108,52 | 108,00 | -0,48% |
| Latência p95 (ms) | 135,30 | 131,83 | -2,57% |
| Latência p99 (ms) | 174,13 | 165,72 | -4,83% |
| Throughput (req/s) | 919,09 | 923,46 | +0,48% |

As quatro execuções apresentaram 0% de erros HTTP e 100% de checks aprovados. Os quatro CSVs de
recursos do grupo B apresentaram 18 registros cada, sem erros; o grupo A não gerou esses arquivos.

Não foi observada degradação dos indicadores nas condições testadas, justificando a manutenção do
monitoramento como medida complementar. O teste não comprova equivalência, ausência de sobrecarga ou
melhoria causada pela instrumentação. Não integra a amostra oficial.

### 9.10. Validação preliminar da infraestrutura

Os testes E04 e E16 anteriores concluíram ambas as fases com 0% de erros HTTP e 100% de checks. O
validador de recursos passou por 21 verificações anteriores de arquivos válidos ou inconsistentes.
Em 26/11/2026, as revisões foram verificadas localmente:

| Verificação | Resultado |
| --- | --- |
| Compilação, `--help` e `plan-only` | Aprovados; 24 cenários e 120 execuções |
| E16 integrado com runner revisado | Duas fases válidas; 6 ciclos de recursos por fase; lock removido; saída 0 |
| Monitor revisado no Windows | 5 coletas do host a cada 1 s; CSV válido; thread encerrada |
| Checkpoint com dados sintéticos | Recuperação, registro, retomada sem repetição e rejeição de arquivos ausentes, excedentes, inesperados ou parciais; saída 0 |

O E16 integrado (`E16_microservices_100ms_100vus_rep1_20261126_010230_497543`) apresentou:

| Métrica | Aquecimento | Medição |
| --- | ---: | ---: |
| Requisições | 26.410 | 42.036 |
| Latência média (ms) | 227,07 | 142,47 |
| p95 (ms) | 400,17 | 197,73 |
| Throughput (req/s) | 438,77 | 699,30 |
| Erros HTTP / checks aprovados | 0% / 100% | 0% / 100% |

Esse E16 antecede a última revisão do monitor. O teste posterior do monitor não consultou Docker nem
simulou falhas fatais. O checkpoint utilizou validadores reais e dados sintéticos das duas
arquiteturas em diretório temporário, sem Docker ou k6; não houve retomada real da coleta oficial.
Nenhuma dessas verificações integra a amostra oficial.

## 10. Procedimento experimental

Antes de cada lote, conferir o planejamento, o ambiente e a disponibilidade das ferramentas. O modo
oficial exige confirmação explícita. Cada execução seguirá as etapas:

1. Encerrar os contêineres anteriores e iniciar os da arquitetura selecionada.
2. Verificar a prontidão da API por POST em `/chat`.
3. Executar o aquecimento de 60 segundos com monitoramento.
4. Exportar e validar os resultados do aquecimento, incluindo recursos no modo oficial.
5. Executar a medição de 60 segundos com monitoramento.
6. Exportar e validar a medição e conferir o conjunto completo de artefatos oficiais.
7. Encerrar os contêineres e aguardar o cooldown de 10 segundos.
8. Registrar a execução oficial validada no checkpoint.

O runner solicita a construção das imagens a cada execução. Construção, inicialização e prontidão
não integram as métricas do k6. O encerramento dos contêineres é tentado mesmo em caso de falha, e o
cooldown integra a finalização. Os comandos e mecanismos técnicos são descritos em
`experimental-environment.md`.

Cada VU realiza requisições sequenciais, sem espera adicional entre iterações. O modelo fechado não
impõe taxa fixa de chegada. As fases utilizam processos k6 independentes, mantendo as JVMs ativas. A
validação do aquecimento introduz intervalo variável antes da medição; não se trata de carga
contínua de 120 segundos. O graceful stop de 30 segundos permite a conclusão de iterações em
andamento, e o resumo pode incluir requisições concluídas após os 60 segundos nominais.

### 10.1. Critérios de validação

Cada requisição tem três checks: HTTP 200, resposta textual exata e `processingTimeMs` finito e
maior ou igual ao atraso. A medição exige aquecimento com 0% de erros HTTP, 100% de checks aprovados
e arquivos válidos. Na medição não há thresholds de desempenho ou taxa de erro.

A validação por fase verifica:

- Metadados esperados e integridade de JSON, CSV agregado e amostras brutas;
- Consistência de contagens de requisições, iterações, durações e checks;
- Throughput consistente com o resumo do k6 (não recalculado por timestamps);
- Média, mínimo, máximo, p50, p90, p95 e p99 das amostras brutas (interpolação linear nos
  percentis), além das taxas de erros e checks;
- No modo oficial, recursos válidos (seção 9.8) e conjunto completo de artefatos (seção 12).

Cada fase nova é validada uma vez, com leitura única do CSV bruto; na retomada, ambas são
revalidadas. Duração nominal válida não comprova tempo efetivo; iterações interrompidas podem causar
rejeição por contagens inconsistentes. No preliminar, recursos podem ser validados separadamente. A
integridade dos arquivos não garante ausência de vieses.

### 10.2. Falhas e reexecuções

Falhas de execução ou validação interrompem o procedimento, preservando os arquivos. Erros HTTP e
checks falhos na medição não justificam excluir resultados estruturalmente válidos: podem expressar
o comportamento sob carga.

Antes de reexecutar, registrar cenário, repetição, `run_id`, fase, motivo, evidências, classificação
e decisão. Falhas comprovadas de infraestrutura ou coleta podem justificar reexecução; preservar os
arquivos anteriores fora do conjunto oficial ativo quando necessário, registrando sua localização.
Não classificar falhas de desempenho ou disponibilidade como externas sem evidência.

Se o aquecimento falhar, não haverá medição. O runner não permite marcar uma execução
permanentemente falha e avançar automaticamente. Se a falha persistir, interromper a coleta e
documentar decisão metodológica antes de prosseguir, inclusive eventual alteração controlada do
procedimento. Não simular sucesso no checkpoint, inventar dados ou repetir seletivamente até obter
êxito. Reportar perdas e pares válidos.

### 10.3. Continuidade da coleta

Na retomada oficial, revalidar resultados registrados e recuperar os completos ainda não registrados
somente se ambas as fases, `run_id`, metadados e oito arquivos forem consistentes. Artefatos
ausentes, parciais, excedentes ou incompatíveis com o plano impedem o avanço automático. As
pendências seguem a ordem planejada. O lock evita instâncias simultâneas; o checkpoint é atualizado
por substituição de arquivo temporário. Não há exclusão nem sobrescrita automática. A validação
controlada consta na seção 9.10.

## 11. Estimativa de duração

| Fase | Tempo por execução | Tempo acumulado |
| --- | ---: | ---: |
| Aquecimento | 60 s | 120 min |
| Medição | 60 s | 120 min |
| Cooldown | 10 s | 20 min |
| Total nominal | 130 s | 260 min |

O total nominal (4 h 20 min) exclui build, inicialização, prontidão, encerramento, graceful stop,
finalização do monitoramento, exportação, validação, backup e interrupções. A duração efetiva será
superior; lotes menores e mais numerosos aumentam o custo de revalidação.

## 12. Armazenamento dos resultados

| Arquivo por fase | Conteúdo |
| --- | --- |
| `<run_id>.csv` | Métricas consolidadas |
| `<run_id>.json` | Métricas consolidadas e resumo k6 |
| `<run_id>_raw.csv` | Amostras individuais do k6 |
| `<run_id>_resources.csv` | CPU e memória |

As duas fases compartilham `run_id` (cenário, arquitetura, atraso, VUs, repetição e timestamp local
com microssegundos). São oito arquivos por execução oficial, 240 fases e 960 arquivos planejados,
além de plano, logs e checkpoint. Testes preliminares sem monitoramento podem não possuir CSV de
recursos.

A raiz `performance-tests/results/` separa `preliminary/` e `official/`, cada um com `warmup/`,
`measurement/` e `logs/`. Apenas `plan-only` exporta `experimental-plan_seed42_<timestamp>.csv` em
`preliminary/`; os demais modos regeneram o plano em memória. Preservar o CSV do código e Python
consolidados fora dos diretórios de fases. O checkpoint fica em `official/completed-runs.json`.

Capturar logs explicitamente, preservar dados brutos sem edição e manter backup independente do Git
após os lotes e antes da análise, incluindo plano e checkpoint. Registrar commit, versões,
configuração e imagens; conferir `.gitignore` conforme `experimental-environment.md`.

## 13. Análise dos resultados

A análise principal utilizará apenas a fase de medição. Para cada cenário, reportar valores
individuais, média, mediana, desvio padrão amostral e coeficiente de variação quando interpretável,
considerando as repetições válidas (cinco planejadas). O coeficiente de variação (`100 × s / média`)
exige pelo menos duas observações e métricas de escala de razão com média positiva, como latência e
throughput; não será aplicado a diferenças com sinal ou taxas próximas de zero.

**Comparações pareadas e hipóteses**

Para cada combinação de atraso e VUs, comparar a latência média dos microsserviços (`L_micro`) e do
monólito (`L_mono`) dentro do mesmo bloco. Para a repetição `i`:

- Diferença absoluta: `d_i = L_micro,i − L_mono,i` (ms).
- Diferença relativa: `r_i = 100 × d_i / L_mono,i` (%).

Resumir as diferenças calculadas em cada bloco, sem confundir a média dos percentuais com a
diferença percentual entre médias agregadas. Se a referência for zero, reportar a diferença absoluta
e identificar a relativa como indisponível.

Para a média das diferenças absolutas pareadas, apresentar IC nominal de 95% pelo intervalo t de
Student:

`média(d) ± t(0,975; n−1) × s(d) / √n`

Em que `n` é o número de pares válidos e `s(d)` o desvio padrão amostral das diferenças. O intervalo
depende da independência aproximada entre blocos e da adequação da distribuição das diferenças. Com
cinco pares, a verificação dos pressupostos é limitada. Se houver assimetria pronunciada,
observações influentes ou dependência evidente, dar maior ênfase aos valores individuais e à
descrição, sem tratar o intervalo como conclusivo.

| Pares válidos | Procedimento |
| --- | --- |
| 5 | Comparação pareada planejada completa |
| 2 a 4 | Estatísticas e IC t exploratório, com ressalvas sobre perdas e precisão |
| 1 | Diferença individual, sem desvio padrão amostral ou IC t |
| 0 | Comparação indisponível |

Não imputar dados ausentes. Reportar execuções válidas por cenário e usar somente blocos com as
duas medições válidas. O desvio padrão amostral exige ao menos duas observações.

As hipóteses serão investigadas pelos seguintes critérios:

- **H1:** avaliar as 12 comparações pareadas de latência média. Diferenças positivas indicam maior
  latência dos microsserviços; efeitos de sinais distintos serão reportados por condição.
- **H2:** comparar as diferenças relativas com sinal entre 100–500, 500–2000 e 100–2000 ms, mantendo
  os VUs fixos. Redução do acréscimo positivo é compatível com H2; inversões de sinal não indicam
  automaticamente redução da magnitude.
- **H3:** comparar as diferenças absolutas nos quatro níveis de VUs, mantendo o atraso fixo. Usar 1
  VU como referência dos contrastes principais e diferenças relativas como complemento, sem
  pressupor tendência monotônica.

Para H2 e H3, calcular os contrastes dentro dos blocos válidos em comum às condições, antes de
resumir. Reportar os blocos utilizados e não inferir contrastes sem pares comuns. Interpretar
magnitude, direção, variabilidade e incerteza, sem pressupor efeito uniforme da arquitetura. Os
intervalos por condição são exploratórios, sem ajuste simultâneo para múltiplas comparações. Não
haverá declaração de confirmação global a partir de testes independentes nem interpretação de
ausência de diferença detectável como equivalência.

**Apresentação e interpretação**

Médias de percentis por execução não equivalem a percentis de requisições agrupadas. Interpretar
latência com throughput, erros HTTP, checks e número de requisições: falhas podem responder mais
rápido. Considerar a imprecisão de percentis elevados com poucas amostras; não remover extremos
automaticamente.

Serão apresentados:

- Latência média e p95 por cenário, com valores individuais e resumos;
- Gráficos de interação entre arquitetura e VUs por atraso, e entre arquitetura e atraso por VUs;
- Diferenças pareadas absolutas com ICs nominais de 95% e diferenças relativas por condição;
- Throughput, erros HTTP e checks junto às métricas de latência;
- Evolução temporal do aquecimento e consumo amostrado de CPU e memória.

### 13.1. Análise complementar do aquecimento

Analisar latência média, p95, máxima, throughput, erros e estabilização em janelas semiabertas de 10
s (`[0, 10)`, ..., `[50, 60)`), ancoradas no primeiro registro HTTP. Classificar latências pelo
timestamp de registro da duração e calcular throughput por contagem de `http_reqs` dividida por 10
s. Janelas sem observações não têm latência zero.

O preliminar `E01_raw.csv` usa segundos Unix inteiros; conferir a resolução oficial. A referência é
aproximada, não necessariamente o início da carga. Preservar separadamente registros a partir de 60
s relativos, sem confundi-los com o início exato do graceful stop. A análise principal utiliza o
resumo completo da medição.

### 13.2. Análise complementar de recursos

Resumir as cinco coletas nominais de 10 a 50 segundos em cada fase, usando as janelas da seção 9.8.
Calcular média e máximo amostrado de CPU e memória por execução, separadamente para o hospedeiro e
cada contêiner. Comparar os resumos entre as repetições válidas de cada cenário.

| Indicador | Tratamento |
| --- | --- |
| CPU do hospedeiro | Percentual da capacidade total (0–100%) |
| CPU dos contêineres | Escala Docker; cerca de 100% por CPU lógica, sem truncamento |
| Memória absoluta | MiB (1.048.576 bytes), extraindo o consumo de `memory_usage` |
| Memória relativa | Percentual em relação à capacidade do host ou ao limite de cada contêiner |

Para o consumo agregado da arquitetura, somar a CPU e a memória absoluta dos contêineres de cada
ciclo antes de calcular as estatísticas. Não somar percentuais de memória; eventual percentual
agregado será obtido dividindo o consumo absoluto agregado pelo limite total configurado. Não somar
o consumo do hospedeiro ao dos contêineres, pois ele inclui Docker, k6 e outros processos.

As estatísticas têm finalidade descritiva. Máximos amostrados não são picos contínuos; a memória do
Docker não equivale ao heap Java e a proximidade da quota de CPU não comprova throttling. Os dados
não estabelecem relações causais por si sós.

## 14. Limitações metodológicas

- **Validade externa:** simulador bloqueante sem inferência real; uma implementação por arquitetura
  e uma máquina, sem outras distribuições de quotas, escalabilidade horizontal ou comunicação entre
  máquinas. Não se isola o efeito da comunicação HTTP.
- **Ambiente:** uma JVM versus duas, quotas não exclusivas e hardware compartilhado. Variações
  térmicas, escalonamento e efeitos residuais podem influenciar as execuções.
- **Carga:** modelo fechado, aquecimento sem garantia de estabilidade, intervalo variável entre
  fases, poucas requisições nos cenários mais lentos e ausência de avaliação prolongada.
- **Instrumentação:** amostragem sem garantia de captura de picos ou sincronização exata; não mede
  diretamente GC, heap ativo, throttling ou ocupação de threads. Os testes de sobrecarga
  restringem-se ao E16 e a análise temporal depende da resolução dos timestamps.
- **Estatística e dados ausentes:** cinco repetições limitam a precisão e avaliação de pressupostos;
  ICs sem ajuste simultâneo. Falhas de aquecimento podem produzir ausência de dados condicionada ao
  desempenho e interromper a coleta. Reportar perdas e desvios, sem extrapolar a condições não
  avaliadas.
