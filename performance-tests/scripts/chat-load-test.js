import http from 'k6/http';
import { check } from 'k6';

// Parâmetros dos experimentos definidos pelo Python, com valores padrão para testes individuais.
const ARCHITECTURE = __ENV.ARCHITECTURE || 'monolith';
const DELAY_MS = Number(__ENV.DELAY_MS || 100);
const VUS = Number(__ENV.VUS || 1);
const DURATION = __ENV.DURATION || '30s';
const PHASE = __ENV.PHASE || 'measurement';
const SCENARIO_ID = __ENV.SCENARIO_ID || 'pilot';
const REPETITION = Number(__ENV.REPETITION || 1);
const EXPERIMENT_TYPE = __ENV.EXPERIMENT_TYPE || 'preliminary';
const RUN_ID = __ENV.RUN_ID || null;

// Endpoints das arquiteturas
const endpoints = {
    monolith: 'http://localhost:8080/chat',
    microservices: 'http://localhost:8081/chat'
};

// Validação dos parâmetros
if (!Object.keys(endpoints).includes(ARCHITECTURE)) {
    throw new Error('Arquitetura invalida');
}

if (![100, 500, 2000].includes(DELAY_MS)) {
    throw new Error('Delay invalido');
}

if (!Number.isInteger(VUS) || VUS <= 0) {
    throw new Error('Quantidade de usuarios virtuais invalida');
}

if (!['warmup', 'measurement'].includes(PHASE)) {
    throw new Error('Fase experimental invalida');
}

if (!['preliminary', 'official'].includes(EXPERIMENT_TYPE)) {
    throw new Error('Tipo de experimento invalido');
}

if (!Number.isInteger(REPETITION) || REPETITION < 1 || REPETITION > 5) {
    throw new Error('Repeticao invalida');
}

if (!/^[a-zA-Z0-9_-]+$/.test(SCENARIO_ID)) {
    throw new Error('Identificador de cenario invalido');
}

if (RUN_ID !== null && !/^[a-zA-Z0-9_-]+$/.test(RUN_ID)) {
    throw new Error('Identificador de execucao invalido');
}

// Validações específicas dos experimentos oficiais
if (EXPERIMENT_TYPE === 'official') {
    if (!/^E(0[1-9]|1[0-9]|2[0-4])$/.test(SCENARIO_ID)) {
        throw new Error('Cenario experimental invalido');
    }

    if (![1, 10, 50, 100].includes(VUS)) {
        throw new Error('Quantidade de usuarios virtuais invalida para coleta oficial');
    }

    if (DURATION !== '60s') {
        throw new Error('Duracao invalida para coleta oficial');
    }

    if (RUN_ID === null) {
        throw new Error('RUN_ID obrigatorio para coleta oficial');
    }
}

const BASE_URL = endpoints[ARCHITECTURE];

// Configurações do teste
export const options = {
    vus: VUS,
    duration: DURATION,

    summaryTrendStats: [
        'avg',
        'min',
        'med',
        'max',
        'p(90)',
        'p(95)',
        'p(99)'
    ],

    // Critérios de sucesso do aquecimento
    thresholds: PHASE === 'warmup' ? {
        http_req_failed: ['rate==0'],
        checks: ['rate==1']
    } : {}
};

// Prompt e resposta esperada, compartilhados entre a requisição e a validação
const PROMPT = 'Teste de desempenho';
const EXPECTED_RESPONSE = `Resposta simulada para: ${PROMPT}`;

// Corpo da requisição
const payload = JSON.stringify({
    prompt: PROMPT,
    delayMs: DELAY_MS
});

// Cabeçalhos HTTP
const params = {
    headers: {
        'Content-Type': 'application/json'
    }
};

// Execução do teste
export default function () {
    const response = http.post(BASE_URL, payload, params);

    let body;

    try {
        body = response.json();
    } catch {
        body = null;
    }

    check(response, {
        'status HTTP 200': (r) => r.status === 200,

        'resposta valida': () =>
            body?.response === EXPECTED_RESPONSE,

        'tempo de processamento valido': () =>
            Number.isFinite(body?.processingTimeMs) &&
            body.processingTimeMs >= DELAY_MS
    });
}

export function handleSummary(data) {
    // Identificação dos arquivos
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');

    const filename = RUN_ID || `${SCENARIO_ID}_${ARCHITECTURE}_${DELAY_MS}ms_${VUS}vus_${DURATION}_${PHASE}_rep${REPETITION}_${timestamp}`;

    const directory = `performance-tests/results/${EXPERIMENT_TYPE}/${PHASE}`;

    // Extração das métricas do k6
    const latency = data.metrics.http_req_duration.values;
    const requests = data.metrics.http_reqs.values;
    const failures = data.metrics.http_req_failed.values;
    const checks = data.metrics.checks.values;

    // Consolidação dos resultados
    const result = {
        run_id: filename,
        timestamp: timestamp,
        experiment_type: EXPERIMENT_TYPE,
        phase: PHASE,
        scenario_id: SCENARIO_ID,
        repetition: REPETITION,
        architecture: ARCHITECTURE,
        delay_ms: DELAY_MS,
        vus: VUS,
        duration: DURATION,
        total_requests: requests.count,
        throughput: requests.rate,
        latency_avg_ms: latency.avg,
        latency_min_ms: latency.min,
        latency_med_ms: latency.med,
        latency_max_ms: latency.max,
        latency_p90_ms: latency['p(90)'],
        latency_p95_ms: latency['p(95)'],
        latency_p99_ms: latency['p(99)'],
        error_rate_percent: failures.rate * 100,
        check_success_percent: checks.rate * 100,
        check_failure_percent: (1 - checks.rate) * 100
    };

    // Conversão para CSV
    const csv = [
        Object.keys(result).join(','),
        Object.values(result).join(',')
    ].join('\n');

    // Exportação em JSON, CSV e terminal
    return {
        [`${directory}/${filename}.json`]: JSON.stringify({
            scenario: result,
            summary: data
        }, null, 4),
        [`${directory}/${filename}.csv`]: csv,
        stdout: JSON.stringify(result, null, 4) + '\n'
    };
}
