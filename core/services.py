# SPDX-License-Identifier: GPL-3.0-or-later
"""systemd service listing and control via pkexec systemctl."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

UNIT_NAME_RE = re.compile(r"^[A-Za-z0-9@_.\\-]+$")
ALLOWED_ACTIONS = frozenset({"start", "stop", "restart", "enable", "disable", "status"})


class ServiceError(Exception):
    """Raised when a systemd operation fails."""


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
    if cleaned.endswith(".service"):
        base = cleaned[: -len(".service")]
    else:
        base = cleaned
    if not base or not UNIT_NAME_RE.match(base):
        raise ServiceError(f"Nom d'unité invalide: {name}")
    return f"{base}.service"


def _parse_unit_files() -> dict[str, str]:
    """Map unit name -> enablement state (enabled/disabled/static/...)."""
    if shutil.which("systemctl") is None:
        return {}
    try:
        completed = _run(
            ["systemctl", "list-unit-files", "--type=service", "--no-pager", "--no-legend"],
            timeout=45.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}

    states: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        unit, state = parts[0], parts[1]
        states[unit] = state
    return states


def list_services() -> list[dict[str, Any]]:
    """Return systemd services with active/inactive and enabled/disabled state."""
    if shutil.which("systemctl") is None:
        return []

    enablement = _parse_unit_files()
    try:
        completed = _run(
            [
                "systemctl",
                "list-units",
                "--type=service",
                "--all",
                "--no-pager",
                "--no-legend",
            ],
            timeout=45.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ServiceError(f"Impossible de lister les services: {exc}") from exc

    services: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in completed.stdout.splitlines():
        # Columns: UNIT LOAD ACTIVE SUB DESCRIPTION...
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        unit, load, active, sub = parts[0], parts[1], parts[2], parts[3]
        description = parts[4] if len(parts) > 4 else ""
        if not unit.endswith(".service"):
            continue
        seen.add(unit)
        services.append(
            {
                "name": unit,
                "short_name": unit.removesuffix(".service"),
                "load": load,
                "active": active,
                "sub": sub,
                "description": description,
                "enabled": enablement.get(unit, "unknown"),
                "is_active": active == "active",
                "is_enabled": enablement.get(unit) == "enabled",
            }
        )

    # Include unit-files not currently loaded.
    for unit, state in enablement.items():
        if unit in seen or not unit.endswith(".service"):
            continue
        services.append(
            {
                "name": unit,
                "short_name": unit.removesuffix(".service"),
                "load": "not-found",
                "active": "inactive",
                "sub": "dead",
                "description": "",
                "enabled": state,
                "is_active": False,
                "is_enabled": state == "enabled",
            }
        )

    services.sort(key=lambda item: item["name"].lower())
    return services


def toggle_service(name: str, action: str) -> dict[str, Any]:
    """Run ``pkexec systemctl <action> <unit>`` for an allowed action."""
    from core import executil

    action_clean = action.strip().lower()
    if action_clean not in ALLOWED_ACTIONS:
        raise ServiceError(f"Action non autorisée: {action}")

    unit = validate_unit_name(name)
    if shutil.which("systemctl") is None:
        raise ServiceError("systemctl introuvable")

    try:
        completed = executil.run_pkexec(["systemctl", action_clean, unit], timeout=120.0)
        out = executil.check_ok(completed, what=f"systemctl {action_clean}")
    except executil.ExecError as exc:
        raise ServiceError(str(exc)) from exc

    return {
        "ok": True,
        "unit": unit,
        "action": action_clean,
        "stdout": out,
    }
