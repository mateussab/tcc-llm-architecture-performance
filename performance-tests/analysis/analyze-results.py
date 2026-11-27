import csv
import json
from collections import Counter
from pathlib import Path
from descriptive_statistics import export_descriptive_statistics
from comparative_statistics import export_comparative_statistics
from hypothesis_analysis import export_hypothesis_analysis
from resource_analysis import export_resource_analysis
from sensitivity_analysis import export_sensitivity_analysis

BASE_DIR = Path(__file__).resolve().parents[1]

OFFICIAL_DIR = BASE_DIR / "results" / "official"
MEASUREMENT_DIR = OFFICIAL_DIR / "measurement"
OUTPUT_DIR = BASE_DIR / "results" / "analysis" / "tables"


def load_measurements():
    records = []

    for path in sorted(MEASUREMENT_DIR.glob("E*.csv")):
        if path.name.endswith(("_raw.csv", "_resources.csv")):
            continue

        with path.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))

        if len(rows) != 1:
            raise ValueError(f"CSV invalido: {path.name}")

        row = rows[0]

        if row["experiment_type"] != "official":
            raise ValueError(f"Experimento nao oficial: {path.name}")

        if row["phase"] != "measurement":
            raise ValueError(f"Fase incorreta: {path.name}")

        if row["run_id"] != path.stem:
            raise ValueError(f"Run ID divergente: {path.name}")

        records.append(row)

    return sorted(
        records,
        key=lambda row: (
            row["scenario_id"],
            int(row["repetition"])
        )
    )


def validate_measurements(records):
    expected = {
        f"E{scenario:02d}_rep{rep}"
        for scenario in range(1, 25)
        for rep in range(1, 6)
    }

    keys = [
        f'{row["scenario_id"]}_rep{row["repetition"]}'
        for row in records
    ]

    checkpoint = json.loads(
        (OFFICIAL_DIR / "completed-runs.json")
        .read_text(encoding="utf-8")
    )

    if len(records) != 120:
        raise ValueError("Quantidade incorreta de medicoes")

    if len(set(keys)) != 120 or set(keys) != expected:
        raise ValueError("Medicoes ausentes ou duplicadas")

    if len(checkpoint) != 120 or set(checkpoint) != expected:
        raise ValueError("Checkpoint divergente")

    counts = Counter(row["scenario_id"] for row in records)

    if len(counts) != 24 or any(n != 5 for n in counts.values()):
        raise ValueError("Distribuicao experimental incorreta")

    print("Medicoes oficiais: 120 | OK")
    print("Cenarios: 24 | OK")
    print("Repeticoes por cenario: 5 | OK")
    print("Correspondencia com checkpoint: OK")


def export_measurements(records):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    destination = OUTPUT_DIR / "consolidated-measurements.csv"

    with destination.open(
            "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=list(records[0].keys())
        )

        writer.writeheader()
        writer.writerows(records)

    print(f"Arquivo consolidado: {destination}")

def main():
    records = load_measurements()
    validate_measurements(records)
    export_measurements(records)

    print("Consolidacao concluida com sucesso.")

    export_descriptive_statistics(records, OUTPUT_DIR)

    print("Analise descritiva concluida com sucesso.")

    export_comparative_statistics(records, OUTPUT_DIR)

    print("Analise comparativa concluida com sucesso.")

    export_hypothesis_analysis(records, OUTPUT_DIR)

    print("Analise das hipoteses concluida com sucesso.")

    export_resource_analysis(records, OUTPUT_DIR)

    print("Analise de recursos concluida com sucesso.")

    export_sensitivity_analysis(records, OUTPUT_DIR)

    print("Analise de sensibilidade concluida com sucesso.")

if __name__ == "__main__":
    main()
