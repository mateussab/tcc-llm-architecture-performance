"""Executa os 150 testes controlados de carga aberta, com retomada segura."""
import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).with_name('run-open-experiments.py')
RESULTS = ROOT / 'performance-tests' / 'results'
OUTPUT = RESULTS / 'open-load' / 'controlled'
LOCK = RESULTS / 'open-load' / '.controlled-batch.lock'
RATES = {100: (100, 500, 1000, 1500, 2000),
         500: (20, 100, 200, 300, 400),
         2000: (5, 25, 50, 75, 100)}
ARCHITECTURES = ('monolith', 'microservices')
SEED = 42
REPETITIONS = 5


def make_plan():
    # Cada bloco contem todos os 30 cenarios uma vez, em ordem aleatoria.
    rng = random.Random(SEED)
    plan = []
    for rep in range(1, REPETITIONS + 1):
        block = [dict(architecture=arch, delay_ms=delay, rate=rate, repetition=rep)
                 for arch in ARCHITECTURES for delay, rates in RATES.items() for rate in rates]
        rng.shuffle(block)
        plan.extend(block)
    return plan


def key(run):
    return f"{run['architecture']}_{run['delay_ms']}ms_{run['rate']}rps_rep{run['repetition']}"


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, data):
    # Substituicao atomica: nao deixa um checkpoint parcial em caso de interrupcao.
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    temp.replace(path)


def capture(command):
    return subprocess.check_output(command, cwd=ROOT, text=True, encoding='utf-8',
                                   errors='replace', timeout=60).strip()


def environment():
    # Congela os scripts, Compose, imagens e recursos do Docker. Nao compara
    # git status: novos arquivos de resultados nao modificam o experimento.
    files = (RUNNER, RUNNER.with_name('chat-open-load-test.js'),
             RUNNER.with_name('open_load_resource_monitor.py'), ROOT/'docker-compose.yml')
    images = ('tcc-llm-monolith:1.0', 'tcc-chat-service:1.0', 'tcc-llm-service:1.0')
    return dict(sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                image_ids={i: capture(['docker','image','inspect','--format','{{.Id}}',i]) for i in images},
                k6_version=capture(['k6','version']), docker_version=capture(['docker','version']),
                python_version=capture([sys.executable,'--version']),
                docker_resources=capture(['docker','info','--format','CPUs={{.NCPU}} MemBytes={{.MemTotal}}']))


def validate_completed(folder, run, baseline):
    # O runner individual ja compara os contadores JSON e CSV bruto.
    # Aqui verificamos a identidade e a presenca dos artefatos de cada fase.
    meta = read_json(folder/'metadata.json')
    plan = meta['plan']
    expected = dict(mode='controlled', architecture=run['architecture'], delay_ms=run['delay_ms'],
                    rates=[run['rate']], repetition=run['repetition'], pre_allocated_vus=400,
                    max_vus=400, warmup_seconds=60, measurement_seconds=60, cooldown_seconds=10,
                    planned_measurement_iterations=run['rate']*60)
    if any(plan.get(k) != v for k,v in expected.items()) or meta.get('run_id') != folder.name:
        raise RuntimeError(f'Metadados divergentes: {folder}')
    for field in ('sha256','k6_version','docker_version','python_version','docker_resources'):
        if meta.get(field) != baseline[field]:
            raise RuntimeError(f'Ambiente divergente ({field}): {folder}')
    expected_services = ('monolith',) if run['architecture']=='monolith' else ('chat-service','llm-service')
    if meta['image_ids'] != {s: baseline['image_ids'][f'tcc-llm-{s}:1.0'] if s=='monolith'
                            else baseline['image_ids'][f'tcc-{s}:1.0'] for s in expected_services}:
        raise RuntimeError(f'Imagens divergentes: {folder}')
    warnings = []
    for phase in ('warmup','measurement'):
        directory = folder/phase
        for name in ('summary.json','raw.csv','resources.csv','validation.json','invocation.json','k6.log','k6-config.json'):
            if not (directory/name).is_file() or not (directory/name).stat().st_size:
                raise RuntimeError(f'Artefato ausente/vazio: {directory/name}')
        validation = read_json(directory/'validation.json')
        if validation['planned_iterations_nominal'] != run['rate']*60:
            raise RuntimeError(f'Volume nominal divergente: {directory}')
        if validation['resource_errors'] or not validation['k6_samples']:
            raise RuntimeError(f'Monitoramento incompleto: {directory}. Revisao manual necessaria.')
        warnings.extend(f'{phase}: {w}' for w in validation.get('warnings', []))
    return warnings


def recover(plan, baseline):
    # Reconstrui o checkpoint pelos resultados em disco, inclusive se o processo
    # parou apos concluir um teste, mas antes de atualizar o checkpoint.
    planned = {key(r):r for r in plan}
    done, incomplete = {}, []
    pattern = re.compile(r'^controlled_(.+)_\d{8}_\d{6}_\d{6}$')
    for folder in sorted(OUTPUT.iterdir()):
        if not folder.is_dir():
            continue
        match = pattern.fullmatch(folder.name)
        if not match or match[1] not in planned:
            raise RuntimeError(f'Diretorio desconhecido: {folder}')
        label = match[1]
        outcome = read_json(folder/'outcome.json') if (folder/'outcome.json').exists() else {}
        if (outcome.get('status') not in ('completed','completed_with_warnings')
                or outcome.get('error') or outcome.get('cleanup_error')):
            incomplete.append(str(folder))
            continue
        if label in done:
            raise RuntimeError(f'Duas execucoes concluidas para {label}; revisar antes de continuar.')
        warnings = validate_completed(folder, planned[label], baseline)
        done[label] = dict(run_id=folder.name, status=outcome['status'], warnings=warnings)
    return done, incomplete


def checkpoint(plan, done, incomplete):
    path = OUTPUT/'completed-runs.json'
    if path.exists():
        previous = read_json(path)['runs']
        if any(label not in done or done[label]['run_id'] != item['run_id']
               for label, item in previous.items()):
            raise RuntimeError('Resultados registrados no checkpoint desapareceram ou mudaram.')
    save_json(path, dict(total=len(plan), completed=len(done),
              pending=len(plan)-len(done), runs=done, incomplete_attempts=incomplete))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('plan-only','run'), default='plan-only')
    parser.add_argument('--max-runs', type=int, help='Limita novas execucoes nesta chamada')
    parser.add_argument('--confirm-open-load', action='store_true')
    parser.add_argument('--retry-incomplete', action='store_true', help='Autoriza novas tentativas apos revisar falhas antigas')
    args = parser.parse_args()
    if args.max_runs is not None and args.max_runs < 1:
        parser.error('--max-runs deve ser positivo')
    plan = make_plan()
    if len(plan) != 150 or len({key(r) for r in plan}) != 150:
        raise RuntimeError('Plano experimental invalido')
    print(f'30 cenarios | 5 repeticoes | {len(plan)} execucoes | seed={SEED}', flush=True)
    if args.mode == 'plan-only':
        for index, run in enumerate(plan, 1):
            print(f'{index:03d} {key(run)}')
        return
    if not args.confirm_open_load:
        parser.error('Execucao exige --confirm-open-load')
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    # Impede dois lotes simultaneos. A trava do runner individual e independente.
    LOCK.mkdir()
    try:
        if (RESULTS/'.experiment-runner.lock').exists():
            raise RuntimeError('Existe trava do runner individual. Verifique se ha coleta ativa.')
        OUTPUT.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(OUTPUT).free < 25*1024**3:
            raise RuntimeError('Menos de 25 GiB livres no volume de resultados; libere espaco antes da coleta.')
        baseline = environment()
        manifest = OUTPUT/'experimental-plan.json'
        expected = dict(seed=SEED, repetitions=REPETITIONS, runs=plan, environment=baseline)
        if manifest.exists():
            if read_json(manifest) != expected:
                raise RuntimeError('Plano ou ambiente mudou. Nao misture coletas diferentes.')
        else:
            if any(p.is_dir() for p in OUTPUT.iterdir()):
                raise RuntimeError('Resultados controlados sem manifesto. Revisar antes de iniciar.')
            save_json(manifest, expected)
        done, incomplete = recover(plan, baseline)
        checkpoint(plan, done, incomplete)
        if incomplete and not args.retry_incomplete:
            raise RuntimeError('Tentativas incompletas preservadas. Revise o checkpoint antes de autorizar nova tentativa.')
        print(f'Retomada: {len(done)}/{len(plan)} concluidos.', flush=True)
        executed = 0
        for run in plan:
            label = key(run)
            if label in done:
                continue
            if args.max_runs is not None and executed >= args.max_runs:
                break
            if shutil.disk_usage(OUTPUT).free < 3*1024**3:
                raise RuntimeError('Menos de 3 GiB livres; coleta interrompida antes do proximo teste.')
            print(f'\n[{len(done)+1}/{len(plan)}] {label}', flush=True)
            command = [sys.executable, str(RUNNER), '--mode','controlled',
                       '--architecture',run['architecture'],'--delay-ms',str(run['delay_ms']),
                       '--rate',str(run['rate']),'--repetition',str(run['repetition']),
                       '--pre-allocated-vus','400','--confirm-open-load']
            # Espera o runner terminar; nunca roda duas arquiteturas em paralelo.
            subprocess.run(command, cwd=ROOT, check=True)
            done, incomplete = recover(plan, baseline)
            if label not in done:
                raise RuntimeError(f'Execucao sem resultado concluido: {label}')
            checkpoint(plan, done, incomplete)
            executed += 1
            print(f'Checkpoint: {len(done)}/{len(plan)}', flush=True)
        print(f'Concluidos: {len(done)}/{len(plan)}. Novos nesta chamada: {executed}.', flush=True)
    finally:
        LOCK.rmdir()


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print(f'Coleta interrompida: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
