# SPDX-License-Identifier: GPL-3.0-or-later
"""Flatpak-aware host execution.

Inside a Flatpak sandbox, ``/proc`` and host tools (systemctl, pkexec,
journalctl, …) are not the real system. Commands are forwarded with
``flatpak-spawn --host``. Metrics and process lists use a stdlib probe
run on the host Python.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

_orig_run = subprocess.run
_orig_which = shutil.which
_installed = False

_PROBE = Path(__file__).with_name("host_probe.py")

# Sandbox PATH is typically /app/bin:/usr/bin — host tools live in /usr/sbin too.
_HOST_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Forwarded Flatpak env breaks host binaries (ufw is Python, timeshift uses GTK/GI).
_UNSET_HOST_ENV = (
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "PYTHONPATH",
    "PYTHONHOME",
    "GI_TYPELIB_PATH",
    "GIO_MODULE_DIR",
    "GTK_PATH",
    "GTK_DATA_PREFIX",
    "GST_PLUGIN_SYSTEM_PATH",
    "GST_PLUGIN_SYSTEM_PATH_1_0",
)


def is_flatpak() -> bool:
    return Path("/.flatpak-info").exists() or bool(os.environ.get("FLATPAK_ID"))


def _is_sandbox_path(path: str) -> bool:
    return path == "/app" or path.startswith("/app/")


def host_cwd() -> str:
    """Directory that exists on the host. Never a Flatpak ``/app/...`` path."""
    candidates = [
        os.environ.get("HOME"),
        str(Path.home()),
        "/",
    ]
    for raw in candidates:
        if not raw:
            continue
        path = os.path.abspath(raw)
        if _is_sandbox_path(path):
            continue
        try:
            if os.path.isdir(path):
                return path
        except OSError:
            continue
    return "/"


def _effective_host_cwd(cwd: Any) -> str:
    if cwd is not None:
        try:
            text = os.fspath(cwd)
        except TypeError:
            text = ""
        if text and not _is_sandbox_path(os.path.abspath(text)):
            return os.path.abspath(text)
    return host_cwd()


def _with_host_cwd(kwargs: dict[str, Any]) -> dict[str, Any]:
    out = dict(kwargs)
    out["cwd"] = _effective_host_cwd(out.get("cwd"))
    return out


def wrap(cmd: list[str]) -> list[str]:
    if not is_flatpak() or not cmd or cmd[0] == "flatpak-spawn":
        return list(cmd)
    env_cmd: list[str] = ["/usr/bin/env"]
    for name in _UNSET_HOST_ENV:
        env_cmd.extend(["-u", name])
    env_cmd.append(f"PATH={_HOST_PATH}")
    env_cmd.extend(cmd)
    return ["flatpak-spawn", "--host", f"--directory={host_cwd()}", "--", *env_cmd]


def run(cmd: Any, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    if isinstance(cmd, (list, tuple)):
        cmd = wrap([str(part) for part in cmd])
        if is_flatpak() and cmd and cmd[0] == "flatpak-spawn":
            kwargs = _with_host_cwd(kwargs)
    return _orig_run(cmd, *args, **kwargs)


def popen(cmd: list[str], **kwargs: Any) -> subprocess.Popen[Any]:
    """``Popen`` with the same Flatpak host wrap as ``run``."""
    wrapped = wrap([str(part) for part in cmd])
    if is_flatpak() and wrapped and wrapped[0] == "flatpak-spawn":
        kwargs = _with_host_cwd(kwargs)
    return subprocess.Popen(wrapped, **kwargs)


def which(cmd: str) -> str | None:
    """Locate a host executable. ``command -v`` is a shell builtin, not a binary."""
    if not cmd or cmd.startswith("-"):
        return None
    if not is_flatpak():
        return _orig_which(cmd)
    if "/" in cmd:
        try:
            completed = _orig_run(
                wrap(["test", "-x", cmd]),
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
                cwd=host_cwd(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return cmd if completed.returncode == 0 else None
    try:
        completed = _orig_run(
            wrap(["sh", "-c", 'command -v "$1"', "sh", cmd]),
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
            cwd=host_cwd(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (completed.stdout or "").strip().splitlines()
    if completed.returncode == 0 and lines:
        path = lines[0].strip()
        return path or None
    return None


def install_flatpak_host_bridge() -> None:
    """Patch ``subprocess.run`` / ``shutil.which`` so system tools hit the host."""
    global _installed
    if _installed or not is_flatpak():
        return
    subprocess.run = run  # type: ignore[assignment]
    shutil.which = which  # type: ignore[assignment]
    _installed = True


def _host_probe(mode: str, *extra: str, timeout: float = 12.0) -> dict[str, Any]:
    script = _PROBE.read_text(encoding="utf-8")
    completed = _orig_run(
        wrap(["python3", "-", mode, *extra]),
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=host_cwd(),
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(err or f"host probe failed ({completed.returncode})")
    raw = (completed.stdout or "").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("host probe returned invalid JSON")
    return data


def collect_metrics() -> dict[str, Any]:
    return _host_probe("metrics", timeout=15.0)


def collect_inventory() -> dict[str, Any]:
    return _host_probe("inventory", timeout=20.0)


def list_processes(*, limit: int | None = None) -> list[dict[str, Any]]:
    extra = [str(int(limit))] if limit is not None and limit > 0 else []
    data = _host_probe("processes", *extra, timeout=12.0)
    rows = data.get("processes") or []
    return rows if isinstance(rows, list) else []


def process_details(pid: int) -> dict[str, Any]:
    data = _host_probe("details", str(int(pid)), timeout=8.0)
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data


def process_tree(pid: int) -> dict[str, Any]:
    data = _host_probe("tree", str(int(pid)), timeout=8.0)
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data


def kill_process(pid: int, signum: int) -> None:
    completed = run(
        ["kill", f"-{int(signum)}", str(int(pid))],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode == 0:
        return
    if which("pkexec") is None:
        err = (completed.stderr or completed.stdout or "kill a échoué").strip()
        raise RuntimeError(err)
    completed = run(
        ["pkexec", "kill", f"-{int(signum)}", str(int(pid))],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "kill a échoué").strip()
        raise RuntimeError(err)


def renice_process(pid: int, nice: int) -> None:
    completed = run(
        ["renice", "-n", str(int(nice)), "-p", str(int(pid))],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode == 0:
        return
    if which("pkexec") is None:
        err = (completed.stderr or completed.stdout or "renice a échoué").strip()
        raise RuntimeError(err)
    completed = run(
        ["pkexec", "renice", "-n", str(int(nice)), "-p", str(int(pid))],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "renice a échoué").strip()
        raise RuntimeError(err)

