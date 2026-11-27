"""Análise exploratória dos pilotos de carga aberta (somente biblioteca padrão)."""
import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean

# Contadores que serão conferidos com os resultados do k6.
COUNTERS = ['open_iterations_started', 'open_iterations_completed',
            'open_requests_valid', 'http_reqs', 'dropped_iterations']


def read_json(path):
    """Lê um JSON e devolve um dicionário Python (semelhante a um Map em Java)."""
    with path.open(encoding='utf-8-sig') as file:
        return json.load(file)


def save_csv(path, rows, columns):
    # O cabeçalho é gravado mesmo quando não há linhas (ex.: zero descartes).
    with path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def percentile(values, p):
    # Recebe valores já ordenados. Interpolação linear entre posições vizinhas.
    # Exemplo: P95 usa p=0.95, e não 95.
    position = (len(values) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def latency_stats(values):
    if not values:
        return dict(mean_ms=None, p50_ms=None, p95_ms=None, p99_ms=None, max_ms=None)
    values.sort()
    return dict(mean_ms=mean(values), p50_ms=percentile(values, .50),
                p95_ms=percentile(values, .95), p99_ms=percentile(values, .99),
                max_ms=values[-1])


def segment_tag(row):
    # O k6 grava a tag arrival_segment no campo extra_tags.
    # A categoria outside (ou tag ausente) não deve ser descartada.
    for tag in row['extra_tags'].replace('&', ',').split(','):
        if tag.startswith('arrival_segment='):
            return tag.split('=', 1)[1]
    return 'missing'


def read_requests(path):
    """Percorre o CSV uma vez: soma contadores e guarda apenas as latências."""
    counts = defaultdict(lambda: dict.fromkeys(COUNTERS, 0))
    latencies = defaultdict(list)
    drops = defaultdict(int)
    first_start = None
    with path.open(encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            metric = row['metric_name']
            if metric not in COUNTERS and metric != 'http_req_duration':
                continue
            value = float(row['metric_value'])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f'Valor inválido: {metric}')
            if metric in COUNTERS and not value.is_integer():
                raise ValueError(f'Contador não inteiro: {metric}')
            if metric == 'dropped_iterations':
                # O descarte ocorre antes da execução do JS: não tem tag de chegada.
                drops[int(row['timestamp'])] += int(value)
                continue
            tag = segment_tag(row)
            if metric == 'http_req_duration':
                latencies[tag].append(value)
            else:
                counts[tag][metric] += int(value)
            if metric == 'open_iterations_started':
                timestamp = int(row['timestamp'])
                if first_start is None or timestamp < first_start:
                    first_start = timestamp
    return counts, latencies, drops, first_start


def memory_mib(text):
    # Host e k6 fornecem bytes; Docker normalmente fornece KiB, MiB ou GiB.
    number, unit = re.fullmatch(r'([0-9.]+)\s*([A-Za-z]+)', text.split('/')[0].strip()).groups()
    factors = {'B': 1 / 1024**2, 'KiB': 1 / 1024, 'MiB': 1,
               'GiB': 1024, 'TiB': 1024**2, 'kB': 1000 / 1024**2,
               'KB': 1000 / 1024**2, 'MB': 1000**2 / 1024**2,
               'GB': 1000**3 / 1024**2}
    return float(number) * factors[unit]


def read_resources(path, segments):
    # Considera apenas patamares estáveis, com margem de 5 s nas bordas.
    # O relógio do monitor é aproximado; não é o relógio interno do k6.
    groups = defaultdict(list)
    with path.open(encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            if row['status'] != 'ok':
                continue
            t = float(row['elapsed_seconds'])
            for s in segments:
                if s['kind'] == 'hold' and s['start_s'] + 5 <= t < s['end_s'] - 5:
                    key = (s['index'], s['start_rate'], row['source'], row['container'])
                    groups[key].append((float(row['cpu_percent']), memory_mib(row['memory_usage']),
                                        float(row['memory_percent'])))
                    break
    rows = []
    for (segment, rate, source, container), samples in sorted(groups.items()):
        cpu = [sample[0] for sample in samples]
        memory = [sample[1] for sample in samples]
        rows.append(dict(segment=segment, rate=rate, source=source, container=container,
                         samples=len(samples), cpu_mean_pct=mean(cpu), cpu_max_pct=max(cpu),
                         memory_mean_mib=mean(memory), memory_max_mib=max(memory),
                         memory_mean_pct=mean([sample[2] for sample in samples])))
    return rows


def analyze(run):
    # 1. Lê os metadados e verifica se o piloto terminou corretamente.
    phase = run / 'measurement'
    outcome = read_json(run / 'outcome.json')
    if outcome['status'] != 'completed' or outcome.get('error') or outcome.get('cleanup_error'):
        raise ValueError('Piloto não concluído corretamente.')
    data = read_json(phase / 'summary.json')
    exp = data['experiment']
    metrics = data['summary']['metrics']
    validation = read_json(phase / 'validation.json')
    if exp['mode'] != 'pilot' or exp['experiment_type'] != 'open-load':
        raise ValueError('Informe uma pasta de piloto de carga aberta.')
    segments = exp['segments']
    warnings = list(validation.get('warnings', []))

    # 2. Confere as contagens brutas com o resumo e a validação do runner.
    counts, latencies, drops, first_start = read_requests(phase / 'raw.csv')
    totals = {name: sum(c[name] for c in counts.values()) for name in COUNTERS}
    totals['dropped_iterations'] = sum(drops.values())
    for name in COUNTERS:
        if name != 'dropped_iterations' and name not in metrics:
            raise ValueError(f'Métrica ausente: {name}')
        expected = metrics[name]['values']['count'] if name in metrics else 0
        if totals[name] != expected or totals[name] != validation[name]:
            raise ValueError(f'Contagem divergente: {name}')
    if not 0 <= totals['open_requests_valid'] <= totals['open_iterations_completed'] <= totals['open_iterations_started']:
        raise ValueError('Contadores de iterações inconsistentes.')
    if sum(len(v) for v in latencies.values()) != totals['http_reqs']:
        warnings.append('Quantidade de amostras de latência diferente de http_reqs.')

    # 3. Produz uma linha por segmento, incluindo tags fora da agenda.
    schedule = {str(s['index']): s for s in segments}
    extra = sorted((set(counts) | set(latencies)) - set(schedule))
    if extra:
        warnings.append('Categorias fora da agenda preservadas: ' + ', '.join(extra))
    rows = []
    for tag in list(schedule) + extra:
        s = schedule.get(tag)
        duration = s['end_s'] - s['start_s'] if s else None
        # Para uma rampa linear, a taxa média é a média das taxas inicial e final.
        nominal = duration * (s['start_rate'] + s['end_rate']) / 2 if s else None
        c = counts[tag]
        valid = c['open_requests_valid']
        rows.append(dict(segment=tag, kind=s['kind'] if s else 'unassigned',
                         start_s=s['start_s'] if s else None, end_s=s['end_s'] if s else None,
                         start_rate=s['start_rate'] if s else None, end_rate=s['end_rate'] if s else None,
                         nominal_iterations=nominal, started=c['open_iterations_started'],
                         completed=c['open_iterations_completed'], valid=valid, http_reqs=c['http_reqs'],
                         latency_samples=len(latencies[tag]),
                         valid_per_nominal_pct=100 * valid / nominal if nominal else None,
                         valid_cohort_rps=valid / duration if duration else None,
                         **latency_stats(latencies[tag])))
    if sum(r['nominal_iterations'] or 0 for r in rows) != exp['planned_iterations_nominal']:
        raise ValueError('Volume nominal dos segmentos divergente.')

    # 4. Agrupa descartes em janelas aproximadas de 10 segundos.
    windows = defaultdict(int)
    for timestamp, count in drops.items():
        window = ((timestamp - first_start) // 10) * 10 if first_start is not None else None
        windows[window] += count
    drop_rows = [dict(window_start_s=w, window_end_s=w + 10 if w is not None else None,
                      dropped=n) for w, n in sorted(windows.items())]
    resources = read_resources(phase / 'resources.csv', segments)
    if not resources or validation.get('resource_errors'):
        warnings.append('Monitoramento de recursos requer revisão.')

    # 5. Consolida o resultado global. Diferença nominal não é sinônimo de descarte.
    nominal = exp['planned_iterations_nominal']
    summary = dict(run_id=run.name, architecture=exp['architecture'], delay_ms=exp['delay_ms'],
                   pre_allocated_vus=exp['pre_allocated_vus'], max_vus=exp['max_vus'],
                   nominal_iterations=nominal, **totals,
                   valid_per_nominal_pct=100 * totals['open_requests_valid'] / nominal,
                   nominal_minus_started_and_dropped=nominal - totals['open_iterations_started'] - totals['dropped_iterations'],
                   vus_max_observed=metrics.get('vus', {}).get('values', {}).get('max'),
                   http_failure_rate=metrics.get('http_req_failed', {}).get('values', {}).get('rate'),
                   **latency_stats([v for group in latencies.values() for v in group]))

    # 6. Escreve SOMENTE na pasta de análise, preservando os dados brutos.
    out = run.parent.parent / 'analysis' / 'pilots' / run.name
    out.mkdir(parents=True, exist_ok=True)
    save_csv(out / 'pilot-summary.csv', [summary], list(summary))
    save_csv(out / 'segment-statistics.csv', rows, list(rows[0]))
    save_csv(out / 'drop-windows.csv', drop_rows, ['window_start_s', 'window_end_s', 'dropped'])
    save_csv(out / 'resource-statistics.csv', resources, ['segment', 'rate', 'source', 'container',
                                                          'samples', 'cpu_mean_pct', 'cpu_max_pct', 'memory_mean_mib', 'memory_max_mib', 'memory_mean_pct'])
    report = dict(integrity='OK', warnings=warnings, summary=summary, notes=[
        'Percentis: interpolação linear; latências incluem respostas com falha, se houver.',
        'Taxa válida por segmento: coorte de início / duração nominal, não vazão de conclusão.',
        'Descartes: janelas aproximadas, sem associação exata ao segmento.',
        'Recursos: patamares com margem de 5 s; CPU host e CPU k6/Docker têm escalas distintas.',
        'Integridade OK significa conferência dos contadores, não ausência de falhas nem saturação.'
    ])
    with (out / 'analysis-report.json').open('w', encoding='utf-8') as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
    print(f'\n{run.name}\nIntegridade dos contadores: OK')
    print(f'Válidas: {totals["open_requests_valid"]} | Descartadas: {totals["dropped_iterations"]}')
    for row in rows:
        print(f'Segmento {row["segment"]}: válidas={row["valid"]}, média={row["mean_ms"]}, P95={row["p95_ms"]}, P99={row["p99_ms"]}')
    for warning in warnings:
        print('AVISO:', warning)
    print('Resultados:', out)


def main():
    # Permite informar uma ou mais pastas pelo terminal, sem caminhos fixos.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', type=Path, nargs='+', help='Pastas dos pilotos concluídos')
    args = parser.parse_args()
    for run in args.runs:
        analyze(run.resolve())


# Executa main apenas quando o arquivo é chamado diretamente pelo Python.
if __name__ == '__main__':
    main()
