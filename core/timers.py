# SPDX-License-Identifier: GPL-3.0-or-later
"""systemd timer listing and control via pkexec systemctl."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

UNIT_NAME_RE = re.compile(r"^[A-Za-z0-9@_.\\-]+$")
ALLOWED_ACTIONS = frozenset({"start", "stop", "enable", "disable"})


class TimerError(Exception):
    """Raised when a systemd timer operation fails."""


def _run(cmd: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def validate_unit_name(name: str) -> str:
    cleaned = name.strip()
    if cleaned.endswith(".timer"):
        base = cleaned[: -len(".timer")]
    else:
        base = cleaned
    if not base or not UNIT_NAME_RE.match(base):
        raise TimerError(f"Nom de timer invalide: {name}")
    return f"{base}.timer"


def parse_list_timers_output(text: str) -> list[dict[str, Any]]:
    """Parse ``systemctl list-timers --all`` legend output."""
    rows: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        raw = line.rstrip()
        if not raw.strip() or raw.startswith("NEXT"):
            continue
        timer_idx = raw.find(".timer")
        if timer_idx < 0:
            continue
        start = raw.rfind(" ", 0, timer_idx)
        unit = raw[start + 1 : timer_idx + len(".timer")].strip()
        if not unit.endswith(".timer"):
            continue
        prefix = raw[:start].strip()
        parts = prefix.split()
        if len(parts) < 5:
            continue
        rows.append(
            {
                "unit": unit,
                "next": f"{parts[0]} {parts[1]} {parts[2]}".strip(),
                "left": parts[3] if len(parts) > 3 else "",
                "last": f"{parts[4]} {parts[5]} {parts[6]}".strip() if len(parts) > 6 else "",
                "active": "active",
            }
        )
    return rows


def list_timers() -> list[dict[str, Any]]:
    if shutil.which("systemctl") is None:
        return []
    try:
        completed = _run(
            ["systemctl", "list-timers", "--all", "--no-pager", "--no-legend"],
            timeout=45.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TimerError(str(exc)) from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise TimerError(err or f"systemctl list-timers ({completed.returncode})")
    items = parse_list_timers_output(completed.stdout)
    enablement = _timer_enablement()
    for item in items:
        unit = str(item.get("unit") or "")
        item["enabled"] = enablement.get(unit, "unknown")
    return items


def _timer_enablement() -> dict[str, str]:
    if shutil.which("systemctl") is None:
        return {}
    try:
        completed = _run(
            ["systemctl", "list-unit-files", "--type=timer", "--no-pager", "--no-legend"],
            timeout=45.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    states: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            states[parts[0]] = parts[1]
    return states


def control_timer(unit: str, action: str, *, privileged: bool = True) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise TimerError(f"Action interdite: {action}")
    name = validate_unit_name(unit)
    cmd = ["systemctl", action, name]
    if privileged:
        cmd = ["pkexec"] + cmd
    try:
        completed = _run(cmd, timeout=60.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TimerError(str(exc)) from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise TimerError(err or f"systemctl {action} ({completed.returncode})")
    return {"unit": name, "action": action, "ok": True}
