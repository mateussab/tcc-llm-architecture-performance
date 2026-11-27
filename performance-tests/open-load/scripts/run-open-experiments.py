"""Runner complementar: smoke e pilotos de carga aberta. Nao altera os dados oficiais."""
import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

from open_load_resource_monitor import monitor_open_load

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).with_name('chat-open-load-test.js')
RESULTS = ROOT / 'performance-tests' / 'results'
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml')]
SERVICES = {'monolith': ('monolith',), 'microservices': ('chat-service', 'llm-service')}
IMAGES = {'monolith': 'tcc-llm-monolith:1.0', 'chat-service': 'tcc-chat-service:1.0',
          'llm-service': 'tcc-llm-service:1.0'}
NOMINAL = (10, 50, 100, 150, 200, 250, 300)
PROMPT = 'Teste de desempenho'


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('plan-only', 'smoke', 'pilot'), default='plan-only')
    p.add_argument('--architecture', choices=tuple(SERVICES), default='monolith')
    p.add_argument('--delay-ms', type=int, choices=(100, 500, 2000), default=100)
    p.add_argument('--pilot-levels', type=int, choices=range(1, 8), default=3)
    p.add_argument('--pre-allocated-vus', type=int, default=None)
    p.add_argument('--confirm-open-load', action='store_true')
    args = p.parse_args()
    if args.pre_allocated_vus is not None and not 1 <= args.pre_allocated_vus <= 2000:
        p.error('--pre-allocated-vus deve estar entre 1 e 2000')
    if args.mode != 'plan-only' and not args.confirm_open_load:
        p.error('Execucao exige --confirm-open-load')
    return args


def build_plan(args):
    smoke = args.mode == 'smoke'
    delay = args.delay_ms
    rates = [n * 1000 // delay for n in NOMINAL[:args.pilot_levels]]
    if smoke:
        rates = [max(1, 1000 // delay)]  # concorrencia nominal proxima de 1
    vus = args.pre_allocated_vus or (10 if smoke else 2 * NOMINAL[args.pilot_levels - 1])
    hold, ramp = 60, 10
    duration = 30 if smoke else len(rates)*hold + (len(rates)-1)*ramp
    warmup = 20 if smoke else 60
    planned = rates[0]*duration if smoke else sum(rates)*hold + sum(
        (a+b)*ramp/2 for a,b in zip(rates, rates[1:]))
    return dict(mode='smoke' if smoke else 'pilot', architecture=args.architecture,
                delay_ms=delay, rates=rates, pilot_levels=args.pilot_levels,
                pre_allocated_vus=vus, max_vus=vus, hold_seconds=hold, ramp_seconds=ramp,
                warmup_seconds=warmup, measurement_seconds=duration,
                planned_measurement_iterations=int(planned), cooldown_seconds=10)


def capture(command, timeout=60):
    return subprocess.check_output(command, cwd=ROOT, text=True, encoding='utf-8',
                                   errors='replace', timeout=timeout).strip()


def run_logged(command, path, timeout=180):
    with path.open('x', encoding='utf-8') as out:
        subprocess.run(command, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                       check=True, timeout=timeout)


def write_json(path, data):
    with path.open('x', encoding='utf-8') as out:
        json.dump(data, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write('\n')


@contextmanager
def experiment_lock():
    # Mesma trava utilizada pelo runner oficial.
    lock = RESULTS / '.experiment-runner.lock'
    RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise RuntimeError(f'Lock existente: {lock}. Verifique se ha outra coleta ativa.') from exc
    try:
        yield
    finally:
        lock.rmdir()


def ready(architecture):
    port = 8080 if architecture == 'monolith' else 8081
    req = request.Request(f'http://localhost:{port}/chat', method='POST',
                          data=json.dumps({'prompt': PROMPT, 'delayMs': 100}).encode(),
                          headers={'Content-Type': 'application/json'})
    deadline = time.monotonic() + 120
    last = None
    while time.monotonic() < deadline:
        try:
            with request.urlopen(req, timeout=5) as res:
                data = json.load(res)
                if (res.status == 200 and data.get('response') == 'Resposta simulada para: '+PROMPT
                        and data.get('processingTimeMs', -1) >= 100):
                    return
                last = 'Resposta invalida'
        except Exception as exc:
            last = str(exc)
        time.sleep(2)
    raise RuntimeError(f'API nao ficou pronta: {last}')


def phase_env(plan, phase, run_id, summary):
    pilot = phase == 'measurement' and plan['mode'] == 'pilot'
    duration = plan['warmup_seconds'] if phase == 'warmup' else plan['measurement_seconds']
    return dict(ARCHITECTURE=plan['architecture'], DELAY_MS=plan['delay_ms'],
                MODE='pilot' if pilot else 'constant', RUN_ID=run_id+'_'+phase,
                SUMMARY_PATH=str(summary), PRE_ALLOCATED_VUS=plan['pre_allocated_vus'],
                RATE=plan['rates'][0], DURATION_SECONDS=duration,
                PILOT_LEVELS=plan['pilot_levels'], HOLD_SECONDS=plan['hold_seconds'],
                RAMP_SECONDS=plan['ramp_seconds'])


def metric_count(metrics, name, optional=False):
    if optional and name not in metrics:
        return 0
    val = metrics[name]['values']['count']
    if not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0 or val != int(val):
        raise ValueError(f'Contador invalido: {name}={val}')
    return int(val)


def validate_phase(directory, env, nominal, expected_planned):
    data = json.loads((directory/'summary.json').read_text(encoding='utf-8'))
    meta = data['experiment']
    expected = dict(run_id=env['RUN_ID'], experiment_type='open-load', mode=env['MODE'],
                    architecture=env['ARCHITECTURE'], delay_ms=env['DELAY_MS'],
                    duration_seconds=nominal, pre_allocated_vus=env['PRE_ALLOCATED_VUS'],
                    max_vus=env['PRE_ALLOCATED_VUS'], planned_iterations_nominal=expected_planned)
    for key, value in expected.items():
        if meta.get(key) != value:
            raise ValueError(f'Metadado divergente: {key}: {meta.get(key)} != {value}')
    metrics = data['summary']['metrics']
    names = ('open_iterations_started', 'open_iterations_completed', 'open_requests_valid',
             'http_reqs', 'dropped_iterations')
    totals = {name: metric_count(metrics, name, optional=name=='dropped_iterations') for name in names}
    started, completed, valid, requests, dropped = (totals[n] for n in names)
    if not (0 <= valid <= completed <= started and completed <= requests <= started):
        raise ValueError(f'Contagens inconsistentes: {totals}')
    # Conferencia independente dos contadores brutos. Falhas da aplicacao nao invalidam a fase.
    raw_totals = dict.fromkeys(names, 0.0)
    rows = 0
    with (directory/'raw.csv').open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        if not {'metric_name', 'metric_value', 'timestamp'} <= set(reader.fieldnames or ()):
            raise ValueError('Cabecalho CSV bruto invalido')
        for row in reader:
            rows += 1
            name = row['metric_name']
            if name in raw_totals:
                value = float(row['metric_value'])
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f'Valor bruto invalido: {name}')
                raw_totals[name] += value
    if not rows or any(abs(raw_totals[n]-totals[n]) > 1e-6 for n in names):
        raise ValueError(f'Contagens JSON/CSV divergentes: {totals} / {raw_totals}')
    warnings = []
    if started != completed:
        warnings.append('Iteracoes iniciadas e nao concluidas (preservar como resultado).')
    if abs(started + dropped - expected_planned) > max(2, expected_planned*0.01):
        warnings.append('Diferenca entre agenda nominal e contagem iniciada + descartada; investigar.')
    resources = list(csv.DictReader((directory/'resources.csv').open(encoding='utf-8', newline='')))
    errors = [r for r in resources if r['status'] == 'error']
    k6_rows = [r for r in resources if r['source'] == 'k6' and r['status'] == 'ok']
    if errors or not k6_rows:
        warnings.append('Monitoramento incompleto ou com erros; nao interpretar recursos sem revisao.')
    # Numero de ciclos e amostras por fonte: diagnostico, nao certificacao temporal.
    result = dict(planned_iterations_nominal=expected_planned, **totals,
                  valid_per_nominal=valid/expected_planned, nominal_valid_rate_rps=valid/nominal,
                  resources_rows=len(resources), k6_samples=len(k6_rows),
                  resource_errors=len(errors), warnings=warnings)
    write_json(directory/'validation.json', result)
    return result


def execute_phase(plan, phase, run_id, run_dir, ids):
    directory = run_dir / phase
    directory.mkdir()
    summary = directory / 'summary.json'
    env = phase_env(plan, phase, run_id, summary)
    duration = env['DURATION_SECONDS']
    planned = (plan['planned_measurement_iterations'] if phase == 'measurement'
               else plan['rates'][0]*duration)
    # Ambiente k6 explicito: nao herdar flags K6_* ou configuracao global do usuario.
    process_env = {k:v for k,v in os.environ.items() if not k.upper().startswith('K6_')}
    config = directory/'k6-config.json'
    write_json(config, {})
    command = ['k6', 'run', '--config', str(config), '--out', f'csv={directory/"raw.csv"}']
    for key, val in env.items():
        command.extend(['--env', f'{key}={val}'])
    command.append(str(SCRIPT))
    write_json(directory/'invocation.json', dict(command=command, environment=env,
               phase=phase, started_utc=datetime.now(timezone.utc).isoformat()))
    print(f'{phase}: {duration}s; {planned} iteracoes nominais', flush=True)
    with (directory/'k6.log').open('x', encoding='utf-8') as log:
        proc = subprocess.Popen(command, cwd=ROOT, env=process_env, stdout=log, stderr=subprocess.STDOUT)
        try:
            with monitor_open_load(directory/'resources.csv', ids, proc.pid, interval_seconds=10):
                code = proc.wait(timeout=duration+120)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    if code:
        raise RuntimeError(f'k6 terminou com codigo {code}; consultar {directory / "k6.log"}')
    result = validate_phase(directory, env, duration, planned)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def execute(plan):
    with experiment_lock():
        if capture(COMPOSE+['ps','-a','-q']):
            raise RuntimeError('Existem containers neste projeto. Nao vou encerra-los automaticamente.')
        services = SERVICES[plan['architecture']]
        run_id = f"{plan['mode']}_{plan['architecture']}_{plan['delay_ms']}ms_" + datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        run_dir = RESULTS/'open-load'/plan['mode']/run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        print(f'Resultados: {run_dir}', flush=True)
        started = False
        status = 'failed'
        problem = None
        try:
            metadata = dict(plan=plan, run_id=run_id, timestamp_utc=datetime.now(timezone.utc).isoformat(),
                            git_commit=capture(['git','rev-parse','HEAD']), git_status=capture(['git','status','--short']),
                            k6_version=capture(['k6','version']), docker_version=capture(['docker','version']),
                            python_version=capture(['python','--version']),
                            docker_resources=capture(['docker','info','--format','CPUs={{.NCPU}} MemBytes={{.MemTotal}}']),
                            image_ids={s:capture(['docker','image','inspect','--format','{{.Id}}', IMAGES[s]]) for s in services},
                            sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                    (SCRIPT, Path(__file__), Path(__file__).with_name('open_load_resource_monitor.py'), ROOT/'docker-compose.yml')})
            write_json(run_dir/'metadata.json', metadata)
            (run_dir/'compose-config.yml').write_text(capture(COMPOSE+['config'])+'\n', encoding='utf-8')
            started = True
            # Preservar imagens locais; nao baixar novas versoes ou reconstruir durante piloto.
            run_logged(COMPOSE+['up','-d','--no-build','--pull','never', services[0]], run_dir/'compose-up.log')
            ready(plan['architecture'])
            ids = capture(COMPOSE+['ps','--status','running','-q',*services]).splitlines()
            if len(ids) != len(services) or len(set(ids)) != len(services):
                raise RuntimeError('Containers ativos inconsistentes.')
            # Docker compose ps -q normalmente fornece IDs completos; normalizar explicitamente.
            ids = [capture(['docker','inspect','--format','{{.Id}}', i]) for i in ids]
            warmup = execute_phase(plan, 'warmup', run_id, run_dir, ids)
            # Aquecimento inicial de baixa carga: problemas impedem um piloto interpretavel.
            if (warmup['open_iterations_started'] != warmup['open_iterations_completed'] or
                    warmup['open_requests_valid'] != warmup['open_iterations_completed'] or
                    warmup['dropped_iterations'] or warmup['warnings']):
                raise RuntimeError('Aquecimento diagnostico nao passou; dados preservados.')
            measurement = execute_phase(plan, 'measurement', run_id, run_dir, ids)
            status = 'completed_with_warnings' if measurement['warnings'] else 'completed'
        except BaseException as exc:
            problem = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            cleanup_error = None
            if started:
                try:
                    run_logged(COMPOSE+['logs','--no-color'], run_dir/'compose-services.log')
                except Exception as exc:
                    print(f'Aviso: nao foi possivel coletar logs: {exc}', flush=True)
                try:
                    run_logged(COMPOSE+['down'], run_dir/'compose-down.log')
                except Exception as exc:
                    cleanup_error = str(exc)
                time.sleep(plan['cooldown_seconds'])
            write_json(run_dir/'outcome.json', dict(status=status, error=problem, cleanup_error=cleanup_error))
            if cleanup_error:
                print(f'ATENCAO: falha ao encerrar containers: {cleanup_error}', flush=True)
                if problem is None:
                    raise RuntimeError(cleanup_error)
        print(f'Finalizado: {status}', flush=True)


def main():
    args = parse_args()
    plan = build_plan(args)
    print(json.dumps(plan, indent=2), flush=True)
    if args.mode == 'plan-only':
        return
    execute(plan)


if __name__ == '__main__':
    main()
