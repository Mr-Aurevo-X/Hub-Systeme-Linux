# SPDX-License-Identifier: GPL-3.0-or-later
"""Spawn host scripts from updates_dir() and stream output (no shell=True)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from core import host, updater


class JobError(Exception):
    """Raised when a host job cannot start."""


def validate_script(script: Path) -> Path:
    """Allow only ``*.sh`` files written under ``updater.updates_dir()``."""
    resolved = script.expanduser().resolve()
    root = updater.updates_dir().resolve()
    if resolved.parent != root:
        raise JobError("Script hors du dossier updates")
    if resolved.suffix != ".sh" or not resolved.name.endswith(".sh"):
        raise JobError("Script invalide")
    if not resolved.is_file():
        raise JobError("Script introuvable")
    return resolved


def script_argv(script: Path, *, have_script_cmd: bool | None = None) -> list[str]:
    """Argv for the host: util-linux ``script`` PTY when available, else bash."""
    path = validate_script(script)
    if have_script_cmd is None:
        have_script_cmd = host.which("script") is not None
    if have_script_cmd:
        quoted = updater._shell_quote(str(path))
        return ["script", "-qefc", f"bash {quoted}", "/dev/null"]
    return ["bash", str(path)]


def spawn(script: Path) -> subprocess.Popen[str]:
    """Start the script on the host; caller reads ``stdout`` (merged stderr)."""
    argv = script_argv(script)
    try:
        proc = host.popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
            cwd=str(host.host_cwd()),
        )
    except OSError as exc:
        raise JobError(f"Impossible de lancer le script: {exc}") from exc
    return proc
