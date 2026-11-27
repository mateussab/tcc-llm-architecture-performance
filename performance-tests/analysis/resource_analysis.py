"""Analise descritiva de recursos, sem alterar os arquivos oficiais."""
import csv
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
from statistics import mean, median, stdev


OFFICIAL_DIR = Path(__file__).resolve().parents[1] / "results" / "official"
PHASES = ("warmup", "measurement")
TIMES = (10, 20, 30, 40, 50)
SERVICES = {
    "monolith": ("monolith",),
    "microservices": ("chat-service", "llm-service"),
}
LIMITS_MIB = {"monolith": 2048, "chat-service": 1024, "llm-service": 1024}
UNITS = {
    "B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3,
    "TiB": 1024**4, "kB": 1000, "KB": 1000,
    "MB": 1000**2, "GB": 1000**3, "TB": 1000**4,
}
FIELDS = {
    "timestamp_utc", "elapsed_seconds", "source", "container",
    "cpu_percent", "memory_percent", "memory_usage", "error",
}
METRICS = tuple(
    f"{metric}_{stat}"
    for metric in ("cpu_percent", "memory_mib", "memory_percent")
    for stat in ("mean", "max")
)


def nonnegative(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Valor numerico invalido: {value}")
    return value


def memory_mib(value):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*", value)
    if not match or match[2] not in UNITS:
        raise ValueError(f"Formato de memoria desconhecido: {value!r}")
    return nonnegative(match[1]) * UNITS[match[2]] / 1024**2


def load_cycles(path, architecture):
    """Retorna os cinco ciclos completos, identificados pelo tempo nominal."""
    services = SERVICES[architecture]
    expected = {"host", *services}
    cycles = {}
    timestamps = {}

    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not FIELDS.issubset(reader.fieldnames or []):
            raise ValueError("Cabecalho de recursos invalido")

        for row in reader:
            if None in row or None in row.values() or row["error"].strip():
                raise ValueError("Registro incompleto ou erro do monitor")

            elapsed = nonnegative(row["elapsed_seconds"])
            stamp = datetime.fromisoformat(row["timestamp_utc"])
            if stamp.utcoffset() != timedelta(0):
                raise ValueError("Timestamp sem fuso UTC")
            if timestamps.setdefault(elapsed, stamp) != stamp:
                raise ValueError("Timestamps divergentes no mesmo ciclo")

            cpu = nonnegative(row["cpu_percent"])
            mem_pct = nonnegative(row["memory_percent"])

            if row["source"] == "host":
                source = "host"
                if row["container"].strip() or cpu > 100 or mem_pct > 100:
                    raise ValueError("Registro do host invalido")
                mem = memory_mib(row["memory_usage"])
            elif row["source"] == "container":
                matches = [
                    s for s in services
                    if row["container"].endswith(f"-{s}-1")
                ]
                if len(matches) != 1:
                    raise ValueError(f"Container inesperado: {row['container']}")
                source = matches[0]
                usage = row["memory_usage"].split("/")
                if len(usage) != 2:
                    raise ValueError("Uso/limite de memoria invalido")
                mem, limit = map(memory_mib, usage)
                if not math.isclose(limit, LIMITS_MIB[source], abs_tol=0.01):
                    raise ValueError(f"Limite de memoria divergente: {source}")
            else:
                raise ValueError(f"Origem inesperada: {row['source']}")

            cycle = cycles.setdefault(elapsed, {})
            if source in cycle:
                raise ValueError(f"Origem duplicada aos {elapsed}s: {source}")
            cycle[source] = (cpu, mem, mem_pct)

    for elapsed, cycle in cycles.items():
        if set(cycle) != expected:
            raise ValueError(f"Ciclo incompleto aos {elapsed}s")

    selected = []
    for nominal in TIMES:
        matches = [t for t in cycles if abs(t - nominal) <= 2]
        if len(matches) != 1:
            raise ValueError(f"Esperado um ciclo em {nominal} +/- 2s")
        elapsed = matches[0]
        cycle = dict(cycles[elapsed])
        # Somar os consumos no mesmo ciclo, nunca os maximos isolados.
        cpu = sum(cycle[s][0] for s in services)
        mem = sum(cycle[s][1] for s in services)
        limit = sum(LIMITS_MIB[s] for s in services)
        cycle["application"] = (cpu, mem, 100 * mem / limit)
        selected.append((nominal, elapsed, timestamps[elapsed], cycle))

    if any(a[2] >= b[2] for a, b in zip(selected, selected[1:])):
        raise ValueError("Timestamps dos ciclos fora de ordem")

    return selected


def summarize_run(record, phase, official_dir):
    run_id = record["run_id"]
    if Path(run_id).name != run_id or "/" in run_id or "\\" in run_id:
        raise ValueError("Run ID invalido")
    architecture = record["architecture"]
    path = official_dir / phase / f"{run_id}_resources.csv"

    try:
        cycles = load_cycles(path, architecture)
    except (ValueError, OSError, KeyError) as exc:
        raise ValueError(f"{path}: {exc}") from exc

    result = []
    for scope in ("host", *SERVICES[architecture], "application"):
        samples = [cycle[scope] for _, _, _, cycle in cycles]
        row = {
            "run_id": run_id,
            "scenario_id": record["scenario_id"],
            "architecture": architecture,
            "delay_ms": int(record["delay_ms"]),
            "vus": int(record["vus"]),
            "repetition": int(record["repetition"]),
            "phase": phase,
            "scope": scope,
            "n_samples": len(samples),
        }
        for index, metric in enumerate(("cpu_percent", "memory_mib", "memory_percent")):
            values = [s[index] for s in samples]
            row[f"{metric}_mean"] = mean(values)
            row[f"{metric}_max"] = max(values)
        result.append(row)
    return result


def summarize_scenarios(runs):
    groups = defaultdict(list)
    fields = ("scenario_id", "architecture", "delay_ms", "vus", "phase", "scope")
    for row in runs:
        groups[tuple(row[f] for f in fields)].append(row)

    result = []
    for key, rows in sorted(groups.items()):
        if len(rows) != 5 or {r["repetition"] for r in rows} != set(range(1, 6)):
            raise ValueError(f"Repeticoes incompletas: {key}")
        for metric in METRICS:
            values = [r[metric] for r in rows]
            avg, std = mean(values), stdev(values)
            result.append({
                **dict(zip(fields, key)),
                "metric": metric,
                "n": len(values),
                "mean": avg,
                "median": median(values),
                "std": std,
                "cv_percent": 100 * std / avg if avg > 0 and "memory_percent" not in metric
                              and "cpu_percent" not in metric else None,
                "min": min(values),
                "max": max(values),
            })
    return result


def compare_architectures(runs):
    """Comparacao descritiva por condicao; sem testes inferenciais."""
    groups = defaultdict(dict)
    fields = ("phase", "delay_ms", "vus", "scope")
    for row in runs:
        if row["scope"] not in ("host", "application"):
            continue
        key = tuple(row[f] for f in fields)
        pair_key = row["architecture"], row["repetition"]
        if pair_key in groups[key]:
            raise ValueError(f"Registro duplicado: {key}, {pair_key}")
        groups[key][pair_key] = row

    expected = set(product(SERVICES, range(1, 6)))
    if len(groups) != 48:
        raise ValueError("Esperados 48 grupos de comparacao de recursos")
    result = []
    for key, rows in sorted(groups.items()):
        if set(rows) != expected:
            raise ValueError(f"Pareamento incompleto: {key}")
        for metric in METRICS:
            mono = [rows["monolith", rep][metric] for rep in range(1, 6)]
            micro = [rows["microservices", rep][metric] for rep in range(1, 6)]
            differences = [b - a for a, b in zip(mono, micro)]
            avg_mono, avg_micro = mean(mono), mean(micro)
            result.append({
                **dict(zip(fields, key)),
                "metric": metric,
                "n_pairs": 5,
                "monolith_mean": avg_mono,
                "microservices_mean": avg_micro,
                "mean_difference": mean(differences),
                "difference_std": stdev(differences),
                "difference_unit": "MiB" if "memory_mib" in metric else "pp",
                "relative_difference_percent": (
                    100 * (avg_micro - avg_mono) / avg_mono if avg_mono > 0 else None
                ),
            })
    return result


def write_csv(rows, path):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export_resource_analysis(records, output_dir, official_dir=OFFICIAL_DIR):
    expected = set(product(SERVICES, (100, 500, 2000), (1, 10, 50, 100), range(1, 6)))
    actual = {
        (r["architecture"], int(r["delay_ms"]), int(r["vus"]), int(r["repetition"]))
        for r in records
    }
    if len(records) != 120 or actual != expected:
        raise ValueError("Plano experimental incompleto ou duplicado")
    if len({r["run_id"] for r in records}) != 120:
        raise ValueError("Run IDs duplicados")

    # Nao criar nem alterar arquivos oficiais.
    output_dir, official_dir = Path(output_dir), Path(official_dir)
    if output_dir.resolve().is_relative_to(official_dir.resolve()):
        raise ValueError("Saida da analise nao pode ficar no diretorio oficial")

    runs = [
        row
        for record in records
        for phase in PHASES
        for row in summarize_run(record, phase, official_dir)
    ]
    scenarios = summarize_scenarios(runs)
    comparisons = compare_architectures(runs)
    if (len(runs), len(scenarios), len(comparisons)) != (840, 1008, 288):
        raise ValueError("Quantidades de registros de recursos divergentes")

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(runs, output_dir / "resource-run-statistics.csv")
    write_csv(scenarios, output_dir / "resource-descriptive-statistics.csv")
    write_csv(comparisons, output_dir / "resource-comparative-statistics.csv")

    print("Arquivos de recursos analisados: 240 | OK")
    print("Ciclos nominais selecionados: 1200 | OK")
    print(f"Resumos por execucao, fase e origem: {len(runs)}")
    print(f"Registros descritivos de recursos: {len(scenarios)}")
    print(f"Comparacoes descritivas de recursos: {len(comparisons)}")
    print("Analise de recursos: OK")
    return runs, scenarios, comparisons
