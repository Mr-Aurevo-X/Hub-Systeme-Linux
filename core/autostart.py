# SPDX-License-Identifier: GPL-3.0-or-later
"""User autostart (.desktop) and systemd --user units."""

from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

UNIT_RE = re.compile(r"^[A-Za-z0-9@_.\\-]+$")


class AutostartError(Exception):
    """Raised when an autostart operation fails."""


def _autostart_dir() -> Path:
    path = Path.home() / ".config" / "autostart"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_desktop_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    folder = _autostart_dir()
    for path in sorted(folder.glob("*.desktop")):
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(path, encoding="utf-8")
            name = parser.get("Desktop Entry", "Name", fallback=path.stem)
            comment = parser.get("Desktop Entry", "Comment", fallback="")
            hidden = parser.getboolean("Desktop Entry", "Hidden", fallback=False)
            try:
                enabled = not parser.getboolean("Desktop Entry", "X-GNOME-Autostart-enabled", fallback=True) is False
                # If key exists and is false → disabled
                if parser.has_option("Desktop Entry", "X-GNOME-Autostart-enabled"):
                    enabled = parser.getboolean("Desktop Entry", "X-GNOME-Autostart-enabled")
                else:
                    enabled = not hidden
            except ValueError:
                enabled = not hidden
            entries.append(
                {
                    "kind": "desktop",
                    "id": path.name,
                    "path": str(path),
                    "name": name,
                    "description": comment,
                    "enabled": enabled and not hidden,
                }
            )
        except (OSError, configparser.Error):
            continue
    return entries


def set_desktop_enabled(filename: str, enabled: bool) -> None:
    if "/" in filename or ".." in filename or not filename.endswith(".desktop"):
        raise AutostartError("Nom de fichier invalide")
    path = _autostart_dir() / filename
    if not path.exists() or not path.is_file():
        raise AutostartError(f"Fichier introuvable: {filename}")
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[misc, assignment]
    parser.read(path, encoding="utf-8")
    if "Desktop Entry" not in parser:
        raise AutostartError("Fichier .desktop invalide")
    parser["Desktop Entry"]["X-GNOME-Autostart-enabled"] = "true" if enabled else "false"
    parser["Desktop Entry"]["Hidden"] = "false" if enabled else "true"
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle, space_around_delimiters=False)


def list_user_services() -> list[dict[str, Any]]:
    if shutil.which("systemctl") is None:
        return []
    try:
        completed = subprocess.run(
            ["systemctl", "--user", "list-unit-files", "--type=service", "--no-pager", "--no-legend"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].endswith(".service"):
            continue
        unit, state = parts[0], parts[1]
        rows.append(
            {
                "kind": "user_service",
                "id": unit,
                "name": unit.removesuffix(".service"),
                "description": state,
                "enabled": state == "enabled",
            }
        )
    return rows[:200]


def toggle_user_service(unit: str, enable: bool) -> None:
    base = unit.removesuffix(".service")
    if not UNIT_RE.match(base):
        raise AutostartError("Nom d'unité invalide")
    full = f"{base}.service"
    action = "enable" if enable else "disable"
    try:
        completed = subprocess.run(
            ["systemctl", "--user", action, "--now", full],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AutostartError(str(exc)) from exc
    if completed.returncode != 0:
        raise AutostartError((completed.stderr or completed.stdout or "échec").strip())


def list_all() -> list[dict[str, Any]]:
    return list_desktop_entries() + list_user_services()
