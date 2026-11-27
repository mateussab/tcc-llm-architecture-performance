import csv
import math
from collections import defaultdict
from statistics import mean, stdev


METRICS = (
    "latency_avg_ms",
    "latency_p95_ms",
    "latency_p99_ms",
    "throughput",
    "error_rate_percent",
)

T_CRITICAL_95 = 2.7764451051977987


def relative_difference(monolith, microservices, metric):
    if metric.endswith("_percent") or monolith == 0:
        return None

    return ((microservices - monolith) / monolith) * 100


def calculate_comparisons(records):
    groups = defaultdict(dict)

    for row in records:
        condition = (
            int(row["delay_ms"]),
            int(row["vus"]),
        )

        key = (
            row["architecture"],
            int(row["repetition"]),
        )

        if key in groups[condition]:
            raise ValueError(f"Medicao duplicada: {condition}, {key}")

        groups[condition][key] = row

    if len(groups) != 12:
        raise ValueError("Esperadas 12 condicoes experimentais")

    comparisons = []
    paired_results = []

    expected_keys = {
        (architecture, rep)
        for architecture in ("monolith", "microservices")
        for rep in range(1, 6)
    }

    for condition, rows in sorted(groups.items()):
        delay_ms, vus = condition

        if set(rows) != expected_keys:
            raise ValueError(f"Pareamento incompleto: {condition}")

        for metric in METRICS:
            monolith = []
            microservices = []
            differences = []

            for rep in range(1, 6):
                mono = float(rows[("monolith", rep)][metric])
                micro = float(rows[("microservices", rep)][metric])

                if not all(
                        math.isfinite(v) and v >= 0
                        for v in (mono, micro)
                ):
                    raise ValueError(f"Metrica invalida: {metric}")

                difference = micro - mono

                monolith.append(mono)
                microservices.append(micro)
                differences.append(difference)

                paired_results.append({
                    "delay_ms": delay_ms,
                    "vus": vus,
                    "metric": metric,
                    "repetition": rep,
                    "monolith": mono,
                    "microservices": micro,
                    "difference": difference,
                    "relative_difference_percent":
                        relative_difference(mono, micro, metric),
                })

            mono_mean = mean(monolith)
            micro_mean = mean(microservices)

            diff_mean = mean(differences)
            diff_std = stdev(differences)

            n = len(differences)

            margin = (
                    T_CRITICAL_95 * diff_std / math.sqrt(n)
            )

            comparisons.append({
                "delay_ms": delay_ms,
                "vus": vus,
                "metric": metric,
                "n_pairs": n,
                "monolith_mean": mono_mean,
                "microservices_mean": micro_mean,
                "mean_difference": diff_mean,
                "difference_std": diff_std,
                "relative_difference_percent":
                    relative_difference(
                        mono_mean, micro_mean, metric
                    ),
                "ci95_lower": diff_mean - margin,
                "ci95_upper": diff_mean + margin,
            })

    return comparisons, paired_results


def write_csv(records, destination):
    with destination.open(
            "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(records[0].keys()),
        )

        writer.writeheader()
        writer.writerows(records)


def export_comparative_statistics(records, output_dir):
    comparisons, paired_results = calculate_comparisons(records)

    output_dir.mkdir(parents=True, exist_ok=True)

    write_csv(
        comparisons,
        output_dir / "comparative-statistics.csv",
        )

    write_csv(
        paired_results,
        output_dir / "paired-differences.csv",
        )

    print("Condicoes comparadas: 12 | OK")
    print(f"Metricas comparadas: {len(METRICS)}")
    print(f"Comparacoes consolidadas: {len(comparisons)}")
    print(f"Diferencas pareadas: {len(paired_results)}")
    print("Intervalos de confianca de 95% calculados.")

    return comparisons
