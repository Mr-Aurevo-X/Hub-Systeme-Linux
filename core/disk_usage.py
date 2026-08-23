# SPDX-License-Identifier: GPL-3.0-or-later
"""Disk usage analysis via du (local, bounded)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_PATH_RE = re.compile(r"^[/a-zA-Z0-9._\-]+$")


class DiskUsageError(Exception):
    """Raised when disk usage scan fails."""


def _run(cmd: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)


def validate_scan_path(path: str) -> Path:
    text = (path or "").strip() or "/"
    if not _PATH_RE.fullmatch(text):
        raise DiskUsageError("Chemin invalide")
    resolved = Path(text).resolve()
    if not resolved.exists():
        raise DiskUsageError("Chemin introuvable")
    return resolved


def scan_top(path: str = "/", *, limit: int = 15, timeout: float = 45.0) -> list[dict[str, Any]]:
    root = validate_scan_path(path)
    if not shutil.which("du"):
        raise DiskUsageError("du introuvable")
    cmd = ["du", "-x", "-B1", "--max-depth=1", str(root)]
    try:
        completed = _run(cmd, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiskUsageError(str(exc)) from exc
    if completed.returncode not in (0, 1):
        err = (completed.stderr or completed.stdout or "").strip()
        raise DiskUsageError(err or f"du ({completed.returncode})")
    rows: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        try:
            size = int(parts[0])
        except ValueError:
            continue
        rows.append({"path": parts[1], "bytes": size})
    rows.sort(key=lambda r: int(r.get("bytes") or 0), reverse=True)
    return rows[: max(1, min(limit, 50))]


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{value} B"
