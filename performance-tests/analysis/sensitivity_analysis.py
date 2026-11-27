"""Analise de sensibilidade da suspensao, sem modificar a amostra principal."""
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

from hypothesis_analysis import calculate_hypotheses

POST_RESUME = {"E13", "E16", "E24", "E11", "E19", "E07"}
METRICS = ("latency_avg_ms", "latency_p95_ms", "latency_p99_ms",
           "throughput", "error_rate_percent", "app_cpu_percent_mean",
           "app_memory_mib_mean")
T95 = {4: 3.182446305284263, 5: 2.7764451051977987}
STRATEGIES = ("affected_pairs", "exclude_block5")


def stats(values):
    n = len(values)
    avg, sd = mean(values), stdev(values)
    margin = T95[n] * sd / math.sqrt(n)
    return avg, avg-margin, avg+margin


def sign_ci(lo, hi):
    return "positive" if lo > 0 else "negative" if hi < 0 else "includes_zero"


def compare(values, affected, strategy):
    reps = sorted(values)
    keep = [rep for rep in reps if not (
        rep == 5 and (affected or strategy == "exclude_block5"))]
    avg, lo, hi = stats([values[rep] for rep in reps])
    alt, altlo, althi = stats([values[rep] for rep in keep])
    return dict(strategy=strategy, affected=affected,
                n_full=len(reps), n_sensitivity=len(keep),
                blocks=";".join(map(str, keep)),
                full_mean=avg, full_ci95_lower=lo, full_ci95_upper=hi,
                sensitivity_mean=alt, sensitivity_ci95_lower=altlo,
                sensitivity_ci95_upper=althi,
                change=alt-avg,
                full_ci_direction=sign_ci(lo, hi),
                sensitivity_ci_direction=sign_ci(altlo, althi))


def write_csv(rows, path):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export_sensitivity_analysis(records, output_dir):
    output_dir = Path(output_dir)
    # Reutilizar os resumos de recursos previamente validados.
    with (output_dir / "resource-run-statistics.csv").open(
            encoding="utf-8-sig", newline="") as file:
        resource_rows = [row for row in csv.DictReader(file)
                         if row["phase"] == "measurement" and
                         row["scope"] == "application"]
    resources = {row["run_id"]: row for row in resource_rows}
    if len(resources) != 120 or len(resource_rows) != 120:
        raise ValueError("Resumos de recursos ausentes ou duplicados")
    if set(resources) != {row["run_id"] for row in records}:
        raise ValueError("Run IDs de recursos divergentes")

    data, scenario_data = {}, defaultdict(dict)
    affected_conditions = set()
    for row in records:
        delay, vus, rep = map(int, (row["delay_ms"], row["vus"], row["repetition"]))
        arch, scenario = row["architecture"], row["scenario_id"]
        key = (delay, vus, arch, rep)
        if key in data or rep in scenario_data[scenario]:
            raise ValueError("Medicao duplicada")
        resource = resources[row["run_id"]]
        for field in ("scenario_id", "architecture", "delay_ms", "vus", "repetition"):
            if str(row[field]) != str(resource[field]):
                raise ValueError("Metadados de recursos divergentes")
        if int(resource["n_samples"]) != 5:
            raise ValueError("Quantidade invalida de coletas")
        values = {metric: float(row[metric]) for metric in METRICS[:5]}
        values.update(app_cpu_percent_mean=float(resource["cpu_percent_mean"]),
                      app_memory_mib_mean=float(resource["memory_mib_mean"]))
        if any(not math.isfinite(v) or v < 0 for v in values.values()):
            raise ValueError("Metrica invalida")
        data[key] = values
        scenario_data[scenario][rep] = values
        if scenario in POST_RESUME and rep == 5:
            affected_conditions.add((delay, vus))

    if len(data) != 120 or len(scenario_data) != 24 or len(affected_conditions) != 5:
        raise ValueError("Plano experimental ou condicoes afetadas divergentes")
    if not POST_RESUME.issubset(scenario_data):
        raise ValueError("Cenario posterior a suspensao ausente")
    if any(set(rows) != set(range(1, 6)) for rows in scenario_data.values()):
        raise ValueError("Blocos incompletos")

    checks = []
    for scenario in sorted(POST_RESUME):
        for metric in METRICS:
            baseline = mean([scenario_data[scenario][rep][metric] for rep in range(1, 5)])
            post = scenario_data[scenario][5][metric]
            checks.append(dict(scenario_id=scenario, repetition=5, metric=metric,
                               prior_four_mean=baseline, post_resume=post,
                               difference=post-baseline,
                               relative_change_percent=100*(post-baseline)/baseline
                               if baseline > 0 else None))

    comparisons = []
    for delay in (100, 500, 2000):
        for vus in (1, 10, 50, 100):
            for metric in METRICS:
                values = {rep: data[delay, vus, "microservices", rep][metric] -
                               data[delay, vus, "monolith", rep][metric]
                          for rep in range(1, 6)}
                for strategy in STRATEGIES:
                    comparisons.append(dict(delay_ms=delay, vus=vus, metric=metric,
                        **compare(values, (delay, vus) in affected_conditions, strategy)))

    # Contrastes H1-H3: preservar exatamente as definicoes do modulo de hipoteses.
    _, block_values = calculate_hypotheses(records)
    fields = ("hypothesis", "measure", "unit", "reference_delay_ms",
              "reference_vus", "target_delay_ms", "target_vus")
    groups = defaultdict(dict)
    for row in block_values:
        key = tuple(row[field] for field in fields)
        rep = row["repetition"]
        if rep in groups[key]:
            raise ValueError("Contraste duplicado")
        groups[key][rep] = row["contrast"]
    hypotheses = []
    for key, values in groups.items():
        if set(values) != set(range(1, 6)):
            raise ValueError("Contraste com blocos incompletos")
        target = (key[5], key[6])
        reference = (key[3], key[4])
        affected = target in affected_conditions or reference in affected_conditions
        for strategy in STRATEGIES:
            hypotheses.append(dict(zip(fields, key), **compare(values, affected, strategy)))

    if (len(checks), len(comparisons), len(hypotheses)) != (42, 168, 108):
        raise ValueError("Quantidades de sensibilidade divergentes")
    for name, rows in (("sensitivity-post-resume.csv", checks),
                       ("sensitivity-comparisons.csv", comparisons),
                       ("sensitivity-hypotheses.csv", hypotheses)):
        write_csv(rows, output_dir / name)
    print("Execucoes apos suspensao: 6 | OK")
    print("Condicoes afetadas: 5 | OK")
    print(f"Verificacoes pos-suspensao: {len(checks)}")
    print(f"Comparacoes de sensibilidade: {len(comparisons)}")
    print(f"Contrastes de sensibilidade: {len(hypotheses)}")
    print("Analise de sensibilidade: OK")
    return checks, comparisons, hypotheses
