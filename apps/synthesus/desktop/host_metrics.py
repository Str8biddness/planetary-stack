"""Real host metrics, read from the kernel.

No psutil dependency and no invented numbers: CPU comes from `/proc/stat`,
memory from `/proc/meminfo`, storage from `statvfs` on the user's home. If a
value cannot be read it is reported as `None` and the UI shows it as unknown —
a dashboard that guesses is worse than one that admits a gap.

CPU utilisation is a rate, so it needs two samples. The first call establishes a
baseline and returns `None` for CPU rather than reporting a since-boot average
dressed up as a current reading.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

_PROC_STAT = "/proc/stat"
_PROC_MEMINFO = "/proc/meminfo"

_lock = threading.Lock()
_previous: tuple[int, int] | None = None  # (idle_all, total)


def _read_cpu_sample() -> tuple[int, int] | None:
    try:
        with open(_PROC_STAT, "r", encoding="ascii") as handle:
            line = handle.readline()
    except OSError:
        return None
    if not line.startswith("cpu "):
        return None
    try:
        values = [int(value) for value in line.split()[1:]]
    except ValueError:
        return None
    if len(values) < 5:
        return None
    # user nice system idle iowait irq softirq steal ...
    idle_all = values[3] + values[4]
    return idle_all, sum(values)


def cpu_percent() -> float | None:
    """Percent busy since the previous call, or None on the first call."""
    global _previous
    sample = _read_cpu_sample()
    if sample is None:
        return None
    with _lock:
        previous = _previous
        _previous = sample
    if previous is None:
        return None
    idle_delta = sample[0] - previous[0]
    total_delta = sample[1] - previous[1]
    if total_delta <= 0:
        return None
    busy = (1.0 - (idle_delta / total_delta)) * 100.0
    return round(max(0.0, min(100.0, busy)), 1)


def memory() -> dict[str, Any]:
    try:
        fields: dict[str, int] = {}
        with open(_PROC_MEMINFO, "r", encoding="ascii") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    fields[key] = int(rest.split()[0]) * 1024
                if len(fields) == 2:
                    break
    except (OSError, ValueError, IndexError):
        return {"total_bytes": None, "used_bytes": None, "percent": None}
    total = fields.get("MemTotal")
    available = fields.get("MemAvailable")
    if not total or available is None:
        return {"total_bytes": None, "used_bytes": None, "percent": None}
    used = total - available
    return {
        "total_bytes": total,
        "used_bytes": used,
        "percent": round(used / total * 100.0, 1),
    }


def storage(path: str | None = None) -> dict[str, Any]:
    target = path or os.path.expanduser("~")
    try:
        stats = os.statvfs(target)
    except OSError:
        return {"total_bytes": None, "used_bytes": None, "percent": None}
    total = stats.f_frsize * stats.f_blocks
    free = stats.f_frsize * stats.f_bavail
    if total <= 0:
        return {"total_bytes": None, "used_bytes": None, "percent": None}
    used = total - free
    return {
        "total_bytes": total,
        "used_bytes": used,
        "percent": round(used / total * 100.0, 1),
    }


def snapshot() -> dict[str, Any]:
    """One reading of everything this module can measure honestly."""
    return {
        "schema": "planetary.synthesus.host_metrics.v1",
        "observed_at": int(time.time()),
        "cpu_percent": cpu_percent(),
        "memory": memory(),
        "storage": storage(),
    }
