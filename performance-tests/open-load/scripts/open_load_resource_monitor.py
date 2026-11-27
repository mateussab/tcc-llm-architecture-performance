"""Monitor exclusivo dos experimentos de carga aberta (Windows + Docker)."""
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

FIELDS = (
    'timestamp_utc', 'elapsed_seconds', 'source', 'container', 'pid',
    'cpu_percent', 'memory_percent', 'memory_usage', 'status', 'error',
)


def collect_container_stats(container_ids):
    result = subprocess.run(
        ['docker', 'stats', '--no-stream', '--no-trunc', '--format',
         '{{json .}}', *container_ids],
        capture_output=True, encoding='utf-8', errors='replace',
        timeout=8, check=True,
    )
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if sorted(row['ID'] for row in rows) != sorted(container_ids):
        raise RuntimeError('IDs dos containers monitorados inconsistentes.')
    return rows


@contextmanager
def monitor_open_load(output_file, container_ids, k6_pid, interval_seconds=10):
    """Recebe IDs completos do Docker e o PID do processo k6 (Popen.pid).

    CPU do host: percentual total. CPU de k6 e containers: 100% por CPU logica.
    Memoria do k6: RSS em bytes. Memoria Docker: texto original de docker stats.
    A primeira amostra ocorre apos um intervalo; o relogio inicia no monitor,
    nao no inicio exato do cenario k6. Status exited nao e falha de coleta.
    """
    if (isinstance(interval_seconds, bool) or
            not isinstance(interval_seconds, (int, float)) or
            not math.isfinite(interval_seconds) or interval_seconds <= 0):
        raise ValueError('Intervalo invalido.')
    if isinstance(k6_pid, bool) or not isinstance(k6_pid, int) or k6_pid <= 0:
        raise ValueError('PID invalido.')
    container_ids = tuple(container_ids)
    if len(set(container_ids)) != len(container_ids):
        raise ValueError('IDs de containers duplicados.')
    process = psutil.Process(k6_pid)
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    fatal_errors = []
    start = time.monotonic()

    with path.open('x', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        file.flush()

        def stamp():
            return {'timestamp_utc': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                    'elapsed_seconds': round(time.monotonic() - start, 3)}

        def row(source, status='ok', **kwargs):
            writer.writerow({**stamp(), 'source': source, 'status': status, **kwargs})

        def collect():
            try:
                psutil.cpu_percent(interval=None)
                process.cpu_percent(interval=None)
                deadline = time.monotonic() + interval_seconds
                while not stop.wait(max(0, deadline - time.monotonic())):
                    memory = psutil.virtual_memory()
                    row('host', cpu_percent=psutil.cpu_percent(interval=None),
                        memory_percent=memory.percent, memory_usage=f'{memory.used} B')
                    try:
                        if not process.is_running():
                            raise psutil.NoSuchProcess(k6_pid)
                        cpu = process.cpu_percent(interval=None)
                        rss = process.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.ZombieProcess):
                        row('k6', 'exited', pid=k6_pid)
                    except psutil.Error as exc:
                        row('k6', 'error', pid=k6_pid, error=f'{type(exc).__name__}: {exc}')
                    else:
                        row('k6', pid=k6_pid, cpu_percent=cpu,
                            memory_percent=100 * rss / memory.total,
                            memory_usage=f'{rss} B')
                    if container_ids:
                        try:
                            stats = collect_container_stats(container_ids)
                            values = [dict(container=item['Name'],
                                           cpu_percent=float(item['CPUPerc'].rstrip('%')),
                                           memory_percent=float(item['MemPerc'].rstrip('%')),
                                           memory_usage=item['MemUsage']) for item in stats]
                        except Exception as exc:
                            row('docker', 'error', error=f'{type(exc).__name__}: {exc}')
                        else:
                            for value in values:
                                row('container', **value)
                    file.flush()
                    deadline += interval_seconds
                    if deadline <= time.monotonic():
                        deadline = time.monotonic() + interval_seconds
            except Exception as exc:
                fatal_errors.append(exc)
                try:
                    row('monitor', 'error', error=f'{type(exc).__name__}: {exc}')
                    file.flush()
                except Exception:
                    pass

        thread = threading.Thread(target=collect, name='open-load-resource-monitor')
        thread.start()
        original_error = None
        try:
            yield
        except BaseException as exc:
            original_error = exc
            raise
        finally:
            stop.set()
            thread.join()
            if fatal_errors:
                message = f'Falha fatal do monitor: {fatal_errors[0]}'
                if original_error is not None:
                    original_error.add_note(message)
                else:
                    raise RuntimeError(message) from fatal_errors[0]
