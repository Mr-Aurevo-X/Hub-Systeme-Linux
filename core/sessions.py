# SPDX-License-Identifier: GPL-3.0-or-later
"""Login sessions (loginctl / who)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any

from core import executil

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")


class SessionError(Exception):
    """Raised when session listing fails."""


def validate_session_id(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned or not SESSION_ID_RE.fullmatch(cleaned):
        raise SessionError("Identifiant de session invalide")
    return cleaned


def current_session_id() -> str | None:
    raw = (os.environ.get("XDG_SESSION_ID") or "").strip()
    return raw or None


def is_current_session(session_id: str) -> bool:
    cur = current_session_id()
    try:
        return cur is not None and cur == validate_session_id(session_id)
    except SessionError:
        return False


def terminate_session(session_id: str) -> None:
    sid = validate_session_id(session_id)
    if shutil.which("loginctl") is None:
        raise SessionError("loginctl introuvable")
    try:
        completed = executil.run_pkexec(["loginctl", "terminate-session", sid], timeout=60.0)
        executil.check_ok(completed, what="loginctl terminate-session")
    except executil.ExecError as exc:
        raise SessionError(str(exc)) from exc


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
