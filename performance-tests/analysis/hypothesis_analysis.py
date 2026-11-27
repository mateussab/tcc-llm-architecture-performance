"""Contrastes exploratorios H1-H3 para os cinco blocos oficiais completos."""
import csv
import math
from itertools import product
from statistics import mean, stdev

DELAYS = (100, 500, 2000)
VUS = (1, 10, 50, 100)
REPS = (1, 2, 3, 4, 5)
ARCH = ("monolith", "microservices")
T95 = 2.7764451051977987


def calculate_hypotheses(records):
    data = {}
    for row in records:
        key = (row["architecture"], int(row["delay_ms"]),
               int(row["vus"]), int(row["repetition"]))
        value = float(row["latency_avg_ms"])
        if key in data or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Latencia ou chave invalida: {key}")
        data[key] = value

    if set(data) != set(product(ARCH, DELAYS, VUS, REPS)):
        raise ValueError("Esperados 120 registros e cinco blocos completos")

    def effect(delay, vus, rep, relative):
        mono = data[("monolith", delay, vus, rep)]
        micro = data[("microservices", delay, vus, rep)]
        delta = micro - mono
        return 100 * delta / mono if relative else delta

    summaries, pairs = [], []

    def contrast(hypothesis, measure, reference, target):
        relative = measure == "relative"
        # H1: efeito micro - mono na condicao alvo.
        # H2/H3: efeito alvo - efeito referencia, dentro do bloco.
        metadata = {
            "hypothesis": hypothesis,
            "measure": measure,
            "unit": ("percent" if hypothesis == "H1" else "pp")
                    if relative else "ms",
            "reference_delay_ms": reference[0] if reference else "",
            "reference_vus": reference[1] if reference else "",
            "target_delay_ms": target[0],
            "target_vus": target[1],
        }
        values = []
        for rep in REPS:
            base = effect(*reference, rep, relative) if reference else None
            end = effect(*target, rep, relative)
            delta = end - base if base is not None else end
            values.append(delta)
            pairs.append({**metadata, "repetition": rep,
                          "reference_effect": base, "target_effect": end,
                          "contrast": delta})

        avg, sd = mean(values), stdev(values)
        half = T95 * sd / math.sqrt(len(values))
        summaries.append({
            **metadata, "n_blocks": len(values),
            "blocks": ";".join(map(str, REPS)),
            "mean_contrast": avg, "std": sd,
            "ci95_lower": avg - half, "ci95_upper": avg + half,
        })

    for delay, vus in product(DELAYS, VUS):
        contrast("H1", "absolute", None, (delay, vus))
        contrast("H1", "relative", None, (delay, vus))

    for vus in VUS:
        for low, high in ((100, 500), (500, 2000), (100, 2000)):
            contrast("H2", "relative", (low, vus), (high, vus))

    for delay in DELAYS:
        for vus in VUS[1:]:
            for measure in ("absolute", "relative"):
                contrast("H3", measure, (delay, 1), (delay, vus))

    return summaries, pairs


def export_hypothesis_analysis(records, output_dir):
    summaries, pairs = calculate_hypotheses(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("hypothesis-contrasts.csv", summaries),
                       ("hypothesis-block-values.csv", pairs)):
        destination = output_dir / name
        with destination.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    print(f"Contrastes H1-H3: {len(summaries)}")
    print(f"Valores por bloco: {len(pairs)}")
    print("Analise de hipoteses: OK")
    return summaries
