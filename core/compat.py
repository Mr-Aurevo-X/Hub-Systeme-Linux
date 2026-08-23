# SPDX-License-Identifier: GPL-3.0-or-later
"""Startup compatibility checks for native and Flatpak launches."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from core import host

_HOST_CORE_COMMANDS = ("python3", "systemctl", "journalctl", "pkexec")
_HOST_OPTIONAL_COMMANDS = ("flatpak", "snap", "apt", "dnf", "pacman", "zypper", "apk", "timeshift", "ufw")


def _read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return data
    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def _host_shell_works() -> bool:
    try:
        completed = host.run(
            ["sh", "-c", "printf ok"],
            check=False,
            capture_output=True,
            text=True,
            timeout=6,
            cwd=host.host_cwd(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and (completed.stdout or "").strip() == "ok"


def _which_many(commands: tuple[str, ...]) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for command in commands:
        found[command] = host.which(command)
    return found


def collect_startup_compatibility() -> dict[str, Any]:
    """Return non-fatal compatibility findings used at startup."""
    flatpak = host.is_flatpak()
    os_release = _read_os_release()
    core_commands = _which_many(_HOST_CORE_COMMANDS)
    optional_commands = _which_many(_HOST_OPTIONAL_COMMANDS)
    warnings: list[str] = []

    if flatpak:
        if not _host_shell_works():
            warnings.append(
                "Pont hote Flatpak indisponible: les actions systeme seront limitees."
            )
        if core_commands.get("python3") is None:
            warnings.append(
                "Python 3 hote introuvable: monitoring et processus peuvent etre limites."
            )
        if core_commands.get("pkexec") is None:
            warnings.append(
                "pkexec introuvable sur l'hote: les actions administrateur seront limitees."
            )
        missing_service_tools = [
            name for name in ("systemctl", "journalctl") if core_commands.get(name) is None
        ]
        if missing_service_tools:
            warnings.append(
                "Outils systeme absents sur l'hote: " + ", ".join(missing_service_tools)
            )

    return {
        "flatpak": flatpak,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP") or "",
            "session": os.environ.get("XDG_SESSION_TYPE") or "",
            "os_id": os_release.get("ID", ""),
            "os_name": os_release.get("PRETTY_NAME") or os_release.get("NAME") or "",
        },
        "host_commands": {**core_commands, **optional_commands},
        "warnings": warnings,
    }
