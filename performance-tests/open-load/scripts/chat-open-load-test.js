import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';
import { Counter, Rate } from 'k6/metrics';

// Experimento complementar: carga aberta. Nao altera o teste oficial.
const endpoints = {
    monolith: 'http://localhost:8080/chat',
    microservices: 'http://localhost:8081/chat',
};
const ARCHITECTURE = __ENV.ARCHITECTURE || 'monolith';
const MODE = __ENV.MODE || 'pilot';
const RUN_ID = __ENV.RUN_ID || 'diagnostic';
const SUMMARY_PATH = __ENV.SUMMARY_PATH || '';

function integer(name, fallback, min, max) {
    const value = Number(__ENV[name] ?? fallback);
    if (!Number.isSafeInteger(value) || value < min || value > max) {
        throw new Error(`Parametro invalido: ${name}`);
    }
    return value;
}

const DELAY_MS = integer('DELAY_MS', 100, 100, 2000);
if (!Object.keys(endpoints).includes(ARCHITECTURE)) {
    throw new Error('Arquitetura invalida');
}
if (![100, 500, 2000].includes(DELAY_MS)) {
    throw new Error('Delay invalido');
}
if (!['pilot', 'constant'].includes(MODE)) {
    throw new Error('Modo invalido');
}
if (!/^[a-zA-Z0-9_-]+$/.test(RUN_ID)) {
    throw new Error('RUN_ID invalido');
}

// Niveis candidatos; a matriz definitiva depende dos pilotos.
const NOMINAL_CONCURRENCY = [10, 50, 100, 150, 200, 250, 300];
const PILOT_LEVELS = integer('PILOT_LEVELS', 3, 1, 7);
const HOLD_SECONDS = integer('HOLD_SECONDS', 60, 10, 600);
const RAMP_SECONDS = integer('RAMP_SECONDS', 10, 1, 120);
const DURATION_SECONDS = integer('DURATION_SECONDS', 60, 1, 3600);
const RATE = integer('RATE', 10000 / DELAY_MS, 1, 10000);
const rates = NOMINAL_CONCURRENCY.slice(0, PILOT_LEVELS)
    .map(n => n * 1000 / DELAY_MS);

// Pre-alocacao fixa, sem criacao dinamica de VUs durante a carga.
// Estes valores sao candidatos e devem ser calibrados no host.
const peakRate = MODE === 'pilot' ? rates[rates.length - 1] : RATE;
const defaultVUs = Math.max(2, Math.ceil(2 * peakRate * DELAY_MS / 1000));
const PRE_ALLOCATED_VUS = integer('PRE_ALLOCATED_VUS', defaultVUs, 1, 2000);

const stages = [];
const segments = [];
let elapsed = 0;
function addSegment(seconds, from, target, kind) {
    stages.push({ duration: `${seconds}s`, target });
    segments.push({ index: segments.length + 1, kind, start_s: elapsed,
        end_s: elapsed + seconds, start_rate: from, end_rate: target });
    elapsed += seconds;
}
if (MODE === 'pilot') {
    rates.forEach((rate, index) => {
        if (index > 0) addSegment(RAMP_SECONDS, rates[index - 1], rate, 'ramp');
        addSegment(HOLD_SECONDS, rate, rate, 'hold');
    });
} else {
    segments.push({ index: 1, kind: 'hold', start_s: 0,
        end_s: DURATION_SECONDS, start_rate: RATE, end_rate: RATE });
    elapsed = DURATION_SECONDS;
}
const plannedIterations = segments.reduce((sum, s) => sum +
    (s.end_s - s.start_s) * (s.start_rate + s.end_rate) / 2, 0);
const common = { timeUnit: '1s', preAllocatedVUs: PRE_ALLOCATED_VUS,
    maxVUs: PRE_ALLOCATED_VUS, gracefulStop: '30s' };

export const options = {
    scenarios: {
        open_load: MODE === 'pilot' ? {
            ...common, executor: 'ramping-arrival-rate',
            startRate: rates[0], stages,
        } : {
            ...common, executor: 'constant-arrival-rate',
            rate: RATE, duration: `${DURATION_SECONDS}s`,
        },
    },
    summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
    // Uma falha sob carga e um resultado, nao um motivo automatico para exclusao.
    thresholds: {},
};

const started = new Counter('open_iterations_started');
const completed = new Counter('open_iterations_completed');
const valid = new Counter('open_requests_valid');
const validRate = new Rate('open_request_valid_rate');
const PROMPT = 'Teste de desempenho';
const EXPECTED_RESPONSE = `Resposta simulada para: ${PROMPT}`;
const payload = JSON.stringify({ prompt: PROMPT, delayMs: DELAY_MS });

function segmentTag() {
    const seconds = (Date.now() - exec.scenario.startTime) / 1000;
    const segment = segments.find(s => seconds >= s.start_s && seconds < s.end_s);
    return segment ? String(segment.index) : 'outside';
}

export default function () {
    // Classifica por inicio da iteracao, inclusive quando a resposta chega depois.
    const tags = { arrival_segment: segmentTag() };
    started.add(1, tags);
    const response = http.post(endpoints[ARCHITECTURE], payload, {
        headers: { 'Content-Type': 'application/json' },
        tags,
        // Mesmo timeout HTTP padrao (60s); evita requisicoes extras por redirecionamento.
        timeout: '60s', redirects: 0,
    });
    let body;
    try { body = response.json(); } catch { body = null; }
    const ok = check(response, {
        'status HTTP 200': r => r.status === 200,
        'resposta valida': () => body?.response === EXPECTED_RESPONSE,
        'tempo de processamento valido': () =>
            Number.isFinite(body?.processingTimeMs) && body.processingTimeMs >= DELAY_MS,
    }, tags);
    valid.add(ok ? 1 : 0, tags);
    validRate.add(ok, tags);
    completed.add(1, tags);
}

export function handleSummary(data) {
    // Conserva o resumo original, evitando depender de uma estrutura de metricas especifica.
    const result = {
        experiment: {
            run_id: RUN_ID, experiment_type: 'open-load', mode: MODE,
            architecture: ARCHITECTURE, delay_ms: DELAY_MS,
            duration_seconds: elapsed, graceful_stop_seconds: 30,
            http_timeout_seconds: 60, pre_allocated_vus: PRE_ALLOCATED_VUS,
            max_vus: PRE_ALLOCATED_VUS, planned_iterations_nominal: plannedIterations,
            segments,
        },
        summary: data,
    };
    const json = JSON.stringify(result, null, 2) + '\n';
    // O runner futuro devera criar o diretorio e impedir sobrescritas.
    const output = { stdout: json };
    if (SUMMARY_PATH) output[SUMMARY_PATH] = json;
    return output;
}