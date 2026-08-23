# SPDX-License-Identifier: GPL-3.0-or-later
"""Login sessions (loginctl / who)."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any


class SessionError(Exception):
    """Raised when session listing fails."""


def _run(cmd: list[str], *, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)


def list_sessions() -> list[dict[str, Any]]:
    if shutil.which("loginctl") is None:
        return _who_fallback()
    try:
        completed = _run(
            ["loginctl", "list-sessions", "--no-legend", "--no-pager"],
            timeout=25.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SessionError(str(exc)) from exc
    if completed.returncode != 0:
        return _who_fallback()
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        rows.append(
            {
                "session": parts[0],
                "uid": parts[1],
                "user": parts[2],
                "seat": parts[3],
                "state": parts[4],
            }
        )
    return rows


def _who_fallback() -> list[dict[str, Any]]:
    if shutil.which("who") is None:
        return []
    try:
        completed = _run(["who"], timeout=10.0)
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        rows.append(
            {
                "session": parts[1].strip("()"),
                "uid": "",
                "user": parts[0],
                "seat": parts[2],
                "state": " ".join(parts[3:]),
            }
        )
    return rows
