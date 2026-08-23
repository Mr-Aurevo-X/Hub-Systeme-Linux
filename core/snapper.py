# SPDX-License-Identifier: GPL-3.0-or-later
"""Snapper (Btrfs) snapshot integration for CachyOS / Arch-like hosts."""

from __future__ import annotations

import re
import shutil
from typing import Any

from core import executil

_CONFIG_RE = re.compile(r"^[A-Za-z0-9_@.-]+$")
_NUM_RE = re.compile(r"^\d+$")


class SnapperError(Exception):
    """Raised when a Snapper operation fails."""


_MISSING = "Snapper n'est pas installé (sudo pacman -S snapper)."


def is_available() -> bool:
    return shutil.which("snapper") is not None


def btrfs_assistant_cmd() -> str | None:
    for name in ("btrfs-assistant-launcher", "btrfs-assistant"):
        if shutil.which(name):
            return name
    return None


def status() -> dict[str, Any]:
    available = is_available()
    info: dict[str, Any] = {
        "available": available,
        "path": shutil.which("snapper"),
        "message": "",
        "configs": [],
        "btrfs_assistant": btrfs_assistant_cmd(),
        "needs_elevation": True,
    }
    if not available:
        info["message"] = _MISSING
        return info
    info["message"] = "Snapper est installé. Les clichés nécessitent les droits admin."
    try:
        info["configs"] = list_configs(privileged=False)
    except SnapperError:
        info["configs"] = []
    return info


def _validate_config(name: str) -> str:
    clean = name.strip()
    if not clean or not _CONFIG_RE.match(clean):
        raise SnapperError(f"Config Snapper invalide: {name}")
    return clean


def _validate_number(num: str | int) -> str:
    text = str(num).strip()
    if not _NUM_RE.match(text):
        raise SnapperError(f"Numéro de cliché invalide: {num}")
    return text


def list_configs(*, privileged: bool = False) -> list[str]:
    if not is_available():
        raise SnapperError(_MISSING)
    cmd = ["snapper", "list-configs"]
    if privileged:
        completed = executil.run_pkexec(cmd, timeout=60.0)
    else:
        completed = executil.run(cmd, timeout=30.0)
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        if not privileged and err:
            # Often needs root — caller may retry privileged
            raise SnapperError(err or "list-configs a échoué")
        raise SnapperError(err or "list-configs a échoué")
    configs: list[str] = []
    for line in (completed.stdout or "").splitlines():
        line = line.strip()
        if not line or line.lower().startswith("config") or set(line) <= {"-", "|", " "}:
            continue
        # Formats: "root | /" or "root"
        name = line.split("|", 1)[0].strip().split()[0] if line else ""
        if name and _CONFIG_RE.match(name) and name.lower() != "config":
            configs.append(name)
    return configs


def parse_list_output(text: str) -> list[dict[str, Any]]:
    """Parse ``snapper list`` / ``snapper -c X list`` tabular output."""
    snapshots: list[dict[str, Any]] = []
    for line in text.splitlines():
        raw = line.rstrip()
        if not raw.strip():
            continue
        lower = raw.lower()
        if lower.startswith("type") or lower.startswith("#") or set(raw.strip()) <= {"-", "+", "|", " "}:
            continue
        if "|" in raw:
            parts = [p.strip() for p in raw.split("|")]
            # Common: Type | # | Pre # | Date | User | Cleanup | Description | …
            num = ""
            snap_type = parts[0] if parts else ""
            if len(parts) > 1 and _NUM_RE.match(parts[1]):
                num = parts[1]
            elif parts and _NUM_RE.match(parts[0].lstrip("#")):
                num = parts[0].lstrip("#")
            if not num:
                continue
            date = parts[3] if len(parts) > 3 else ""
            desc = parts[6] if len(parts) > 6 else (parts[-1] if len(parts) > 4 else "")
        else:
            parts = raw.split(None, 6)
            if len(parts) < 2:
                continue
            # number first, or type then number
            if _NUM_RE.match(parts[0].lstrip("#")):
                num = parts[0].lstrip("#")
                snap_type = parts[1] if len(parts) > 1 else ""
                date = parts[2] if len(parts) > 2 else ""
                desc = parts[-1] if len(parts) > 3 else ""
            elif len(parts) > 1 and _NUM_RE.match(parts[1]):
                snap_type = parts[0]
                num = parts[1]
                date = parts[3] if len(parts) > 3 else ""
                desc = parts[-1] if len(parts) > 4 else ""
            else:
                continue
        snapshots.append(
            {
                "id": num,
                "name": num,
                "date": date,
                "description": desc,
                "type": snap_type,
                "backend": "snapper",
            }
        )
    return snapshots


def list_snapshots(config: str = "root", *, privileged: bool = True) -> list[dict[str, Any]]:
    if not is_available():
        raise SnapperError(_MISSING)
    cfg = _validate_config(config)
    args = ["snapper", "-c", cfg, "list"]
    try:
        if privileged:
            completed = executil.run_pkexec(args, timeout=120.0)
        else:
            completed = executil.run(args, timeout=60.0)
    except executil.ExecError as exc:
        raise SnapperError(str(exc)) from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise SnapperError(err or "snapper list a échoué")
    return parse_list_output(completed.stdout or "")


def create_snapshot(config: str = "root", *, description: str = "Hub Système") -> dict[str, Any]:
    if not is_available():
        raise SnapperError(_MISSING)
    cfg = _validate_config(config)
    desc = (description or "Hub Système").strip()[:120] or "Hub Système"
    # Restrict description to safe printable chars
    if not re.match(r"^[\w .@_+/:#-]+$", desc, re.UNICODE):
        raise SnapperError("Description de cliché invalide")
    args = ["snapper", "-c", cfg, "create", "--description", desc]
    try:
        completed = executil.run_pkexec(args, timeout=300.0)
        out = executil.check_ok(completed, what="snapper create")
    except executil.ExecError as exc:
        raise SnapperError(str(exc)) from exc
    return {"ok": True, "config": cfg, "stdout": out, "backend": "snapper"}


def delete_snapshot(config: str, number: str | int) -> dict[str, Any]:
    if not is_available():
        raise SnapperError(_MISSING)
    cfg = _validate_config(config)
    num = _validate_number(number)
    args = ["snapper", "-c", cfg, "delete", num]
    try:
        completed = executil.run_pkexec(args, timeout=300.0)
        out = executil.check_ok(completed, what="snapper delete")
    except executil.ExecError as exc:
        raise SnapperError(str(exc)) from exc
    return {"ok": True, "config": cfg, "id": num, "stdout": out}


def rollback_snapshot(config: str, number: str | int) -> dict[str, Any]:
    """Best-effort rollback via snapper undochange / rollback (Btrfs)."""
    if not is_available():
        raise SnapperError(_MISSING)
    cfg = _validate_config(config)
    num = _validate_number(number)
    # Prefer `snapper rollback` when available (openSUSE / some setups)
    for args in (
        ["snapper", "-c", cfg, "rollback", num],
        ["snapper", "-c", cfg, "undochange", f"{num}..0"],
    ):
        try:
            completed = executil.run_pkexec(args, timeout=600.0)
        except executil.ExecError as exc:
            last = str(exc)
            continue
        if completed.returncode == 0:
            return {
                "ok": True,
                "config": cfg,
                "id": num,
                "stdout": (completed.stdout or "").strip(),
                "backend": "snapper",
            }
        last = (completed.stderr or completed.stdout or "").strip()
    raise SnapperError(last or "snapper rollback a échoué")
