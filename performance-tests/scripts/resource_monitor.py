import csv
import json
import math
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psutil


DOCKER_STATS_TIMEOUT_SECONDS = 8


def collect_container_stats(container_ids):
    """Coleta as métricas dos containers selecionados."""

    result = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--no-trunc",
            "--format",
            "{{json .}}",
            *container_ids,
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=DOCKER_STATS_TIMEOUT_SECONDS,
        check=True,
    )

    stats = [
        json.loads(line)
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    if len(stats) != len(container_ids):
        raise RuntimeError("Quantidade de containers monitorados inconsistente.")

    return stats


@contextmanager
def monitor_resources(output_file, container_ids, interval_seconds=10):
    """Monitora os recursos durante uma fase experimental."""

    output_file = Path(output_file)
    container_ids = tuple(container_ids)

    if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(interval_seconds)
            or interval_seconds <= 0
    ):
        raise ValueError("Intervalo de monitoramento inválido.")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    stop_event = threading.Event()
    fatal_errors = []

    fieldnames = [
        "timestamp_utc",
        "elapsed_seconds",
        "source",
        "container",
        "cpu_percent",
        "memory_percent",
        "memory_usage",
        "error",
    ]

    # Impede a sobrescrita de resultados existentes.
    with output_file.open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        file.flush()

        def collect():
            start_time = time.monotonic()

            try:
                # Inicializa a medição de CPU.
                psutil.cpu_percent(interval=None)

                start_time = time.monotonic()
                next_sample = start_time + interval_seconds

                while not stop_event.wait(
                        max(0, next_sample - time.monotonic())
                ):
                    base = {
                        "timestamp_utc": datetime.now(
                            timezone.utc
                        ).isoformat(timespec="milliseconds"),
                        "elapsed_seconds": round(
                            time.monotonic() - start_time, 3
                        ),
                    }

                    # Coleta os recursos do hospedeiro.
                    memory = psutil.virtual_memory()

                    writer.writerow({
                        **base,
                        "source": "host",
                        "cpu_percent": psutil.cpu_percent(interval=None),
                        "memory_percent": memory.percent,
                        "memory_usage": f"{memory.used} B",
                    })

                    # Coleta os recursos dos containers.
                    if container_ids:
                        try:
                            stats = collect_container_stats(container_ids)

                            container_rows = [
                                {
                                    **base,
                                    "source": "container",
                                    "container": container["Name"],
                                    "cpu_percent": float(
                                        container["CPUPerc"].rstrip("%")
                                    ),
                                    "memory_percent": float(
                                        container["MemPerc"].rstrip("%")
                                    ),
                                    "memory_usage": container["MemUsage"],
                                }
                                for container in stats
                            ]

                        except Exception as exc:
                            writer.writerow({
                                **base,
                                "source": "docker",
                                "error": f"{type(exc).__name__}: {exc}",
                            })

                            print(f"AVISO: falha no monitoramento Docker: {exc}")
                        else:
                            # Falhas de escrita são fatais, não falhas do Docker.
                            writer.writerows(container_rows)

                    file.flush()

                    next_sample += interval_seconds

                    # Evita coletas consecutivas em caso de atraso.
                    if next_sample <= time.monotonic():
                        next_sample = time.monotonic() + interval_seconds

            except Exception as exc:
                # Registra falhas fatais para sinalizá-las à thread principal.
                fatal_errors.append(exc)
                print(f"AVISO: monitoramento interrompido: {exc}")

                try:
                    writer.writerow({
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(
                            timespec="milliseconds"
                        ),
                        "elapsed_seconds": round(time.monotonic() - start_time, 3),
                        "source": "monitor",
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    file.flush()
                except Exception as write_error:
                    print(f"AVISO: falha ao registrar erro no CSV: {write_error}")

        monitor_thread = threading.Thread(
            target=collect,
            name="resource-monitor",
        )

        monitor_thread.start()

        original_error = None
        try:
            yield
        except BaseException as exc:
            original_error = exc
            raise
        finally:
            stop_event.set()
            monitor_thread.join()

            if fatal_errors:
                error = fatal_errors[0]
                message = f"Falha fatal no monitoramento: {type(error).__name__}: {error}"
                if original_error is not None:
                    # Preserva a exceção da execução principal (por exemplo, do k6).
                    original_error.add_note(message)
                else:
                    raise RuntimeError(message) from error
