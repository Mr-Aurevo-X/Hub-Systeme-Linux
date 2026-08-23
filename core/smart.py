# SPDX-License-Identifier: GPL-3.0-or-later
"""SMART disk health (read-only smartctl)."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

_SMART_RE = re.compile(r"SMART overall-health self-assessment test result:\s*(\w+)", re.I)


class SmartError(Exception):
    """Raised when SMART query fails."""


def is_available() -> bool:
    return shutil.which("smartctl") is not None


def _run(cmd: list[str], *, timeout: float = 25.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)


def query_device(device: str) -> dict[str, Any]:
    dev = (device or "").strip()
    if not dev or not re.fullmatch(r"/dev/[a-zA-Z0-9]+", dev):
        raise SmartError("Périphérique invalide")
    if not is_available():
        raise SmartError("smartctl introuvable")
    try:
        completed = _run(["smartctl", "-H", "-A", dev], timeout=30.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SmartError(str(exc)) from exc
    text = f"{completed.stdout}\n{completed.stderr}"
    health = "unknown"
    match = _SMART_RE.search(text)
    if match:
        health = match.group(1).lower()
    ok = health in {"passed", "ok"}
    return {
        "device": dev,
        "health": health,
        "ok": ok,
        "raw": text.strip()[:4000],
        "returncode": completed.returncode,
    }


def list_block_devices() -> list[str]:
    if not shutil.which("lsblk"):
        return []
    try:
        completed = _run(["lsblk", "-dn", "-o", "NAME,TYPE"], timeout=10.0)
    except (OSError, subprocess.TimeoutExpired):
        return []
    out: list[str] = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "disk":
            out.append(f"/dev/{parts[0]}")
    return out


def summarize() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for dev in list_block_devices()[:6]:
        try:
            items.append(query_device(dev))
        except SmartError as exc:
            items.append({"device": dev, "health": "error", "ok": False, "error": str(exc)})
    return items
