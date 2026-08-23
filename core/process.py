# SPDX-License-Identifier: GPL-3.0-or-later
"""Process listing and termination."""

from __future__ import annotations

import signal
from typing import Any

import psutil

from core import host

SIGNAL_MAP = {
    "TERM": signal.SIGTERM,
    "KILL": signal.SIGKILL,
    "HUP": signal.SIGHUP,
    "INT": signal.SIGINT,
}

# Keep Process handles so cpu_percent(interval=None) is meaningful across polls
# without a full warm pass (which burned ~1–2 cores and ranked Gest itself #1).
_process_cache: dict[int, psutil.Process] = {}


class ProcessError(Exception):
    """Raised when a process operation fails."""

    def __init__(self, message: str, *, pid: int | None = None) -> None:
        super().__init__(message)
        self.pid = pid


def list_processes(*, limit: int | None = None) -> list[dict[str, Any]]:
    """Return processes sorted by CPU then RAM (descending)."""
    if host.is_flatpak():
        return host.list_processes(limit=limit)

    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    attrs = ["pid", "name", "username", "memory_info", "status"]
    for proc in psutil.process_iter(attrs):
        try:
            info = proc.info
            pid = int(info["pid"])
            seen.add(pid)
            cached = _process_cache.get(pid)
            if cached is None:
                cached = proc
                _process_cache[pid] = cached
            mem = info.get("memory_info")
            rss = float(mem.rss) if mem is not None else 0.0
            cpu = float(cached.cpu_percent(interval=None))
            rows.append(
                {
                    "pid": pid,
                    "name": str(info.get("name") or "?"),
                    "cpu": round(cpu, 1),
                    "ram_mib": round(rss / (1024**2), 1),
                    "user": str(info.get("username") or "?"),
                    "status": str(info.get("status") or "?"),
                }
            )
        except (psutil.Error, ProcessLookupError, PermissionError, TypeError, ValueError):
            continue

    stale = [pid for pid in _process_cache if pid not in seen]
    for pid in stale:
        _process_cache.pop(pid, None)

    rows.sort(key=lambda item: (item["cpu"], item["ram_mib"]), reverse=True)
    if limit is not None and limit > 0:
        return rows[:limit]
    return rows


def process_details(pid: int) -> dict[str, Any]:
    """Return detailed information for a single process."""
    if not isinstance(pid, int) or pid <= 0:
        raise ProcessError("PID invalide", pid=pid)

    if host.is_flatpak():
        try:
            data = host.process_details(pid)
        except (RuntimeError, OSError, ValueError) as exc:
            raise ProcessError(str(exc), pid=pid) from exc
        if data.get("error"):
            raise ProcessError(str(data["error"]), pid=pid)
        return data

    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess as exc:
        raise ProcessError(f"Processus {pid} introuvable", pid=pid) from exc
    except psutil.AccessDenied as exc:
        raise ProcessError(
            f"Permission refusée pour accéder au processus {pid}",
            pid=pid,
        ) from exc

    try:
        with proc.oneshot():
            cmdline_list = proc.cmdline()
            name = proc.name()
            try:
                cwd = proc.cwd()
            except (psutil.Error, PermissionError, OSError):
                cwd = "—"
            try:
                nice = proc.nice()
            except (psutil.Error, PermissionError, OSError):
                nice = None
            try:
                num_threads = proc.num_threads()
            except (psutil.Error, PermissionError, OSError):
                num_threads = None
            try:
                open_files = len(proc.open_files())
            except (psutil.Error, PermissionError, OSError):
                open_files = None
            try:
                create_time = proc.create_time()
            except (psutil.Error, PermissionError, OSError):
                create_time = None
            try:
                status = proc.status()
            except (psutil.Error, PermissionError, OSError):
                status = "?"
            try:
                username = proc.username()
            except (psutil.Error, PermissionError, OSError):
                username = "?"
            try:
                mem = proc.memory_info()
                ram_mib = round(mem.rss / (1024**2), 1)
            except (psutil.Error, PermissionError, OSError):
                ram_mib = 0.0
            try:
                cpu = round(float(proc.cpu_percent(interval=None)), 1)
            except (psutil.Error, PermissionError, OSError):
                cpu = 0.0
    except psutil.NoSuchProcess as exc:
        raise ProcessError(f"Processus {pid} introuvable", pid=pid) from exc
    except psutil.AccessDenied as exc:
        raise ProcessError(
            f"Permission refusée pour accéder au processus {pid}",
            pid=pid,
        ) from exc

    cmdline = " ".join(cmdline_list).strip() if cmdline_list else name
    return {
        "pid": pid,
        "name": name,
        "cmdline": cmdline or name,
        "cwd": cwd,
        "nice": nice,
        "num_threads": num_threads,
        "open_files": open_files,
        "create_time": create_time,
        "status": status,
        "user": username,
        "cpu": cpu,
        "ram_mib": ram_mib,
    }


def kill_process(pid: int, sig: int | str = signal.SIGTERM) -> None:
    """Send a signal to a process.

    ``sig`` may be an int signal number, a name like ``\"TERM\"`` / ``\"KILL\"``,
    or ``signal.SIGTERM`` / ``signal.SIGKILL``.
    """
    if not isinstance(pid, int) or pid <= 0:
        raise ProcessError("PID invalide", pid=pid)

    if isinstance(sig, str):
        key = sig.upper().removeprefix("SIG")
        if key not in SIGNAL_MAP:
            raise ProcessError(f"Signal inconnu: {sig}", pid=pid)
        signum = SIGNAL_MAP[key]
    else:
        signum = int(sig)

    if host.is_flatpak():
        try:
            host.kill_process(pid, signum)
            return
        except (RuntimeError, OSError) as exc:
            raise ProcessError(str(exc), pid=pid) from exc

    try:
        process = psutil.Process(pid)
    except psutil.NoSuchProcess as exc:
        raise ProcessError(f"Processus {pid} introuvable", pid=pid) from exc
    except psutil.AccessDenied as exc:
        raise ProcessError(
            f"Permission refusée pour accéder au processus {pid}",
            pid=pid,
        ) from exc

    try:
        process.send_signal(signum)
    except psutil.NoSuchProcess as exc:
        raise ProcessError(f"Processus {pid} introuvable", pid=pid) from exc
    except psutil.AccessDenied as exc:
        raise ProcessError(
            f"Permission refusée pour signaler le processus {pid}",
            pid=pid,
        ) from exc
    except PermissionError as exc:
        raise ProcessError(
            f"Permission refusée pour signaler le processus {pid}",
            pid=pid,
        ) from exc


def renice_process(pid: int, nice: int) -> None:
    """Change process nice value (-20..19). Uses pkexec if needed."""
    import os
    import shutil
    import subprocess

    if not isinstance(pid, int) or pid <= 0:
        raise ProcessError("PID invalide", pid=pid)
    value = max(-20, min(19, int(nice)))
    if host.is_flatpak():
        try:
            host.renice_process(pid, value)
            return
        except (RuntimeError, OSError) as exc:
            raise ProcessError(str(exc), pid=pid) from exc
    try:
        psutil.Process(pid).nice(value)
        return
    except psutil.NoSuchProcess as exc:
        raise ProcessError(f"Processus {pid} introuvable", pid=pid) from exc
    except (psutil.AccessDenied, PermissionError, OSError):
        pass
    if shutil.which("pkexec") is None:
        raise ProcessError("Permission refusée (pkexec introuvable)", pid=pid)
    completed = subprocess.run(
        ["pkexec", "renice", "-n", str(value), "-p", str(pid)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=host.host_cwd(),
    )
    if completed.returncode != 0:
        raise ProcessError(
            (completed.stderr or completed.stdout or "renice a échoué").strip(),
            pid=pid,
        )


def process_tree(pid: int) -> dict[str, Any]:
    """Return parent + children summary for a process."""
    if host.is_flatpak():
        try:
            data = host.process_tree(pid)
        except (RuntimeError, OSError, ValueError) as exc:
            raise ProcessError(str(exc), pid=pid) from exc
        if data.get("error"):
            raise ProcessError(str(data["error"]), pid=pid)
        return data
    details = process_details(pid)
    parent: dict[str, Any] | None = None
    children: list[dict[str, Any]] = []
    try:
        proc = psutil.Process(pid)
        try:
            pp = proc.parent()
            if pp is not None:
                parent = {"pid": pp.pid, "name": pp.name()}
        except (psutil.Error, PermissionError):
            parent = None
        try:
            for child in proc.children(recursive=False):
                try:
                    children.append({"pid": child.pid, "name": child.name()})
                except (psutil.Error, PermissionError):
                    continue
        except (psutil.Error, PermissionError):
            pass
    except psutil.Error as exc:
        raise ProcessError(str(exc), pid=pid) from exc
    details["parent"] = parent
    details["children"] = children
    return details
