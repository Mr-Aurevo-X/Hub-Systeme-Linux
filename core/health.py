# SPDX-License-Identifier: GPL-3.0-or-later
"""Dashboard health score from already-collected metrics (no extra pkexec)."""

from __future__ import annotations

from typing import Any

from core import settings as app_settings

_GRADES = (
    (90, "A"),
    (75, "B"),
    (50, "C"),
    (0, "D"),
)


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _root_disk_percent(metrics: dict[str, Any]) -> float | None:
    disks = metrics.get("disks") or {}
    for part in disks.get("partitions") or []:
        if part.get("mountpoint") == "/":
            return _f(part.get("percent"))
    parts = disks.get("partitions") or []
    if not parts:
        return None
    return _f(parts[0].get("percent"))


def _cpu_temp_c(metrics: dict[str, Any]) -> float | None:
    temps = ((metrics.get("cpu") or {}).get("temperatures_c")) or []
    if not temps:
        return None
    try:
        return float(temps[0].get("current"))
    except (TypeError, ValueError, IndexError):
        return None


def _item(
    key: str,
    *,
    page: str,
    ok: bool,
    label: str,
    penalty: int,
) -> dict[str, Any]:
    return {
        "key": key,
        "page": page,
        "ok": ok,
        "label": label,
        "penalty": 0 if ok else penalty,
    }


def evaluate(
    metrics: dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return score 0–100, grade A–D, items and failing recommendations."""
    data = metrics or {}
    cfg = settings if isinstance(settings, dict) else app_settings.DEFAULTS
    th = cfg.get("thresholds") or app_settings.DEFAULTS["thresholds"]
    cpu_th = _f(th.get("cpu_percent", 90))
    ram_th = _f(th.get("ram_percent", 90))
    disk_th = _f(th.get("disk_percent", 90))
    temp_th = _f(th.get("temp_celsius", 85))

    cpu = _f((data.get("cpu") or {}).get("percent_total"))
    ram = _f((data.get("ram") or {}).get("percent"))
    disk = _root_disk_percent(data)
    temp = _cpu_temp_c(data)
    swap = _f((data.get("ram") or {}).get("swap_percent"))
    cores = int((data.get("cpu") or {}).get("logical_cores") or 0)
    load = (data.get("system") or {}).get("loadavg") or []
    load1 = _f(load[0]) if load else 0.0
    batt = (data.get("system") or {}).get("battery") or None

    items: list[dict[str, Any]] = [
        _item(
            "cpu",
            page="processes",
            ok=cpu < cpu_th,
            label=f"CPU {cpu:.0f}%",
            penalty=25,
        ),
        _item(
            "ram",
            page="processes",
            ok=ram < ram_th,
            label=f"RAM {ram:.0f}%",
            penalty=25,
        ),
        _item(
            "disk",
            page="cleaner",
            ok=disk is None or disk < disk_th,
            label="Disque N/A" if disk is None else f"Disque {disk:.0f}%",
            penalty=20,
        ),
        _item(
            "temp",
            page="dashboard",
            ok=temp is None or temp < temp_th,
            label="Temp. N/A" if temp is None else f"Temp. {temp:.0f} °C",
            penalty=20,
        ),
        _item(
            "swap",
            page="processes",
            ok=swap < 50.0,
            label=f"Swap {swap:.0f}%",
            penalty=10,
        ),
    ]
    load_ok = cores <= 0 or load1 <= (2.0 * cores)
    items.append(
        _item(
            "load",
            page="processes",
            ok=load_ok,
            label=f"Load {load1:.2f}",
            penalty=10,
        )
    )
    if isinstance(batt, dict):
        pct = _f(batt.get("percent"))
        plugged = bool(batt.get("plugged"))
        items.append(
            _item(
                "battery",
                page="dashboard",
                ok=plugged or pct >= 15.0,
                label=f"Batterie {pct:.0f}%",
                penalty=5,
            )
        )

    score = 100
    for item in items:
        score -= int(item["penalty"])
    score = max(0, min(100, score))
    grade = "D"
    for floor, letter in _GRADES:
        if score >= floor:
            grade = letter
            break
    recs = [item for item in items if not item["ok"]]
    return {
        "score": score,
        "grade": grade,
        "items": items,
        "recommendations": recs,
    }
