import csv
import math
from collections import defaultdict
from itertools import product
from statistics import mean, median, stdev


METRICS = (
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
)


def calculate_statistics(values, metric):
    if len(values) != 5:
        raise ValueError("Esperadas cinco repeticoes")

    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError(f"Valores invalidos: {metric}")

    if metric.endswith("_percent") and any(v > 100 for v in values):
        raise ValueError(f"Percentual invalido: {metric}")

    avg = mean(values)
    std = stdev(values)

    cv = (
        (std / avg) * 100
        if avg > 0 and not metric.endswith("_percent")
        else None
    )

    return {
        "n": len(values),
        "mean": avg,
        "median": median(values),
        "std": std,
        "cv_percent": cv,
        "min": min(values),
        "max": max(values),
    }


def calculate_descriptive_statistics(records):
    groups = defaultdict(list)

    for row in records:
        key = (
            row["scenario_id"],
            row["architecture"],
            int(row["delay_ms"]),
            int(row["vus"]),
        )

        groups[key].append(row)

    expected_conditions = set(product(
        ("monolith", "microservices"),
        (100, 500, 2000),
        (1, 10, 50, 100),
    ))

    actual_conditions = {
        key[1:] for key in groups
    }

    if len(groups) != 24 or actual_conditions != expected_conditions:
        raise ValueError("Configuracoes experimentais divergentes")

    results = []

    for key, rows in sorted(groups.items()):
        scenario_id, architecture, delay_ms, vus = key

        repetitions = {int(row["repetition"]) for row in rows}

        if len(rows) != 5 or repetitions != {1, 2, 3, 4, 5}:
            raise ValueError(
                f"Repeticoes invalidas: {scenario_id}"
            )

        for metric in METRICS:
            values = [float(row[metric]) for row in rows]

            stats = calculate_statistics(values, metric)

            results.append({
                "scenario_id": scenario_id,
                "architecture": architecture,
                "delay_ms": delay_ms,
                "vus": vus,
                "metric": metric,
                **stats,
            })

    return results


def export_descriptive_statistics(records, output_dir):
    results = calculate_descriptive_statistics(records)

    output_dir.mkdir(parents=True, exist_ok=True)

    destination = output_dir / "descriptive-statistics.csv"

    with destination.open(
            "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(results[0].keys()),
        )

        writer.writeheader()
        writer.writerows(results)

    print("Estatistica descritiva: 24 cenarios | OK")
    print(f"Metricas analisadas: {len(METRICS)}")
    print(f"Registros estatisticos: {len(results)}")
    print(f"Arquivo gerado: {destination}")

    return results
