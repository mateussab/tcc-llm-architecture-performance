import http from 'k6/http';
import { check } from 'k6';

// Parâmetros do experimento
const ARCHITECTURE = __ENV.ARCHITECTURE || 'monolith';
const DELAY_MS = Number(__ENV.DELAY_MS || 100);
const VUS = Number(__ENV.VUS || 1);
const DURATION = __ENV.DURATION || '30s';

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
    ]
};

// Corpo da requisição
const payload = JSON.stringify({
    prompt: 'Teste de desempenho',
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

    check(response, {
        'status HTTP 200': (r) => r.status === 200
    });
}

// Consolidação e exportação dos resultados do teste
export function handleSummary(data) {

    const timestamp = new Date()
        .toISOString()
        .replace(/[:.]/g, '-');

    const filename =
        `${ARCHITECTURE}_${DELAY_MS}ms_${VUS}vus_${DURATION}_${timestamp}`;

    const directory = 'performance-tests/results';

    const latency = data.metrics.http_req_duration.values;
    const requests = data.metrics.http_reqs.values;
    const failures = data.metrics.http_req_failed.values;

    const result = {
        timestamp: timestamp,
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
        error_rate_percent: failures.rate * 100
    };

    const csv = [
        Object.keys(result).join(','),
        Object.values(result).join(',')
    ].join('\n');

    return {
        [`${directory}/${filename}.json`]:
            JSON.stringify({ scenario: result, summary: data }, null, 4),

        [`${directory}/${filename}.csv`]: csv,

        stdout: JSON.stringify(result, null, 4) + '\n'
    };
}
