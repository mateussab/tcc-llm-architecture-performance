import argparse
import csv
import json
import random
import subprocess
import time
import math
from contextlib import contextmanager

from datetime import datetime
from pathlib import Path
from urllib import error, request
from resource_monitor import monitor_resources


PROJECT_ROOT = Path(__file__).resolve().parents[2]
K6_SCRIPT = PROJECT_ROOT / "performance-tests" / "scripts" / "chat-load-test.js"

WARMUP_DURATION = "60s"
MEASUREMENT_DURATION = "60s"
REPETITIONS = 5
COOLDOWN_SECONDS = 10
STARTUP_TIMEOUT_SECONDS = 120
RANDOM_SEED = 42
PHASES = ("warmup", "measurement")
RESULT_SUFFIXES = (".json", ".csv", "_raw.csv", "_resources.csv")
METADATA_FIELDS = ("scenario_id", "architecture", "delay_ms", "vus", "repetition")


def results_directory(experiment_type, phase=None):
    """Centraliza os caminhos sem impedir a configuração de PROJECT_ROOT nos testes."""
    if experiment_type not in ("preliminary", "official"):
        raise ValueError("Tipo de experimento inválido.")
    root = PROJECT_ROOT / "performance-tests" / "results" / experiment_type
    if phase is None:
        return root
    if phase not in PHASES:
        raise ValueError("Fase experimental inválida.")
    return root / phase


def result_paths(run_id, experiment_type, phase):
    directory = results_directory(experiment_type, phase)
    return tuple(directory / f"{run_id}{suffix}" for suffix in RESULT_SUFFIXES)


def experiment_prefix(run):
    return (
        f"{run['scenario_id']}_{run['architecture']}_"
        f"{run['delay_ms']}ms_{run['vus']}vus_rep{run['repetition']}_"
    )


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Automação dos experimentos do TCC."
    )

    parser.add_argument(
        "--mode",
        choices=["plan-only", "preliminary", "official"],
        default="plan-only",
        help="Modo de execução do experimento."
    )

    parser.add_argument(
        "--max-runs",
        type=int,
        default=2,
        help="Número máximo de execuções por chamada nos modos preliminary e official (padrão: 2)."
    )

    parser.add_argument(
        "--confirm-official",
        action="store_true",
        help="Confirma explicitamente a execução dos experimentos oficiais."
    )

    return parser.parse_args()


# Gera as 24 combinações de arquitetura, latência simulada e usuários virtuais.
def create_experimental_scenarios():
    architectures = ["monolith", "microservices"]
    delays = [100, 500, 2000]
    virtual_users = [1, 10, 50, 100]

    scenarios = []

    for architecture in architectures:
        for delay in delays:
            for vus in virtual_users:
                scenario = {
                    "scenario_id": f"E{len(scenarios) + 1:02d}",
                    "architecture": architecture,
                    "delay_ms": delay,
                    "vus": vus,
                }

                scenarios.append(scenario)

    return scenarios


# Gera cinco repetições para cada um dos 24 cenários experimentais.
def create_experimental_runs(scenarios):
    runs = []

    for repetition in range(1, REPETITIONS + 1):
        for scenario in scenarios:
            run = {
                **scenario,
                "repetition": repetition,
            }

            runs.append(run)

    return runs


# Embaralha os cenários de cada repetição de forma reproduzível.
def randomize_experimental_runs(runs):
    rng = random.Random(RANDOM_SEED)
    randomized_runs = []

    for repetition in range(1, REPETITIONS + 1):
        repetition_runs = [
            run.copy()
            for run in runs
            if run["repetition"] == repetition
        ]

        rng.shuffle(repetition_runs)
        randomized_runs.extend(repetition_runs)

    return randomized_runs


# Verifica a quantidade e a distribuição dos cenários experimentais.
def validate_experimental_plan(runs):
    expected_scenarios = {
        f"E{number:02d}"
        for number in range(1, 25)
    }

    if len(runs) != 24 * REPETITIONS:
        raise ValueError("Quantidade incorreta de execuções.")

    for repetition in range(1, REPETITIONS + 1):
        repetition_runs = [
            run
            for run in runs
            if run["repetition"] == repetition
        ]

        scenario_ids = [
            run["scenario_id"]
            for run in repetition_runs
        ]

        if len(scenario_ids) != 24:
            raise ValueError(
                f"Repetição {repetition}: quantidade incorreta de cenários."
            )

        if set(scenario_ids) != expected_scenarios:
            raise ValueError(
                f"Repetição {repetition}: cenários ausentes ou duplicados."
            )

    expected_configurations = {
        scenario["scenario_id"]: scenario
        for scenario in create_experimental_scenarios()
    }

    for run in runs:
        expected = expected_configurations[run["scenario_id"]]

        for field in ("architecture", "delay_ms", "vus"):
            if run[field] != expected[field]:
                raise ValueError(
                    f"Cenário {run['scenario_id']}: "
                    f"valor incorreto para {field}."
                )


# Exporta o planejamento experimental em formato CSV.
def export_experimental_plan(runs, experiment_type):
    output_dir = results_directory(experiment_type)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]
    filename = f"experimental-plan_seed{RANDOM_SEED}_{timestamp}.csv"
    output_file = output_dir / filename

    fieldnames = [
        "ExecutionOrder",
        "ScenarioId",
        "Architecture",
        "DelayMs",
        "Vus",
        "Repetition",
        "RandomSeed",
        "ExperimentType",
    ]

    with output_file.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for execution_order, run in enumerate(runs, start=1):
            writer.writerow({
                "ExecutionOrder": execution_order,
                "ScenarioId": run["scenario_id"],
                "Architecture": run["architecture"],
                "DelayMs": run["delay_ms"],
                "Vus": run["vus"],
                "Repetition": run["repetition"],
                "RandomSeed": RANDOM_SEED,
                "ExperimentType": experiment_type.capitalize(),
            })

    return output_file


# Verifica se uma ferramenta está instalada e acessível pelo terminal.
def check_tool_availability():
    """Valida as ferramentas e a comunicação com o daemon antes da carga."""
    commands = (
        ("Docker", ["docker", "version"]),
        ("Docker Compose", ["docker", "compose", "version"]),
        ("k6", ["k6", "version"]),
    )
    for name, command in commands:
        try:
            subprocess.run(
                command, cwd=PROJECT_ROOT, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=20, check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            details = getattr(exc, "stderr", None) or str(exc)
            raise RuntimeError(f"{name} indisponível: {details}") from exc
        print(f"{name}: disponível")


# Inicia somente os serviços necessários à arquitetura selecionada.
def start_containers(architecture):
    services = {
        "monolith": "monolith",
        "microservices": "chat-service",
    }

    if architecture not in services:
        raise ValueError(f"Arquitetura inválida: {architecture}")

    print(f"Iniciando arquitetura: {architecture}")

    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(PROJECT_ROOT / "docker-compose.yml"),
            "up",
            "-d",
            "--build",
            services[architecture],
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    print(f"Arquitetura {architecture}: inicialização solicitada.")


# Encerra e remove os contêineres do ambiente experimental.
def stop_containers():
    print("Encerrando os contêineres...")

    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(PROJECT_ROOT / "docker-compose.yml"),
            "down",
            "--remove-orphans",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    print("Contêineres encerrados com sucesso.")


# Aguarda a API responder antes de iniciar os testes de carga.
def wait_for_api(architecture):
    ports = {"monolith": 8080, "microservices": 8081}
    if architecture not in ports:
        raise ValueError(f"Arquitetura inválida: {architecture}")

    url = f"http://localhost:{ports[architecture]}/chat"
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    payload = json.dumps({"prompt": "Teste de inicialização", "delayMs": 100}).encode("utf-8")
    http_request = request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    last_error = None
    print(f"Aguardando API: {url}")
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            with request.urlopen(http_request, timeout=min(5, remaining)) as response:
                if response.status == 200:
                    print(f"API {architecture}: pronta!")
                    return
                last_error = RuntimeError(f"HTTP {response.status}")
        except (error.URLError, OSError) as exc:
            last_error = exc
            if isinstance(exc, error.HTTPError):
                exc.close()
        time.sleep(max(0, min(2, deadline - time.monotonic())))
    raise TimeoutError(
        f"API {architecture} não ficou pronta em {STARTUP_TIMEOUT_SECONDS} segundos. "
        f"Último erro: {last_error}"
    ) from last_error


# Executa o k6 e salva as métricas brutas e consolidadas do experimento.
def run_k6(run, phase, duration, experiment_type, run_id):
    results_directory(experiment_type, phase).mkdir(parents=True, exist_ok=True)
    validate_result_paths(run_id, experiment_type, phases=(phase,))
    _, _, raw_file, resource_file = result_paths(run_id, experiment_type, phase)

    # Monta o comando de execução do k6.
    command = [
        "k6",
        "run",
        "--out", f"csv={raw_file}",
        "--vus", str(run["vus"]),
        "--duration", duration,
        "--env", f"ARCHITECTURE={run['architecture']}",
        "--env", f"DELAY_MS={run['delay_ms']}",
        "--env", f"VUS={run['vus']}",
        "--env", f"DURATION={duration}",
        "--env", f"PHASE={phase}",
        "--env", f"SCENARIO_ID={run['scenario_id']}",
        "--env", f"REPETITION={run['repetition']}",
        "--env", f"EXPERIMENT_TYPE={experiment_type}",
        "--env", f"RUN_ID={run_id}",
        str(K6_SCRIPT),
    ]

    print(
        f"Executando k6: {run['scenario_id']}, "
        f"arquitetura {run['architecture']}, "
        f"delay {run['delay_ms']}ms, "
        f"{run['vus']} VUs, "
        f"repetição {run['repetition']}, "
        f"fase {phase}, duração {duration}"
    )

    # Identifica os serviços da arquitetura avaliada.
    services = (
        ["monolith"]
        if run["architecture"] == "monolith"
        else ["chat-service", "llm-service"]
    )

    # Obtém os identificadores dos containers em execução.
    container_ids = subprocess.check_output(
        [
            "docker",
            "compose",
            "-f",
            str(PROJECT_ROOT / "docker-compose.yml"),
            "ps",
            "--status", "running",
            "-q",
            *services,
        ],
        cwd=PROJECT_ROOT,
        text=True,
    ).splitlines()

    if len(container_ids) != len(services):
        raise RuntimeError(
            "Quantidade de containers em execução inconsistente."
        )

    # Executa o k6 com monitoramento simultâneo de recursos.
    with monitor_resources(
            output_file=resource_file,
            container_ids=container_ids,
            interval_seconds=10,
    ):
        subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=True,
        )

    print(f"k6 finalizado: {run_id} ({phase})")


# Prepara os diretórios e o identificador único de uma execução.
def prepare_run_files(run, experiment_type):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_id = experiment_prefix(run) + timestamp
    for phase in PHASES:
        results_directory(experiment_type, phase).mkdir(parents=True, exist_ok=True)
    return run_id


# Impede que uma execução sobrescreva resultados existentes.
def validate_result_paths(run_id, experiment_type, phases=PHASES):
    for phase in phases:
        for result_file in result_paths(run_id, experiment_type, phase):
            if result_file.exists() or result_file.is_symlink():
                raise FileExistsError(f"Arquivo de resultado já existe: {result_file}")


# Executa, valida e finaliza um cenário experimental.
def execute_experimental_run(run, experiment_type):
    run_id = prepare_run_files(run, experiment_type)
    validate_result_paths(run_id, experiment_type)
    original_error = None
    try:
        stop_containers()
        start_containers(run["architecture"])
        wait_for_api(run["architecture"])

        # Cada fase é validada uma vez; a medição depende do aquecimento válido.
        for phase, duration in (("warmup", WARMUP_DURATION), ("measurement", MEASUREMENT_DURATION)):
            run_k6(run, phase, duration, experiment_type, run_id)
            validate_experimental_results(
                run_id, experiment_type, phases=(phase,), expected_run=run,
            )
        if experiment_type == "official":
            validate_official_artifact_set(run, run_id)
    except BaseException as exc:
        original_error = exc
        raise
    finally:
        try:
            stop_containers()
        except Exception as cleanup_error:
            if original_error is None:
                raise
            original_error.add_note(f"Falha adicional ao encerrar containers: {cleanup_error}")
            print(f"AVISO: falha no encerramento: {cleanup_error}")
        finally:
            print(f"Cooldown: {COOLDOWN_SECONDS} segundos")
            time.sleep(COOLDOWN_SECONDS)
    print(f"\nExecução validada e finalizada com sucesso: {run_id}")


# Executa um número limitado de experimentos preliminares.
def execute_preliminary_experiments(runs, max_runs):
    if not 1 <= max_runs <= len(runs):
        raise ValueError(
            f"max_runs deve estar entre 1 e {len(runs)}."
        )

    check_tool_availability()
    selected_runs = runs[:max_runs]

    print(f"Execuções preliminares selecionadas: {len(selected_runs)}")

    for index, run in enumerate(selected_runs, start=1):
        print(
            f"\nExecução {index}/{len(selected_runs)}: "
            f"{run['scenario_id']} | "
            f"{run['architecture']} | "
            f"{run['delay_ms']}ms | "
            f"{run['vus']} VUs | "
            f"repetição {run['repetition']}"
        )

        execute_experimental_run(run, "preliminary")

    print("\nExperimentos preliminares concluídos!")


# Verifica a existência e o conteúdo dos arquivos de uma execução.
def validate_run_files(run_id, experiment_type, phases=PHASES):
    for phase in phases:
        paths = result_paths(run_id, experiment_type, phase)
        # O monitoramento é obrigatório na coleta oficial; pilotos podem ser diagnósticos.
        for file_path in paths if experiment_type == "official" else paths[:3]:
            if not file_path.is_file():
                raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
            if file_path.stat().st_size == 0:
                raise ValueError(f"Arquivo vazio: {file_path}")
        print(f"Arquivos da fase {phase}: OK")
    print(f"Arquivos validados: {run_id}")


# Valida os campos e os valores das métricas consolidadas.
def validate_json_metrics(run_id, experiment_type, phase, expected_run=None):
    json_path = result_paths(run_id, experiment_type, phase)[0]

    # Carrega o JSON completo.
    with json_path.open("r", encoding="utf-8") as file:
        result = json.load(file)

    # Extrai as métricas consolidadas do cenário.
    if not isinstance(result, dict):
        raise ValueError("Estrutura JSON inválida.")

    data = result.get("scenario")

    if not isinstance(data, dict):
        raise ValueError("Objeto 'scenario' ausente ou inválido.")

    # Confere a presença dos dados detalhados do k6.
    summary = result.get("summary")

    if not isinstance(summary, dict):
        raise ValueError("Objeto 'summary' ausente ou inválido.")

    if not isinstance(summary.get("metrics"), dict):
        raise ValueError("Métricas detalhadas do k6 ausentes.")

    required_fields = [
        "run_id",
        "timestamp",
        "experiment_type",
        "phase",
        "scenario_id",
        "repetition",
        "architecture",
        "delay_ms",
        "vus",
        "duration",
        "total_requests",
        "throughput",
        "latency_avg_ms",
        "latency_min_ms",
        "latency_med_ms",
        "latency_max_ms",
        "latency_p90_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "error_rate_percent",
        "check_success_percent",
        "check_failure_percent",
    ]

    # Confere a presença dos campos obrigatórios.
    missing_fields = [
        field for field in required_fields
        if field not in data or data[field] is None
    ]

    if missing_fields:
        raise ValueError(
            f"Campos ausentes ou nulos: {missing_fields}"
        )

    # Confere a identificação do resultado.
    if data["run_id"] != run_id:
        raise ValueError("run_id inconsistente.")

    if data["experiment_type"] != experiment_type:
        raise ValueError("Tipo de experimento inconsistente.")

    if data["phase"] != phase:
        raise ValueError("Fase experimental inconsistente.")

    # Confere a duração prevista para a fase experimental.
    expected_duration = (
        WARMUP_DURATION if phase == "warmup"
        else MEASUREMENT_DURATION
    )

    if data["duration"] != expected_duration:
        raise ValueError(
            f"Duração experimental inconsistente: "
            f"esperado={expected_duration}, "
            f"encontrado={data['duration']}"
        )

    # Confere os metadados também durante uma nova execução.
    if expected_run is not None:
        for field in METADATA_FIELDS:
            if type(data[field]) is not type(expected_run[field]) or data[field] != expected_run[field]:
                raise ValueError(f"Metadados inconsistentes em {phase}: {field}.")

    if type(data["total_requests"]) is not int or data["total_requests"] <= 0:
        raise ValueError("Quantidade de requisições inválida.")
    if type(data["throughput"]) not in (int, float) or not math.isfinite(data["throughput"]) or data["throughput"] <= 0:
        raise ValueError("Throughput inválido.")

    # Verifica a taxa original do k6, sem assumir que a fase durou exatamente 60s.
    request_metric = summary["metrics"].get("http_reqs")
    if not isinstance(request_metric, dict) or not isinstance(request_metric.get("values"), dict):
        raise ValueError("Métrica http_reqs ausente ou inválida no resumo do k6.")
    requests = request_metric["values"]
    count, rate = requests.get("count"), requests.get("rate")
    if type(count) not in (int, float) or not math.isfinite(count) or count != data["total_requests"]:
        raise ValueError("Contagem de requisições inconsistente com o resumo do k6.")
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0 or not math.isclose(rate, data["throughput"], rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("Throughput inconsistente com o resumo do k6.")

    latency_fields = [
        "latency_avg_ms",
        "latency_min_ms",
        "latency_med_ms",
        "latency_max_ms",
        "latency_p90_ms",
        "latency_p95_ms",
        "latency_p99_ms",
    ]

    for field in latency_fields:
        if type(data[field]) not in (int, float):
            raise ValueError(f"Métrica não numérica: {field}")

        if not math.isfinite(data[field]) or data[field] < 0:
            raise ValueError(f"Métrica inválida: {field}")

    if not (
            data["latency_min_ms"]
            <= data["latency_med_ms"]
            <= data["latency_max_ms"]
    ):
        raise ValueError("Ordem das latências inconsistente.")

    if not (
            data["latency_p90_ms"]
            <= data["latency_p95_ms"]
            <= data["latency_p99_ms"]
    ):
        raise ValueError("Ordem dos percentis inconsistente.")

    for field in (
            "error_rate_percent",
            "check_success_percent",
            "check_failure_percent",
    ):
        value = data[field]

        if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0 <= value <= 100
        ):
            raise ValueError(f"Percentual inválido: {field}")

    print(f"Metricas JSON da fase {phase}: OK")
    return data


# Compara os dados consolidados do CSV com os dados do JSON.
def validate_csv_consistency(run_id, experiment_type, phase, scenario=None):
    json_path, csv_path, _, _ = result_paths(run_id, experiment_type, phase)
    if scenario is None:
        with json_path.open("r", encoding="utf-8") as file:
            scenario = json.load(file)["scenario"]
    if not isinstance(scenario, dict):
        raise ValueError("Objeto 'scenario' inválido no JSON.")

    # Carrega a linha consolidada do CSV.
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames
        rows = list(reader)

    if len(rows) != 1:
        raise ValueError(
            f"CSV deve conter exatamente uma linha: {len(rows)}"
        )

    if columns is None or len(columns) != len(scenario) or set(columns) != set(scenario):
        raise ValueError("Colunas do CSV diferentes dos campos do JSON.")

    csv_row = rows[0]
    if None in csv_row or None in csv_row.values():
        raise ValueError("Linha do CSV incompleta ou com campos excedentes.")

    # Compara cada campo respeitando seu tipo.
    for field, json_value in scenario.items():
        csv_value = csv_row[field]

        if json_value is None:
            raise ValueError(f"Valor nulo no JSON: {field}")

        if isinstance(json_value, bool):
            matches = csv_value.lower() == str(json_value).lower()

        elif isinstance(json_value, int):
            try:
                matches = int(csv_value) == json_value
            except ValueError:
                matches = False

        elif isinstance(json_value, float):
            try:
                matches = math.isclose(
                    float(csv_value),
                    json_value,
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                )
            except ValueError:
                matches = False

        else:
            matches = csv_value == str(json_value)

        if not matches:
            raise ValueError(
                f"Divergência no campo '{field}': "
                f"JSON={json_value}, CSV={csv_value}"
            )

    print(f"Consistencia JSON/CSV da fase {phase}: OK")


# Valida as quantidades de amostras brutas do k6.
def validate_raw_metrics(run_id, experiment_type, phase, scenario=None):
    """Valida contagens, latências, percentis e erros em uma única leitura."""
    json_path, _, raw_path, _ = result_paths(run_id, experiment_type, phase)
    if scenario is None:
        with json_path.open("r", encoding="utf-8") as file:
            scenario = json.load(file)["scenario"]
    total_requests = scenario["total_requests"]
    counts = dict.fromkeys(("http_reqs", "http_req_duration", "iterations", "checks", "http_req_failed"), 0)
    latencies = []
    http_failed = checks_passed = 0

    with raw_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not {"metric_name", "metric_value"}.issubset(reader.fieldnames or []):
            raise ValueError("Colunas obrigatórias ausentes no CSV bruto.")
        for row in reader:
            metric = row["metric_name"]
            if metric not in counts:
                continue
            counts[metric] += 1
            try:
                value = float(row["metric_value"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Valor bruto inválido em {metric}.") from exc
            if not math.isfinite(value):
                raise ValueError(f"Valor bruto não finito em {metric}.")
            if metric == "http_req_duration":
                if value < 0:
                    raise ValueError("Latência bruta inválida.")
                latencies.append(value)
            elif metric in ("http_reqs", "iterations"):
                if value != 1:
                    raise ValueError(f"Valor inválido para {metric}: {value}")
            elif metric in ("http_req_failed", "checks"):
                if value not in (0.0, 1.0):
                    raise ValueError(f"Valor inválido para {metric}: {value}")
                if metric == "http_req_failed":
                    http_failed += int(value)
                else:
                    checks_passed += int(value)

    for metric, count in counts.items():
        expected = total_requests * 3 if metric == "checks" else total_requests
        if count != expected:
            raise ValueError(f"Inconsistência em {metric}: esperado={expected}, encontrado={count}")
    if not latencies:
        raise ValueError("Nenhuma latência registrada.")
    print(f"Amostras brutas da fase {phase}: OK")

    latencies.sort()
    for field, calculated in (
            ("latency_min_ms", latencies[0]),
            ("latency_max_ms", latencies[-1]),
            ("latency_avg_ms", math.fsum(latencies) / len(latencies)),
    ):
        expected = scenario[field]
        if not math.isclose(calculated, expected, rel_tol=1e-5, abs_tol=0.001):
            raise ValueError(f"{field} inconsistente: JSON={expected}, bruto={calculated}")
    print(f"Latências média, mínima e máxima da fase {phase}: OK")

    for percentile, field in ((50, "latency_med_ms"), (90, "latency_p90_ms"),
                              (95, "latency_p95_ms"), (99, "latency_p99_ms")):
        calculated = calculate_percentile(latencies, percentile)
        expected = scenario[field]
        if not math.isclose(calculated, expected, rel_tol=1e-5, abs_tol=0.01):
            raise ValueError(f"Percentil p{percentile} inconsistente: JSON={expected}, bruto={calculated}")
        print(f"{phase} p{percentile}: JSON={expected:.4f} ms | Bruto={calculated:.4f} ms | OK")

    if phase == "warmup" and (http_failed or checks_passed != counts["checks"]):
        raise ValueError("Aquecimento apresentou erros HTTP ou checks falhos nas amostras brutas.")
    error_rate = 100 * http_failed / total_requests
    check_success = 100 * checks_passed / counts["checks"]
    for field, calculated in (("error_rate_percent", error_rate),
                              ("check_success_percent", check_success),
                              ("check_failure_percent", 100 - check_success)):
        expected = scenario[field]
        if not math.isclose(calculated, expected, rel_tol=1e-6, abs_tol=0.001):
            raise ValueError(f"Inconsistência em {field}: JSON={expected}, bruto={calculated}")
    print(f"{phase}: erros={error_rate:.4f}% | checks OK={check_success:.4f}% | OK")


# Calcula um percentil por interpolação linear.
def calculate_percentile(sorted_values, percentile):
    if not sorted_values:
        raise ValueError("Não existem amostras para calcular o percentil.")

    position = (len(sorted_values) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return sorted_values[lower]

    fraction = position - lower

    return (
            sorted_values[lower] * (1 - fraction)
            + sorted_values[upper] * fraction
    )


# Valida os arquivos de monitoramento de recursos.
def validate_resource_metrics(run_id, experiment_type, phase, scenario=None):
    json_path, _, _, resource_path = result_paths(run_id, experiment_type, phase)
    if not resource_path.is_file():
        raise FileNotFoundError(f"Arquivo de recursos não encontrado: {resource_path}")
    if scenario is None:
        with json_path.open("r", encoding="utf-8") as file:
            scenario = json.load(file)["scenario"]
    architecture = scenario["architecture"]
    if architecture not in ("monolith", "microservices"):
        raise ValueError("Arquitetura inválida para o monitoramento.")

    services = (
        ["monolith"]
        if architecture == "monolith"
        else ["chat-service", "llm-service"]
    )

    expected_sources = {"host", *services}

    required_fields = {
        "timestamp_utc",
        "elapsed_seconds",
        "source",
        "container",
        "cpu_percent",
        "memory_percent",
        "memory_usage",
        "error",
    }

    samples = {}

    with resource_path.open(
            "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        if not required_fields.issubset(reader.fieldnames or []):
            raise ValueError("Cabeçalho de recursos inválido.")

        for row in reader:
            if None in row or None in row.values():
                raise ValueError("Registro de recursos incompleto.")

            if row["error"].strip():
                raise ValueError(
                    f"Erro de monitoramento: {row['error']}"
                )

            elapsed = float(row["elapsed_seconds"])
            cpu = float(row["cpu_percent"])
            memory = float(row["memory_percent"])

            if not all(
                    math.isfinite(value) and value >= 0
                    for value in (elapsed, cpu, memory)
            ):
                raise ValueError("Métricas de recursos inválidas.")

            timestamp = datetime.fromisoformat(row["timestamp_utc"])

            if (
                    timestamp.utcoffset() is None
                    or timestamp.utcoffset().total_seconds() != 0
            ):
                raise ValueError("Timestamp de recursos inválido.")

            if not row["memory_usage"].strip():
                raise ValueError("Consumo de memória ausente.")

            if row["source"] == "host":
                source = "host"

                if cpu > 100 or memory > 100:
                    raise ValueError("Percentual do host inválido.")

            elif row["source"] == "container":
                source = next(
                    (
                        service for service in services
                        if row["container"].endswith(f"-{service}-1")
                    ),
                    None,
                )

                if source is None:
                    raise ValueError("Container inesperado.")

            else:
                raise ValueError("Origem de monitoramento inválida.")

            sample = samples.setdefault(elapsed, set())

            if source in sample:
                raise ValueError("Amostra de recursos duplicada.")

            sample.add(source)

    # Verifica se todas as coletas possuem as origens esperadas.
    for elapsed, sources in samples.items():
        if sources != expected_sources:
            raise ValueError(
                f"Coleta incompleta em {elapsed}s."
            )

    # Exige as cinco amostras durante a geração de carga.
    # A coleta final aos 60 segundos é opcional.
    for expected_time in (10, 20, 30, 40, 50):
        matching_samples = [
            elapsed for elapsed in samples
            if abs(elapsed - expected_time) <= 2
        ]

        if len(matching_samples) != 1:
            raise ValueError(
                f"Amostra ausente ou duplicada em {expected_time}s."
            )

    print(
        f"Monitoramento da fase {phase}: "
        f"{len(samples)} coletas completas | OK"
    )


# Executa todas as validações dos resultados experimentais.
def validate_experimental_results(run_id, experiment_type, phases=PHASES, expected_run=None):
    print(f"\nValidando resultados: {run_id}")
    if not phases or any(phase not in PHASES for phase in phases):
        raise ValueError("Fases experimentais inválidas.")
    validate_run_files(run_id, experiment_type, phases=phases)
    for phase in phases:
        print(f"\nValidando fase: {phase}")
        scenario = validate_json_metrics(run_id, experiment_type, phase, expected_run)
        validate_csv_consistency(run_id, experiment_type, phase, scenario)
        validate_raw_metrics(run_id, experiment_type, phase, scenario)
        if experiment_type == "official":
            validate_resource_metrics(run_id, experiment_type, phase, scenario)
        if phase == "warmup" and (
                scenario["error_rate_percent"] != 0 or not math.isclose(
            scenario["check_success_percent"], 100.0, abs_tol=1e-9
        )
        ):
            raise ValueError("Aquecimento apresentou erros HTTP ou checks falhos.")
    print(f"\nTodas as validações passaram: {run_id} ({', '.join(phases)})")


# Identifica uma execução experimental pelo cenário e pela repetição.
def get_experiment_key(run):
    return f"{run['scenario_id']}_rep{run['repetition']}"


# Carrega o registro das execuções oficiais concluídas.
def load_completed_runs():
    checkpoint_file = results_directory("official") / "completed-runs.json"

    if not checkpoint_file.exists():
        return set()

    with checkpoint_file.open("r", encoding="utf-8") as file:
        completed = json.load(file)

    if not isinstance(completed, list):
        raise ValueError("Registro de execuções concluídas inválido.")

    if not all(isinstance(key, str) for key in completed):
        raise ValueError("Identificadores de execuções inválidos.")

    if len(completed) != len(set(completed)):
        raise ValueError("Registro contém identificadores duplicados.")

    return set(completed)


# Salva o registro das execuções oficiais concluídas.
def save_completed_runs(completed):
    checkpoint_file = results_directory("official") / "completed-runs.json"

    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

    temporary_file = checkpoint_file.with_suffix(".tmp")

    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(
            sorted(completed),
            file,
            indent=4,
            ensure_ascii=False
        )

    temporary_file.replace(checkpoint_file)


# Executa experimentos oficiais com confirmação e retomada.
def execute_official_experiments(runs, max_runs, confirmed):
    if not confirmed:
        raise RuntimeError(
            "Execução oficial não confirmada. "
            "Utilize --confirm-official."
        )

    if not 1 <= max_runs <= len(runs):
        raise ValueError(
            f"max_runs deve estar entre 1 e {len(runs)}."
        )

    validate_official_directory(runs)
    completed = load_completed_runs()

    # Verifica se o checkpoint contém apenas execuções planejadas.
    valid_keys = {
        get_experiment_key(run)
        for run in runs
    }

    unknown_keys = completed - valid_keys

    if unknown_keys:
        raise ValueError(
            "Checkpoint contém execuções desconhecidas: "
            + ", ".join(sorted(unknown_keys))
        )

    # Reconcilia resultados existentes antes de selecionar novas execuções.
    # Nenhum arquivo é excluído ou sobrescrito automaticamente.
    recovered = set()
    for run in runs:
        key = get_experiment_key(run)
        existing_files = find_official_run_artifacts(run)

        if key in completed:
            validate_official_result_files(run)
        elif existing_files:
            try:
                validate_official_result_files(run)
            except (ValueError, FileNotFoundError, KeyError, TypeError, OSError) as exc:
                paths = "\n".join(f"  - {path}" for path in existing_files)
                raise RuntimeError(
                    f"Execução oficial {key} possui resultados parciais ou inválidos. "
                    "Nenhum arquivo foi alterado. Verifique os arquivos antes "
                    f"de retomar:\n{paths}"
                ) from exc
            recovered.add(key)
            print(f"Resultado completo recuperado: {key}")

    # Persiste somente após verificar todos os cenários; evita recuperação parcial.
    if recovered:
        completed.update(recovered)
        save_completed_runs(completed)
        print(f"Checkpoint reconciliado: {len(recovered)} execução(ões) recuperada(s).")

    # Mantém a ordem experimental e ignora execuções concluídas.
    pending_runs = [
        run for run in runs
        if get_experiment_key(run) not in completed
    ]

    selected_runs = pending_runs[:max_runs]

    print(f"Execuções já concluídas: {len(completed)}")
    print(f"Execuções pendentes: {len(pending_runs)}")
    print(f"Execuções selecionadas: {len(selected_runs)}")

    if selected_runs:
        check_tool_availability()

    for index, run in enumerate(selected_runs, start=1):
        key = get_experiment_key(run)

        print(
            f"\nExecução oficial {index}/{len(selected_runs)}: {key}"
        )

        # A função já valida os resultados antes de retornar.
        execute_experimental_run(run, "official")

        # Registra somente após a execução validada.
        completed.add(key)
        save_completed_runs(completed)

        print(f"Checkpoint atualizado: {key}")


# Localiza qualquer artefato de uma execução, inclusive CSVs sem JSON.
def find_official_run_artifacts(run):
    prefix = experiment_prefix(run)
    return sorted(
        path for phase in PHASES
        for path in results_directory("official", phase).glob(f"{prefix}*")
        if path.is_file()
    )


def validate_official_directory(runs):
    """Rejeita arquivos não associados a nenhuma configuração planejada."""
    prefixes = tuple(experiment_prefix(run) for run in runs)
    unexpected = []
    for phase in PHASES:
        directory = results_directory("official", phase)
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if path.name == ".gitkeep" and path.is_file():
                continue
            if not path.is_file() or not path.name.startswith(prefixes):
                unexpected.append(path)
    if unexpected:
        paths = "\n".join(f"  - {path}" for path in sorted(unexpected))
        raise ValueError(f"Artefatos oficiais não previstos no planejamento:\n{paths}")


# Localiza os resultados JSON de uma execução oficial.
def find_official_result_files(run):
    files = find_official_run_artifacts(run)
    return {
        phase: [path for path in files if path.parent.name == phase and path.suffix == ".json"]
        for phase in PHASES
    }


def validate_official_artifact_set(run, run_id):
    expected = {path for phase in PHASES for path in result_paths(run_id, "official", phase)}
    found = set(find_official_run_artifacts(run))
    if found != expected:
        raise ValueError(
            f"Execução {get_experiment_key(run)}: arquivos ausentes ou excedentes. "
            f"Ausentes: {sorted(str(p) for p in expected - found)}; "
            f"Excedentes: {sorted(str(p) for p in found - expected)}."
        )


# Verifica se uma execução oficial possui os resultados das duas fases.
def validate_official_result_files(run):
    files = find_official_result_files(run)
    for phase in PHASES:
        if len(files[phase]) != 1:
            raise ValueError(
                f"Execução {get_experiment_key(run)}: esperado exatamente 1 JSON em {phase}, "
                f"encontrados {len(files[phase])}."
            )
    run_id = files["measurement"][0].stem
    if files["warmup"][0].stem != run_id:
        raise ValueError(f"Execução {get_experiment_key(run)}: identificadores das fases diferentes.")
    validate_official_artifact_set(run, run_id)
    validate_experimental_results(run_id, "official", expected_run=run)


@contextmanager
def exclusive_experiment_lock():
    """Impede execuções simultâneas do runner no mesmo diretório do projeto."""
    lock_dir = PROJECT_ROOT / "performance-tests" / "results" / ".experiment-runner.lock"
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_dir.mkdir()
    except FileExistsError as exc:
        raise RuntimeError(
            f"Outra execução pode estar ativa. Lock encontrado: {lock_dir}. "
            "Se uma execução anterior terminou abruptamente, confirme que "
            "nenhum runner está ativo antes de remover essa pasta."
        ) from exc
    try:
        yield
    finally:
        lock_dir.rmdir()


if __name__ == "__main__":
    args = parse_arguments()

    # Gera e valida o planejamento experimental.
    scenarios = create_experimental_scenarios()
    runs = create_experimental_runs(scenarios)
    randomized_runs = randomize_experimental_runs(runs)

    validate_experimental_plan(randomized_runs)

    print("Planejamento experimental validado!")
    print(f"Modo selecionado: {args.mode}")
    print(f"Total de cenários: {len(scenarios)}")
    print(f"Total de execuções planejadas: {len(randomized_runs)}")

    if args.mode == "plan-only":
        # Exporta o planejamento sem executar experimentos.
        output_file = export_experimental_plan(
            randomized_runs,
            "preliminary"
        )

        print(f"Planejamento exportado: {output_file}")

    elif args.mode == "preliminary":
        with exclusive_experiment_lock():
            execute_preliminary_experiments(randomized_runs, args.max_runs)

    elif args.mode == "official":
        if not args.confirm_official:
            raise RuntimeError("Execução oficial não confirmada. Utilize --confirm-official.")
        with exclusive_experiment_lock():
            execute_official_experiments(
                runs=randomized_runs,
                max_runs=args.max_runs,
                confirmed=args.confirm_official
            )
