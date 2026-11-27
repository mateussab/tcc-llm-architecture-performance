# Protocolo experimental complementar — carga aberta

**Versão:** 1.0 — 27/11/2026. Planejamento anterior à coleta controlada.

## Objetivo e escopo

Comparar as implementações monolítica e de microsserviços sob taxas externas de chegada programadas equivalentes, utilizando um LLM simulado por espera. A coleta de carga aberta complementa, sem substituir ou agregar indiscriminadamente, os 120 experimentos de carga fechada. Os oito pilotos, os smoke tests e os dois controlled-checks são exploratórios e não integram a amostra definitiva. Os seis pilotos ampliados foram dispensados para limitar o custo experimental; os dois maiores patamares permanecem na matriz para investigar degradação sob carga elevada.

## Fatores e matriz

| Delay (ms) | Taxas programadas (requisições/s) |
|---|---|
| 100 | 100, 500, 1000, 1500, 2000 |
| 500 | 20, 100, 200, 300, 400 |
| 2000 | 5, 25, 50, 75, 100 |

Cada taxa será executada em ambas as arquiteturas. Os cinco níveis correspondem a concorrências nominais de 10, 50, 100, 150 e 200, calculadas por taxa × delay em segundos. Essa aproximação não é uma medição de concorrência real. São 30 cenários e cinco repetições por cenário, totalizando 150 execuções. Cada bloco de repetição contém os 30 cenários em ordem aleatorizada pelo runner de lote com semente 42. A ordem efetiva será registrada no manifesto.

## Execução e controles

- Executor k6: `constant-arrival-rate`, unidade de tempo de um segundo.
- VUs pré-alocados e máximos: 400 em todos os cenários.
- Aquecimento: 60 s na taxa alvo; medição: 60 s na mesma taxa; cooldown: 10 s após encerramento dos serviços.
- Aquecimento e medição usam processos k6 separados, mantendo os serviços da execução ativos entre as fases. Não se pressupõe regime estacionário apenas em função do aquecimento.
- Graceful stop: 30 s; timeout HTTP: 60 s. Requisições pendentes podem terminar após a janela de chegada ou não ser concluídas.
- Execuções sequenciais, sem reconstrução ou atualização de imagens. Quotas: monólito 4 CPUs e 2 GiB; chat-service e llm-service 2 CPUs e 1 GiB cada.
- Monitoramento de host, k6 e contêineres em intervalos de 10 s. Registrar ambiente, hashes dos scripts e Compose, identificadores de imagens, versões e logs conforme o runner.
- Preservar resultados brutos de warmup e measurement, manifesto, checkpoint e tentativas incompletas; manter separação dos resultados de carga fechada.

## Métricas e análise planejada

Analisar a fase measurement como unidade experimental (uma execução), mantendo warmup para diagnóstico. Calcular, por execução, latências HTTP média, mediana, P95 e P99 das requisições efetivamente observadas; taxa de falha HTTP; contagens de iterações iniciadas, concluídas, descartadas e requisições válidas; razão de atendimento nominal (válidas / [taxa programada × 60]); taxa válida nominal (válidas / 60 s); taxa efetiva usando a duração real informada pelo k6, incluindo finalização; consumo de CPU e memória por contêiner e soma por arquitetura, além dos recursos de host e gerador como diagnóstico. Para recursos, excluir coletas com tempo de observação fora da janela e próximas às bordas (usar janela interna de 5 a 55 s, conforme timestamps disponíveis); informar número de amostras e ausência de dados. CPU de contêineres e k6 é expressa em percentual de CPU lógica (100% equivale aproximadamente a uma CPU); CPU do host é normalizada.

Comparar arquiteturas dentro do mesmo delay, taxa e bloco de repetição. Apresentar estatísticas descritivas entre as cinco execuções e diferenças absolutas e relativas pareadas por bloco, sem tratar requisições individuais como repetições independentes. Examinar tendências de overhead relativo entre delays e níveis de concorrência nominal, reconhecendo que as taxas também variam com o delay. Reportar conjuntamente latência, demanda atendida, descartes e falhas; latências de solicitações descartadas não são observadas. P99 em 5 req/s tem apenas cerca de 300 observações por execução sem descartes, devendo ser interpretado com cautela.

## Validação e tratamento de incidentes

Conferir identidade do cenário, duração nominal, contadores JSON/CSV, arquivos de monitoramento, encerramento dos serviços, ambiente e unicidade da repetição. Descartes e falhas da aplicação são resultados da investigação, não motivos automáticos para exclusão. Incidentes operacionais (por exemplo, suspensão do computador, corrupção de arquivos, mudança de configuração ou monitoramento ausente) devem ser registrados separadamente; revisar tentativas incompletas antes de autorizar nova execução. Não substituir silenciosamente resultados desfavoráveis. Uma diferença pequena entre contagem nominal e iterações iniciadas mais descartadas pode ocorrer na fronteira da agenda; reportar divergências e investigar avisos.

## Limitações

Os resultados caracterizam as implementações e o ambiente testados, não capacidade máxima universal nem desempenho de inferência real. O limite comum de 400 VUs pode restringir a demanda efetivamente enviada quando a latência aumenta. CPU próxima à quota sugere um possível gargalo, mas não demonstra causalidade ou throttling sem instrumentação específica. A duração nominal acumulada é 5h25min; o tempo real depende da sobrecarga operacional e da finalização das requisições.
