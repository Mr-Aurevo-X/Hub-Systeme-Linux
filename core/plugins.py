# SPDX-License-Identifier: GPL-3.0-or-later
"""Simple user script plugins loader (local files only, no network)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Any

_ALLOWED_SUFFIXES = {".sh", ".py"}


class PluginError(Exception):
    """Raised when a plugin fails."""


def plugins_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    path = base / "hub-systeme" / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_plugin_path(name: str) -> Path:
    if not name or name.startswith(".") or "/" in name or "\\" in name or name in {".", ".."}:
        raise PluginError("Nom de plugin invalide")
    folder = plugins_dir().resolve()
    path = folder / name
    if path.is_symlink():
        raise PluginError("Les liens symboliques sont refusés")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PluginError(f"Plugin introuvable: {name}") from exc
    try:
        resolved.relative_to(folder)
    except ValueError as exc:
        raise PluginError("Plugin hors répertoire autorisé") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise PluginError(f"Plugin introuvable: {name}")
    if resolved.suffix not in _ALLOWED_SUFFIXES:
        raise PluginError("Seuls les scripts .sh et .py sont autorisés")
    try:
        st = resolved.stat()
    except OSError as exc:
        raise PluginError(str(exc)) from exc
    if st.st_uid != os.getuid():
        raise PluginError("Le script doit appartenir à l'utilisateur courant")
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise PluginError("Script accessible en écriture par d'autres utilisateurs")
    if st.st_mode & (stat.S_ISUID | stat.S_ISGID):
        raise PluginError("Script setuid/setgid refusé")
    return resolved


def list_plugins() -> list[dict[str, Any]]:
    folder = plugins_dir()
    items: list[dict[str, Any]] = []
    for path in sorted(folder.iterdir()):
        try:
            safe = _safe_plugin_path(path.name)
        except PluginError:
            continue
        items.append(
            {
                "name": safe.name,
                "path": str(safe),
                "executable": os.access(safe, os.X_OK),
            }
        )
    return items


def run_plugin(name: str, *, timeout: float = 120.0) -> dict[str, Any]:
    path = _safe_plugin_path(name)
    if path.suffix == ".py":
        cmd = ["python3", str(path)]
    else:
        cmd = ["bash", str(path)]
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(plugins_dir()),
        )
    except subprocess.TimeoutExpired as exc:
        raise PluginError("Délai dépassé") from exc
    except OSError as exc:
        raise PluginError(str(exc)) from exc
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def ensure_example_plugin() -> Path:
    path = plugins_dir() / "exemple-hello.sh"
    if not path.exists():
        path.write_text(
            "#!/usr/bin/env bash\necho \"Hello from Hub Système plugin\"\n",
            encoding="utf-8",
        )
        path.chmod(0o700)
    return path
