# Ambiente Experimental

## 1. Objetivo

Caracterizar o ambiente computacional da pesquisa **Análise Comparativa da Latência entre
Arquiteturas Monolítica e de Microsserviços em Aplicações com Integração Simulada a LLMs**,
registrando hardware, software, infraestrutura, automação e mecanismos de rastreabilidade.

O delineamento, as hipóteses, os critérios de análise e as evidências metodológicas constam em
[experimental-design.md](experimental-design.md). Os valores deste documento foram registrados
na preparação de novembro de 2026. A seção 13 define a conferência do ambiente definitivo;
a coleta oficial ainda não foi iniciada.

## 2. Hardware

| Componente | Especificação |
| --- | --- |
| Processador | AMD Ryzen 5 3600 |
| Núcleos físicos | 6 |
| Processadores lógicos | 12 |
| Frequência base | 3,6 GHz |
| Memória RAM | 16 GiB DDR4 (2 módulos de 8 GiB) |
| Frequência da memória | 2400 MT/s |
| Placa de vídeo | NVIDIA GeForce RTX 2060 |
| Placa-mãe | Gigabyte B550M AORUS ELITE |
| SSD NVMe | Patriot P300 128 GB |
| HDD SATA | Toshiba HDWD110 1 TB |
| HDD SATA | Western Digital WD10JPVX-22JC3T0 1 TB |
| SSD SATA | Kingston SA400S37/240G 240 GB |

### 2.1. Distribuição física do armazenamento

| Unidade | Disco físico (número) | Finalidade | Capacidade do volume (GiB) | Espaço livre (GiB) |
| --- | --- | --- | ---: | ---: |
| C: | Patriot P300 NVMe (3) | Windows | 118,25 | 8,82 |
| D: | Toshiba HDWD110 SATA (1) | Armazenamento do Docker Desktop | 931,51 | 362,89 |
| E: | Western Digital WD10JPVX-22JC3T0 SATA (2) | Projeto e resultados | 931,51 | 519,24 |

As unidades C:, D: e E: são NTFS e pertencem a discos físicos distintos, identificados por
`Get-Partition` e `Get-Disk`. A localização do armazenamento Docker foi conferida na interface
do Docker Desktop. O Kingston (disco 0, 223,57 GiB) não corresponde a essas unidades.
A separação reduz a concorrência direta de operações de disco, mas não elimina o compartilhamento
de recursos. O espaço livre é um registro pontual; conferir novamente antes de cada lote,
especialmente C:, que contém o sistema, temporários e potencialmente a paginação.

GPU, placa-mãe, frequência base e tipo DDR4 são registros anteriores, não reconfirmados pelos
comandos de armazenamento e memória. A GPU não é utilizada para inferência no experimento.

## 3. Software

| Software | Versão |
| --- | --- |
| Windows 11 Pro | 64 bits - Build 26300 (versão completa 10.0.26300.9974) |
| Oracle JDK (host) | 21.0.10+8-LTS-217 |
| Java dos containers | Eclipse Temurin 21.0.13.1+2-LTS |
| Spring Boot | 4.1.2 |
| Docker Desktop | 4.76.0 |
| Docker Engine | 29.5.2 |
| Docker Compose | 5.1.4 |
| k6 | 2.4.0 |
| WSL | 2.7.3.0 |
| Kernel Docker | 6.6.114.1-microsoft-standard-WSL2 |
| Windows PowerShell | 5.1.26100.9818 |
| IntelliJ IDEA | 2026.1 (registro anterior) |
| Python | 3.14.3 |
| psutil | 7.2.2 (dependência definida em `performance-tests/requirements.txt`) |
| Maven (imagem de build consultada por digest) | Apache Maven 3.9.16 |
| Java da imagem de build consultada | Eclipse Adoptium 21.0.12.1 |
| Git | 2.53.0.windows.3 |
| containerd | 2.2.4 |
| runc | 1.3.5 |
| docker-init | 0.19.0 |

O JDK do hospedeiro e a IDE são ferramentas de desenvolvimento; o Java das imagens executa as
aplicações. A versão Maven consultada por digest caracteriza a imagem de construção registrada,
não o Maven do hospedeiro. Reconfirmar as versões pertinentes antes da coleta (seção 13).

## 4. Ambiente de containerização

| Característica | Configuração registrada |
| --- | --- |
| Plataforma | Docker Desktop com WSL 2 |
| Arquitetura | Linux AMD64 |
| Contexto | `desktop-linux` |
| CPUs lógicas reportadas pelo Docker | 12 |
| Memória reportada pelo Docker | 8284901376 bytes (aprox. 7,72 GiB) |
| Driver de rede | bridge |
| Rede lógica | `tcc-network` |
| Rede efetiva | `tcc-llm-architecture-performance_tcc-network` |

A memória reportada pelo servidor Docker/WSL2 não é a memória livre do Windows nem a quota
individual dos contêineres.

### 4.1. Imagens e construção

| Serviço | Imagem da aplicação | Contexto de build |
| --- | --- | --- |
| `monolith` | `tcc-llm-monolith:1.0` | `monolith/tcc-llm-monolith` |
| `chat-service` | `tcc-chat-service:1.0` | `microservices/chat-service` |
| `llm-service` | `tcc-llm-service:1.0` | `microservices/llm-service` |

Os Dockerfiles utilizam construção em múltiplos estágios, com `maven:3.9-eclipse-temurin-21`
para empacotamento e `eclipse-temurin:21-jre` para execução. O build realiza
`mvn dependency:go-offline -B` e `mvn clean package -DskipTests`; a inicialização utiliza
`java -jar app.jar`. O `-DskipTests` não desativa os checks do k6.

A consulta ao digest Maven registrado no build preliminar confirmou Maven 3.9.16, Java
21.0.12.1, Linux AMD64, locale en_US e UTF-8:
`sha256:99e61abcff91a9b1333463bd8451fb18495d6eba9250ac66a338b518f8278320`.
No log preliminar E16 de 26/11/2026, o runtime `eclipse-temurin:21-jre` foi resolvido para
`sha256:d77e090ae1f6970c047b443c6f0a6c1358b0426d44432bb5a7753408cd43de0d`.
Esses registros não garantem a resolução futura das tags. O runner solicita `--build` em cada
execução; preservar os digests, IDs e logs e investigar mudanças conforme a seção 13.3.

### 4.2. Portas e comunicação

| Serviço | Porta | Acesso |
| --- | --- | --- |
| `monolith` | 8080 | `http://localhost:8080/chat` |
| `chat-service` | 8081 | `http://localhost:8081/chat` |
| `llm-service` | 8082 | `http://llm-service:8082/generate` (interno à rede Docker) |

A porta 8082 não é publicada no hospedeiro. O `chat-service` depende de `llm-service` no Compose,
usa `LLM_SERVICE_URL=http://llm-service:8082` e realiza a chamada HTTP síncrona com `RestClient`.
O monólito invoca o simulador na mesma JVM. A dependência do Compose não garante prontidão,
que é conferida pelo runner.

## 5. Ambiente de execução dos testes

| Componente | Local de execução |
| --- | --- |
| Runner Python | Hospedeiro Windows |
| k6 e script `chat-load-test.js` | Hospedeiro Windows |
| `resource_monitor.py` e psutil | Hospedeiro Windows |
| Docker Engine | Ambiente Linux/WSL2 do Docker Desktop |
| Aplicações Java | Contêineres da arquitetura avaliada |

O k6 e o monitoramento compartilham o hardware físico com Docker e demais processos do host.
Executar somente a arquitetura selecionada, reduzir atividades não essenciais (IDE, jogos,
gravação de tela), manter as proteções de segurança e evitar suspensão do computador.
Não há garantia de isolamento físico nem de temperatura, frequência ou utilização constantes.
O modelo de carga, a métrica principal e os parâmetros são definidos no planejamento experimental.

## 6. Simulação do modelo de linguagem

As aplicações Java implementam o mesmo atraso configurável por `Thread.sleep(delayMs)` e
retornam `Resposta simulada para: ` seguida do prompt. A simulação é uma espera bloqueante,
sem inferência real, GPU, tokenização ou streaming. Os detalhes metodológicos e as limitações
da simulação estão no planejamento experimental, seções 1 e 14.

## 7. Padronização dos recursos computacionais

### 7.1. Distribuição dos recursos

| Arquitetura | Serviço | Limite de CPU | Limite de memória |
| --- | --- | --- | --- |
| Monolítica | monolith | 4 CPUs | 2 GiB |
| Microsserviços | chat-service | 2 CPUs | 1 GiB |
| Microsserviços | llm-service | 2 CPUs | 1 GiB |

Os limites totais são 4 CPUs e 2 GiB por arquitetura; são quotas, não reservas exclusivas.
A distribuição por serviço e as diferenças entre JVMs integram a configuração avaliada.

### 7.2. Validação dos limites

Durante a preparação, os serviços foram iniciados separadamente por arquitetura com
`docker compose up -d --no-build --pull never` e encerrados com `docker compose down`.
Foram utilizados `docker compose config`, `docker inspect` e `docker stats --no-stream`.
Os limites observados foram:

| Serviço | HostConfig.NanoCpus | Memory (bytes) | MemorySwap (bytes, RAM + swap) |
| --- | ---: | ---: | ---: |
| monolith | 4000000000 | 2147483648 | 4294967296 |
| chat-service | 2000000000 | 1073741824 | 2147483648 |
| llm-service | 2000000000 | 1073741824 | 2147483648 |

O limite combinado de RAM e swap é 4 GiB por arquitetura; isso não demonstra uso de swap.
`docker stats` permite observar consumo e limite de memória, não comprova a quota de CPU.

Amostras pontuais de diagnóstico sem carga k6:

| Serviço | CPU (%) | Memória (MiB) | Memória (%) | PIDs |
| --- | ---: | ---: | ---: | ---: |
| monolith | 0,22 | 151,9 | 7,42 | 37 |
| chat-service | 0,09 | 132,8 | 12,97 | 30 |
| llm-service | 0,12 | 119,5 | 11,67 | 29 |

As amostras foram obtidas em instantes distintos, sem protocolo de estabilização; não são
médias, resultados oficiais nem evidência de diferenças de consumo sob carga.

### 7.3. Limitações da distribuição

O monólito utiliza uma JVM e os microsserviços duas, com quotas individuais fixas. Limites totais
iguais não asseguram igualdade de capacidade instantânea. Os efeitos das configurações padrão
da JVM são detalhados na seção 9.

### 7.4. Monitoramento de recursos

O `resource_monitor.py` coleta CPU (`psutil.cpu_percent(interval=None)`) e memória
(`psutil.virtual_memory()`) do hospedeiro e métricas dos contêineres selecionados por ID em
uma chamada `docker stats --no-stream --no-trunc --format "{{json .}}"` por ciclo.

A thread auxiliar inicializa a referência de CPU e agenda coletas com relógio monotônico,
intervalo nominal de 10 s e sem compensação em rajadas após atrasos. O intervalo deve ser
numérico, positivo e finito. O timeout do Docker é 8 s (`DOCKER_STATS_TIMEOUT_SECONDS`).
Ao encerrar a fase, o contexto sinaliza a parada e aguarda `join()` antes de fechar o CSV.
O arquivo é criado em modo exclusivo (`x`), com gravação incremental e `flush()` por ciclo.

O cabeçalho do CSV contém `timestamp_utc`, `elapsed_seconds`, `source`, `container`,
`cpu_percent`, `memory_percent`, `memory_usage` e `error`. O timestamp UTC e o tempo monotônico
registram o início de cada ciclo; o tempo relativo reinicia por fase. A leitura do host precede
a do Docker. CPU do host refere-se à capacidade total, enquanto 100% no Docker corresponde
aproximadamente a uma CPU lógica; valores maiores são possíveis. A memória Docker é relativa
ao limite do contêiner, não ao heap Java. Não somar consumo do host ao dos contêineres.

| Falha de monitoramento | Tratamento |
| --- | --- |
| Consulta ou interpretação do Docker | Linha `source=docker` com erro e aviso; tenta continuar a coleta |
| Falha geral da thread (incluindo escrita) | Linha `source=monitor` quando possível; falha fatal sinalizada ao runner após `join()` |
| Falha simultânea na execução principal | Preserva a exceção original, acrescentando nota sobre a falha do monitor |

Em uma fase oficial são exigidos ciclos completos nas janelas de 10, 20, 30, 40 e 50 s (±2 s).
A coleta final próxima de 60 s é opcional; os dados são preservados, mas ficam fora das
estatísticas descritivas de recursos. Qualquer registro de erro invalida a fase oficial, mesmo
em uma coleta opcional. Cada ciclo completo contém duas linhas no monólito e três nos
microsserviços. Os testes A/B e a metodologia de análise constam no planejamento, seções 9.9 e 13.2.

## 8. Padronização das dependências

### 8.1. Aplicações

| Dependência | Monolith | Chat Service | LLM Service |
| --- | --- | --- | --- |
| spring-boot-starter-webmvc | Sim | Sim | Sim |
| spring-boot-starter-webmvc-test | Sim | Sim | Sim |

Os três POMs conferidos utilizam parent Spring Boot 4.1.2, Java 21, groupId `br.ufma`, versão
`0.0.1-SNAPSHOT` e `spring-boot-maven-plugin`. A dependência `spring-boot-starter-webmvc-test`
possui escopo `test`. Os artifactIds são distintos; não há Actuator ou configuração personalizada
de compilador. Não foi feita inspeção independente de todas as dependências transitivas dos JARs.

### 8.2. Automação

O runner utiliza a biblioteca padrão do Python e importa `monitor_resources`, que depende de
`psutil==7.2.2`, declarado em `performance-tests/requirements.txt`. Docker, Compose e k6 são
ferramentas externas. Instalar psutil no interpretador que executará o runner; ambiente virtual
é opcional.

## 9. Padronização das JVMs

### 9.1. Configuração e versões verificadas

| Característica | Monolith | Chat Service | LLM Service |
| --- | --- | --- | --- |
| Distribuição | Eclipse Temurin | Eclipse Temurin | Eclipse Temurin |
| Versão | 21.0.13.1 | 21.0.13.1 | 21.0.13.1 |
| Build | 21.0.13.1+2-LTS | 21.0.13.1+2-LTS | 21.0.13.1+2-LTS |
| Máquina virtual | OpenJDK 64-Bit Server VM | OpenJDK 64-Bit Server VM | OpenJDK 64-Bit Server VM |
| Imagem base | eclipse-temurin:21-jre | eclipse-temurin:21-jre | eclipse-temurin:21-jre |

A consulta `java -version` nas três imagens locais confirmou Eclipse Temurin 21.0.13.1+2-LTS,
substituindo o registro anterior de 21.0.13+9-LTS. Reconfirmar caso as imagens mudem.

### 9.2. Configuração de execução e quotas reconhecidas

Não definir manualmente `-Xms`, `-Xmx`, flags de GC ou `JAVA_TOOL_OPTIONS`. As aplicações
executam `java -jar app.jar`. Consultas em contêineres temporários sob as mesmas quotas,
sem download ou rebuild, com `-XshowSettings:vm -version` e `-XshowSettings:system -version`,
produziram os seguintes resultados:

| Característica | Monolith | Chat Service | LLM Service |
| --- | ---: | ---: | ---: |
| CPUs efetivas | 4 | 2 | 2 |
| Período de CPU (µs) | 100000 | 100000 | 100000 |
| Quota de CPU (µs) | 400000 | 200000 | 200000 |
| Limite de RAM (GiB) | 2 | 1 | 1 |
| RAM + swap (GiB) | 4 | 2 | 2 |
| Heap máximo estimado (MiB) | 512 | 247,5 | 247,5 |
| Provedor | cgroupv2 | cgroupv2 | cgroupv2 |

Os heaps máximos estimados somam 495 MiB nos microsserviços e 512 MiB no monólito; não são
heaps compartilhados nem medidas de utilização. As consultas caracterizam JVMs de diagnóstico,
não a JVM ativa da aplicação. Não ajustar heaps para igualá-los: a distribuição de recursos
integra a comparação. Mesmo com a mesma versão Java, heap, JIT, GC e paralelismo podem diferir.
Conferir opções externas no registro final.

## 10. Organização dos resultados experimentais

### 10.1. Diretórios e formatos

```text
performance-tests/results/
├── preliminary/
│   ├── logs/
│   ├── warmup/
│   └── measurement/
└── official/
    ├── logs/
    ├── warmup/
    ├── measurement/
    └── completed-runs.json
```

| Formato | Conteúdo |
| --- | --- |
| CSV agregado | Métricas consolidadas |
| JSON | Métricas consolidadas e resumo do k6 |
| CSV temporal | Registros individuais das métricas do k6 |
| CSV de recursos | Amostras de CPU e memória do hospedeiro e dos contêineres |

Cada fase oficial contém `{run_id}.csv`, `{run_id}.json`, `{run_id}_raw.csv` e
`{run_id}_resources.csv`. São oito arquivos por execução; os preliminares intencionalmente
sem monitoramento podem não ter CSV de recursos. O identificador compartilhado entre fases é
`{cenario}_{arquitetura}_{delay}ms_{vus}vus_rep{repeticao}_{timestamp}`, com timestamp local
`YYYYMMDD_HHMMSS_ffffff`. A fase é identificada pelo diretório e metadados.

### 10.2. Logs e plano experimental

O runner exibe mensagens no terminal, sem persistência automática de logs. Capturar a saída
com `python -u ... 2>&1 | Tee-Object -FilePath ...`, em arquivo único por lote, e conferir
`$LASTEXITCODE` imediatamente. Mensagens do Docker em stderr podem aparecer como
`NativeCommandError` no Windows PowerShell; avaliar também o código de saída e a validação.

Somente `plan-only` exporta `experimental-plan_seed42_<timestamp>.csv` em `preliminary/`.
O modo oficial regenera o plano em memória, não lê esse CSV nem o exporta automaticamente.
Preservar a cópia correspondente ao código e à versão do Python usados na coleta.

### 10.3. Versionamento, backup e rastreabilidade

Os resultados CSV, JSON, LOG e checkpoint devem permanecer fora do Git por regras específicas
no `.gitignore`; preservar a estrutura com `.gitkeep`. Conferir também a exclusão de temporários
e de `.experiment-runner.lock` antes do commit. Fazer backup independente dos dados, logs,
planejamento e checkpoint, preferencialmente após cada lote. Registrar commit, hashes, versões,
IDs/digests das imagens, configuração Compose e horários; não alterar os dados brutos na análise.
Verificar espaço livre para os resultados e backups.

## 11. Validação e proteção experimental

### 11.1. Validação das fases

O runner valida cada nova fase uma vez, o aquecimento antes da medição. Na recuperação oficial,
ambas são revalidadas. São conferidos:

- Existência e tamanho não nulo dos arquivos do k6, correspondência com o `run_id` e campos obrigatórios;
- Metadados (cenário, arquitetura, atraso, VUs, repetição, tipo, fase, identificador e duração nominal) conforme a execução esperada;
- Consistência entre CSV agregado e objeto `scenario` do JSON;
- Contagem e throughput em relação a `summary.metrics.http_reqs.values` (`count` e `rate`);
- Contagens brutas de requisições, iterações, latências e três checks por requisição;
- Média, mínimo, máximo, mediana (p50), p90, p95 e p99 recalculados das amostras HTTP, com interpolação linear dos percentis;
- Consistência das taxas de erros HTTP e checks, valores numéricos finitos e limites aplicáveis;
- No modo oficial, estrutura e conteúdo do CSV de recursos, timestamps UTC, origens esperadas, ausência de erros/duplicidades e ciclos completos da seção 7.4.

As métricas brutas são verificadas em uma única varredura do CSV por fase, com contadores e
armazenamento das latências necessárias ao cálculo dos percentis. O throughput é comparado
com o resumo do k6, não recalculado independentemente dos timestamps. A duração informada
nos metadados não comprova a duração efetiva. Iterações interrompidas podem provocar
inconsistência de contagens. Os critérios metodológicos de aceitação estão no planejamento.

### 11.2. Tratamento de falhas

O runner verifica os códigos de saída dos comandos externos. Na falha de prontidão da API,
informa o último erro. Dentro do fluxo de execução, tenta encerrar os contêineres mesmo quando
há exceção, preserva a exceção original se houver falha adicional no encerramento e aguarda
10 s de cooldown no bloco de finalização. Falhas fatais de monitoramento são sinalizadas
conforme a seção 7.4. Resultados disponíveis são preservados para investigação.

### 11.3. Checkpoint e proteção dos artefatos

O modo oficial exige `--confirm-official`. O checkpoint `official/completed-runs.json` contém
chaves de cenário e repetição (`E##_repN`), gravadas após execução bem-sucedida e validação,
por substituição de arquivo temporário. Na retomada, o runner verifica globalmente os diretórios
oficiais de fases, rejeitando prefixos inesperados, e exige correspondência exata com os oito
artefatos de cada execução completa. Resultados registrados são revalidados; resultados completos
não registrados podem ser reconciliados sem nova carga. Resultados parciais, duplicados,
excedentes ou inválidos interrompem a retomada, sem exclusão automática.

A ordem planejada é preservada para as execuções pendentes. Não há mecanismo de marcar uma
execução permanentemente falha e continuar automaticamente; aplicar a política de investigação
e reexecução do planejamento. Não editar o checkpoint para simular sucesso.

### 11.4. Controle de execuções simultâneas

Nos modos `preliminary` e `official`, o diretório `performance-tests/results/.experiment-runner.lock`
é criado de forma exclusiva e removido ao final do fluxo normal ou em exceções tratadas.
Encerramento abrupto pode deixar um lock residual; removê-lo somente após verificar que não há
execução ativa. Essa proteção não impede cargas externas ao runner.

### 11.5. Evidências de validação da infraestrutura

| Verificação | Resultado registrado |
| --- | --- |
| Validação dos CSVs de recursos | 21 verificações anteriores de aceitação/rejeição |
| Testes integrados anteriores E04 e E16 | Warmup e measurement sem erros HTTP, checks 100% |
| Runner revisado: compilação, `--help` e `plan-only` | Aprovados; 24 cenários e 120 execuções |
| E16 preliminar com runner revisado (26/11/2026) | Ambas as fases validadas, saída 0 |
| Recursos do E16 revisado | 6 ciclos completos por fase; lock removido |
| Monitor revisado: compilação e teste local do host | 5 ciclos válidos, CSV íntegro, thread encerrada, saída 0 |
| `test-checkpoint.py` no Windows | Recuperação, retomada e rejeição de artefatos inválidos aprovadas; saída 0 |

O identificador do E16 revisado é `E16_microservices_100ms_100vus_rep1_20261126_010230_497543`.
Os resumos registraram 26.410 requisições no warmup e 42.036 na medição, sem falhas HTTP e com
checks 100%. O teste integrado ocorreu antes da última revisão do monitor; o teste posterior
verificou somente o hospedeiro. O teste do checkpoint utilizou dois cenários sintéticos em
diretório temporário, sem Docker ou k6: recuperou E16, registrou E06 simulado, retomou sem
repetição e rejeitou arquivo ausente, excedente, prefixo inesperado e execução parcial,
preservando artefatos inválidos. Nenhum desses resultados constitui coleta oficial.

### 11.6. Limitações da validação

A validação confirma consistência e integridade básica dos dados, não ausência de vieses,
correção semântica de todas as métricas ou estabilidade do sistema. A amostragem de recursos
não mede diretamente throttling, GC nem picos entre coletas. A recuperação foi testada de
forma controlada, não em interrupção real da coleta oficial. A última versão do monitor ainda
não foi exercitada com Docker e k6 reais em conjunto; conferir no ambiente antes de oficializar.

## 12. Automação dos experimentos

| Script | Responsabilidade |
| --- | --- |
| `performance-tests/scripts/run-experiments.py` | Planejamento, orquestração, validação e checkpoint |
| `performance-tests/scripts/chat-load-test.js` | Geração de carga, checks e exportação de métricas |
| `performance-tests/scripts/resource_monitor.py` | Coleta de CPU e memória por fase |

O runner oferece `plan-only` (plano sem carga), `preliminary` (validação) e `official` (coleta).
`--max-runs` limita o número de execuções por chamada nos dois modos de carga (padrão 2).
Antes de novas execuções selecionadas, verifica `docker version`, `docker compose version`
e `k6 version` com timeout de 20 s por comando; `plan-only` dispensa essa verificação.

Na execução, o runner solicita `docker compose down --remove-orphans`, inicializa a arquitetura
com `docker compose up -d --build` e verifica a prontidão por POST em `/chat`, com prompt
`Teste de inicialização`, `delayMs=100` e status 200 esperado. A janela nominal é de 120 s,
com timeout de até 5 s por tentativa e espera de até 2 s após falha, limitados ao tempo restante.
O aquecimento e a medição usam processos k6 separados e as mesmas aplicações ativas entre fases.
O procedimento completo, a randomização e os critérios de aceitação estão no planejamento.

O script de carga verifica arquitetura (`monolith` ou `microservices`), atraso (100, 500 ou
2000 ms), VUs inteiros positivos, fase, tipo, repetição (1 a 5) e formato dos identificadores.
No modo oficial, exige cenário E01–E24, VUs 1, 10, 50 ou 100, duração `60s` e `RUN_ID`.
O runner também verifica a correspondência dos parâmetros com o plano. Os checks validam
status 200, texto exato esperado e `processingTimeMs` finito e maior ou igual ao atraso.
Somente o aquecimento possui thresholds de 0% de falhas HTTP e 100% de checks aprovados.

Comandos de consulta e instalação (na raiz do projeto):

```powershell
python -m pip install -r performance-tests/requirements.txt
python performance-tests/scripts/run-experiments.py --help
python performance-tests/scripts/run-experiments.py --mode plan-only
```

## 13. Verificação final e registro do ambiente oficial

Preservar as evidências da preparação; não repetir toda a caracterização física se não houver
mudanças. Antes da coleta oficial, registrar o estado definitivo do código, das ferramentas e
das imagens. Executar os diagnósticos fora dos testes de carga, na raiz do projeto.

### 13.1. Conferência do hospedeiro e ferramentas

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed, ConfiguredClockSpeed
Get-Volume -DriveLetter C,D,E | Select-Object DriveLetter, FileSystem, Size, SizeRemaining
Get-Partition -DriveLetter C,D,E | Select-Object DriveLetter, DiskNumber
Get-Disk | Select-Object Number, FriendlyName, BusType, Size
$PSVersionTable.PSVersion
java -version
python --version
python -c "import psutil; print(psutil.__version__)"
k6 version
git --version
wsl --version
wsl -l -v
docker version
docker compose version
docker info --format 'OS={{.OSType}} Arch={{.Architecture}} CPUs={{.NCPU}} MemBytes={{.MemTotal}} Kernel={{.KernelVersion}}'
```

Conferir a versão e a localização do disco virtual do Docker Desktop na interface, espaço para
backup e divergências em relação às seções 2–4. As CPUs e a memória reportadas pelo Docker
não correspondem às quotas individuais das aplicações.

### 13.2. Conferência do código e das imagens

```powershell
git status --short
git rev-parse HEAD
docker compose config
Get-FileHash performance-tests/scripts/run-experiments.py, performance-tests/scripts/chat-load-test.js, performance-tests/scripts/resource_monitor.py, docker-compose.yml -Algorithm SHA256
```

Conferir os três POMs, Dockerfiles e `requirements.txt`. Após construir as imagens do código
consolidado, registrar seus IDs e as versões Java. Consultar somente imagens já presentes:

```powershell
$images = @('tcc-llm-monolith:1.0','tcc-chat-service:1.0','tcc-llm-service:1.0')
foreach ($img in $images) {
    docker image inspect $img --format '{{.Id}} {{json .RepoDigests}} {{json .Config.Env}}'
    docker run --rm --pull=never --entrypoint java $img -version
}
```

`RepoDigests` pode estar vazio em imagens locais; preservar IDs e digests das bases nos logs.
Conferir quotas com `docker inspect` e as configurações de JVM em serviços ativos, separadamente
por arquitetura. Executar `java -XshowSettings:vm -version`,
`java -XshowSettings:system -version` e `java -XX:+PrintCommandLineFlags -version` por
`docker compose exec -T <serviço>`. São JVMs de consulta sob as mesmas quotas, não medidas
do heap ativo. Encerrar os serviços antes da carga e não executar diagnósticos junto ao k6.

### 13.3. Identificação das imagens verificadas

| Imagem local | ID SHA-256 | Created (UTC, metadado da imagem) |
| --- | --- | --- |
| tcc-llm-monolith:1.0 | `sha256:a963d7ff65fec45101efbd55507f9b188628358e0bca87e43b3a77b48bb6a37a` | 2026-11-20T22:43:46.191934863Z |
| tcc-chat-service:1.0 | `sha256:951769eb3457d7e9feb0f3e05537261dc638c04e2a3f53e26728053df56564d4` | 2026-11-20T23:11:20.297081016Z |
| tcc-llm-service:1.0 | `sha256:aeea598909fb95895b8eaf3a999b4674d218513b6fc6f822c34923a20cb06d4b` | 2026-11-20T23:11:20.59499411Z |

As imagens históricas eram Linux AMD64 e os IDs coincidiram com o campo `Image` dos contêineres
iniciados na verificação sem build. O campo `Created` é metadado, não comprovação da data da
última construção. O E16 de 26/11/2026 realizou novo build; manifestos/atestações podem mudar
sem alteração do código executável. Os IDs da tabela não são definitivos. O runner não registra
IDs automaticamente por execução; preservar os logs de build, consultar IDs entre lotes e
investigar mudanças antes de prosseguir. Evitar atualizações de ferramentas e imagens durante
a coleta; registrar qualquer desvio relevante do ambiente.

### 13.4. Condições para iniciar a coleta

- Código e documentação consolidados, commit e hashes identificados, sem alterações não planejadas;
- Ferramentas, dependências, imagens e quotas conferidas; espaço livre e backup preparados;
- Plano de 24 cenários e 120 execuções com semente 42 exportado e preservado;
- Validações do runner e checkpoint aprovadas; conferência integrada da versão final do monitor;
- Nenhuma execução concorrente, `docker ps` conferido e portas 8080/8081 disponíveis;
- Captura de logs preparada e atividades concorrentes não essenciais reduzidas;
- Resultados existentes, se houver, preservados e reconciliados sem manipular o checkpoint.

Registrar interrupções e mudanças do ambiente durante a coleta. A confirmação destas condições
não garante ausência de variabilidade; eventuais falhas serão tratadas conforme o planejamento.
