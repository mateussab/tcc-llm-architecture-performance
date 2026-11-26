# tcc-llm-architecture-performance

Projeto experimental do Trabalho de Conclusão de Curso (TCC) de Ciência da Computação da Universidade Federal do Maranhão (UFMA).

**Tema:** Análise Comparativa da Latência entre Arquiteturas Monolítica e de Microsserviços em Aplicações com Integração Simulada a LLMs.

O objetivo é comparar a latência HTTP das duas arquiteturas sob diferentes atrasos de processamento simulado e níveis de concorrência. O simulador utiliza `Thread.sleep(delayMs)` e uma resposta textual determinística, sem inferência de modelos de linguagem reais.

## Arquiteturas

| Serviço | Responsabilidade | Porta | CPU | RAM |
| --- | --- | --- | ---: | ---: |
| `monolith` | API de chat e simulador na mesma aplicação | 8080 (publicada) | 4 | 2 GiB |
| `chat-service` | API de chat e comunicação com o simulador | 8081 (publicada) | 2 | 1 GiB |
| `llm-service` | Simulador de processamento do LLM | 8082 (interna) | 2 | 1 GiB |

As arquiteturas são executadas separadamente, com limites totais de 4 CPUs e 2 GiB de RAM por arquitetura. Nos microsserviços, a comunicação interna é HTTP síncrona via `RestClient`.

## Tecnologias

- Java 21, Spring Boot 4.1.2 e Maven: implementação e construção das aplicações.
- Docker Desktop com WSL 2 e Docker Compose: ambiente de execução.
- k6: geração de carga e coleta de métricas HTTP.
- Python 3.14.3 e psutil 7.2.2: automação e monitoramento de recursos.
- Git: controle de versão.

As versões completas verificadas durante a preparação estão no documento de ambiente experimental.

## Estrutura do projeto

```text
tcc-llm-architecture-performance/
├── docs/
│   ├── experimental-design.md
│   └── experimental-environment.md
├── monolith/tcc-llm-monolith/
├── microservices/
│   ├── chat-service/
│   └── llm-service/
├── performance-tests/
│   ├── requirements.txt
│   ├── scripts/
│   │   ├── chat-load-test.js
│   │   ├── resource_monitor.py
│   │   └── run-experiments.py
│   └── results/
│       ├── preliminary/
│       └── official/
├── docker-compose.yml
└── README.md
```

## Pré-requisitos

Docker Desktop em execução (contêineres Linux), Docker Compose, Python e k6 disponíveis no terminal. É necessário espaço livre para imagens e resultados e disponibilidade das portas 8080 e 8081. Java e Maven locais são opcionais para desenvolvimento, pois a construção das aplicações ocorre no Docker.

Execute os comandos abaixo no PowerShell, na raiz do projeto. A criação e a ativação do ambiente virtual são opcionais (crie-o somente se ainda não existir):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale as dependências no interpretador que será usado pelo runner:

```powershell
python -m pip install -r performance-tests/requirements.txt
```

## Planejamento experimental

| Fator | Níveis |
| --- | --- |
| Arquitetura | Monolítica e microsserviços |
| Atraso simulado | 100, 500 e 2000 ms |
| Concorrência | 1, 10, 50 e 100 VUs |
| Repetições | 5 por cenário |

São **24 cenários e 120 execuções oficiais planejadas**, em cinco blocos randomizados com semente 42. Cada execução inclui aquecimento de 60 s, medição de 60 s e cooldown de 10 s, além da inicialização, validação e finalização. A métrica principal é a latência HTTP média (`http_req_duration`); os resultados do aquecimento não integram a análise principal.

## Execução dos experimentos

O runner `performance-tests/scripts/run-experiments.py` gerencia a inicialização das aplicações, a carga, o monitoramento, a validação e o encerramento dos contêineres. Execute apenas uma instância do runner por vez e não realize diagnósticos manuais durante a carga.

### Consultar as opções e gerar o plano

```powershell
python performance-tests/scripts/run-experiments.py --help
python performance-tests/scripts/run-experiments.py --mode plan-only
```

O modo `plan-only` valida o planejamento e exporta seu CSV em `performance-tests/results/preliminary/`, sem iniciar Docker ou k6. É o modo padrão.

### Executar um teste preliminar

```powershell
python performance-tests/scripts/run-experiments.py --mode preliminary --max-runs 1
```

Esse modo verifica o funcionamento do ambiente e da automação sem registrar resultados no checkpoint oficial.

### Realizar a coleta oficial

**Somente após cumprir as condições de início descritas no [ambiente experimental](docs/experimental-environment.md).** Registre o código, as versões e os IDs das imagens utilizados, preserve o CSV do planejamento e confirme os recursos disponíveis antes da coleta.

Exemplo de lote de dez execuções, com captura persistente do log:

```powershell
$logs = 'performance-tests/results/official/logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
python -u performance-tests/scripts/run-experiments.py --mode official --max-runs 10 --confirm-official 2>&1 | Tee-Object -FilePath "$logs/lote_$timestamp.log"
$LASTEXITCODE
```

O argumento `--confirm-official` é obrigatório. `--max-runs` limita as execuções por chamada nos modos de carga (padrão: 2). O modo oficial regenera o plano em memória, revalida os resultados existentes e retoma as execuções pendentes pelo checkpoint. Em caso de falha, preserve os arquivos e investigue a causa antes de retomar; não manipule o checkpoint para simular sucesso.

## Resultados

Os dados são armazenados em `performance-tests/results/preliminary/` ou `performance-tests/results/official/`, separados por fase (`warmup/` e `measurement/`). Cada fase oficial gera CSV agregado, JSON, CSV bruto e CSV de recursos; o checkpoint fica em `official/completed-runs.json`, relativo à raiz de resultados.

A captura de logs é feita explicitamente no terminal. Confira o código de saída após cada lote; mensagens do Docker em stderr podem aparecer como `NativeCommandError` no Windows PowerShell sem indicar, por si só, uma falha. Mantenha os resultados fora do Git conforme as regras de exclusão do projeto e faça backup independente de dados, logs, plano e checkpoint. Não altere os arquivos brutos para análise.

## Documentação

- [Planejamento experimental](docs/experimental-design.md): hipóteses, delineamento, procedimento, análise estatística e limitações.
- [Ambiente experimental](docs/experimental-environment.md): hardware, software, Docker, JVMs, automação, validações e condições de início da coleta.
