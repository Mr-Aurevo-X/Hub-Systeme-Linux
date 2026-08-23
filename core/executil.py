# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared subprocess / pkexec helpers (argv-only, timeouts, logging)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Sequence

log = logging.getLogger("gest.executil")


class ExecError(Exception):
    """Raised when a command fails or cannot be started."""


def run(
    cmd: Sequence[str],
    *,
    timeout: float = 60.0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` as argv list (never through a shell)."""
    if not cmd:
        raise ExecError("Commande vide")
    try:
        completed = subprocess.run(
            list(cmd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExecError(f"Délai dépassé ({timeout:.0f}s): {' '.join(cmd[:4])}") from exc
    except OSError as exc:
        raise ExecError(f"Échec d'exécution: {exc}") from exc
    return completed


def require_cmd(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ExecError(f"{name} introuvable")
    return path


def require_pkexec() -> str:
    return require_cmd("pkexec")


def run_pkexec(
    args: Sequence[str],
    *,
    timeout: float = 120.0,
    env_prefix: Sequence[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``pkexec [env …] <args>`` without ``bash -c``."""
    require_pkexec()
    cmd: list[str] = ["pkexec"]
    if env_prefix:
        cmd.extend(env_prefix)
    cmd.extend(args)
    log.debug("pkexec argv: %s", cmd[1:6])
    return run(cmd, timeout=timeout)


def check_ok(
    completed: subprocess.CompletedProcess[str],
    *,
    what: str,
) -> str:
    """Return stdout on success; raise ExecError with stderr/stdout on failure."""
    if completed.returncode == 0:
        return (completed.stdout or "").strip()
    err = (completed.stderr or completed.stdout or "").strip()
    raise ExecError(err or f"{what} a échoué ({completed.returncode})")
