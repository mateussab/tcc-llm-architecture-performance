import csv
import json
import runpy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

script = Path('performance-tests/scripts/run-experiments.py').resolve()
if len(sys.argv) > 1:
    script = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(script.parent))
ns = runpy.run_path(str(script))
g = ns['execute_official_experiments'].__globals__
plan = g['randomize_experimental_runs'](g['create_experimental_runs'](g['create_experimental_scenarios']()))
g['validate_experimental_plan'](plan)
runs = plan[:2]


def fixture(run):
    run_id = g['experiment_prefix'](run) + 'synthetic_test'
    latency = run['delay_ms'] + 10
    for phase in ('warmup', 'measurement'):
        j, c, raw, resources = g['result_paths'](run_id, 'official', phase)
        j.parent.mkdir(parents=True, exist_ok=True)
        data = dict(run, run_id=run_id, timestamp='2026-11-26T00:00:00Z',
                    experiment_type='official', phase=phase, duration='60s',
                    total_requests=1, throughput=1/60, error_rate_percent=0,
                    check_success_percent=100, check_failure_percent=0)
        for metric in ('avg', 'min', 'med', 'max', 'p90', 'p95', 'p99'):
            data[f'latency_{metric}_ms'] = latency
        j.write_text(json.dumps({'scenario': data, 'summary': {'metrics': {
            'http_reqs': {'values': {'count': 1, 'rate': 1/60}}}}}), encoding='utf-8')
        with c.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(data)); w.writeheader(); w.writerow(data)
        with raw.open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f); w.writerow(['metric_name', 'metric_value'])
            w.writerows([('http_reqs', 1), ('iterations', 1), ('http_req_duration', latency),
                         ('http_req_failed', 0)] + [('checks', 1)] * 3)
        services = ['monolith'] if run['architecture'] == 'monolith' else ['chat-service', 'llm-service']
        with resources.open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['timestamp_utc', 'elapsed_seconds', 'source', 'container',
                        'cpu_percent', 'memory_percent', 'memory_usage', 'error'])
            for t in (10, 20, 30, 40, 50):
                w.writerow(['2026-11-26T00:00:00+00:00', t, 'host', '', 5, 20, '100 B', ''])
                for service in services:
                    w.writerow(['2026-11-26T00:00:00+00:00', t, 'container', f'test-{service}-1', 5, 20, '10MiB / 1GiB', ''])
    return run_id


def simulated_run(run, experiment_type):
    assert experiment_type == 'official'
    fixture(run)


def reject(action):
    try:
        action()
    except (ValueError, RuntimeError, FileNotFoundError):
        return
    raise AssertionError('Resultado inválido foi aceito')


with tempfile.TemporaryDirectory() as tmp:
    # Redireciona todos os caminhos do runner para o diretório temporário.
    with patch.dict(g, {'PROJECT_ROOT': Path(tmp)}), \
         patch.dict(g, {'check_tool_availability': lambda: None}):
        execute = g['execute_official_experiments']
        key1, key2 = map(g['get_experiment_key'], runs)
        with patch.dict(g, {'execute_experimental_run': simulated_run}):
            reject(lambda: execute(runs, 1, False))
            assert not g['load_completed_runs']()
            first_id = fixture(runs[0])
            execute(runs, 1, True)
            assert g['load_completed_runs']() == {key1, key2}
            print('OK: recuperação sem checkpoint e registro da próxima execução')
        def forbidden(*args, **kwargs):
            raise AssertionError('Nova execução indevida')
        with patch.dict(g, {'execute_experimental_run': forbidden}):
            execute(runs, 1, True)
            print('OK: retomada sem repetição')
            path = g['result_paths'](first_id, 'official', 'measurement')[-1]
            contents = path.read_bytes()
            path.unlink()
            reject(lambda: execute(runs, 1, True))
            assert g['load_completed_runs']() == {key1, key2}
            path.write_bytes(contents)
            print('OK: checkpoint com arquivo ausente é rejeitado')
            extra = path.parent / (g['experiment_prefix'](runs[0]) + 'extra_raw.csv')
            extra.write_text('teste', encoding='utf-8')
            reject(lambda: execute(runs, 1, True))
            assert extra.exists()
            extra.unlink()
            print('OK: artefato excedente rejeitado e preservado')
            unexpected = path.parent / 'unexpected.csv'
            unexpected.write_text('teste', encoding='utf-8')
            reject(lambda: execute(runs, 1, True))
            assert unexpected.exists()
            unexpected.unlink()
            print('OK: prefixo inesperado rejeitado e preservado')
            g['save_completed_runs'](set())
            path.unlink()
            reject(lambda: execute(runs, 1, True))
            assert not g['load_completed_runs']()
            print('OK: execução parcial sem checkpoint rejeitada')
print('Todos os testes de checkpoint passaram; nenhum Docker ou k6 executado.')
