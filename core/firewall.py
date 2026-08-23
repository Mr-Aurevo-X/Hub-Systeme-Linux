# SPDX-License-Identifier: GPL-3.0-or-later
"""Firewall status/control: UFW and firewalld."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any, Literal

Backend = Literal["ufw", "firewalld", "none"]

_MISSING_UFW = (
    "UFW n'est pas installé sur l'hôte (sudo apt install ufw). "
    "Le binaire se trouve généralement dans /usr/sbin/ufw."
)
_MISSING_ANY = (
    "Aucun pare-feu géré (installez ufw ou firewalld)."
)


class FirewallError(Exception):
    """Raised when firewall operations fail."""


def detect_backend() -> Backend:
    if shutil.which("ufw") is not None:
        return "ufw"
    if shutil.which("firewall-cmd") is not None:
        return "firewalld"
    return "none"


def is_available() -> bool:
    return detect_backend() != "none"


def _parse_active(text: str) -> bool | None:
    lower = text.lower()
    if re.search(r"(?:status|statut)\s*:\s*active\b", lower) or re.search(
        r"(?:status|statut)\s*:\s*actif\b", lower
    ):
        return True
    if re.search(r"(?:status|statut)\s*:\s*inactive\b", lower) or re.search(
        r"(?:status|statut)\s*:\s*inactif\b", lower
    ):
        return False
    return None


def _needs_root(text: str) -> bool:
    lower = text.lower()
    return any(
        needle in lower
        for needle in (
            "devez être root",
            "devez etre root",
            "must be root",
            "you need to be root",
            "permission denied",
            "opération non permise",
            "operation not permitted",
            "command not found",
            "commande introuvable",
            "authorize",
            "authentication",
        )
    )


def _systemd_ufw_active() -> bool | None:
    if shutil.which("systemctl") is None:
        return None
    for unit in ("ufw", "ufw.service"):
        try:
            completed = subprocess.run(
                ["systemctl", "is-active", unit],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        state = (completed.stdout or "").strip().lower()
        if state == "active":
            return True
        if state in {"inactive", "failed", "dead"}:
            return False
    try:
        completed = subprocess.run(
            ["systemctl", "is-enabled", "ufw"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        enabled = (completed.stdout or "").strip().lower()
        if enabled == "enabled":
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _run_ufw_status(*, privileged: bool) -> tuple[str, int]:
    if privileged:
        if shutil.which("pkexec") is None:
            raise FirewallError("pkexec introuvable")
        cmd = ["pkexec", "env", "LC_ALL=C", "LANG=C", "ufw", "status", "verbose"]
    else:
        cmd = ["env", "LC_ALL=C", "LANG=C", "ufw", "status", "verbose"]
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=60 if privileged else 20,
    )
    raw = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
    return raw.strip(), completed.returncode


def _extract_rules(raw: str) -> list[str]:
    rules: list[str] = []
    for ln in raw.splitlines():
        line = ln.strip()
        if not line:
            continue
        if re.match(r"^(Status|Statut)\s*:", line, re.IGNORECASE):
            continue
        if _needs_root(line) or line.upper().startswith("ERROR:"):
            continue
        if line.lower().startswith("logging:") or line.lower().startswith("default:"):
            continue
        if line.lower().startswith("new profiles:"):
            continue
        rules.append(line)
    return rules[:80]


def _firewalld_status(*, privileged: bool) -> dict[str, Any]:
    if shutil.which("firewall-cmd") is None:
        return {
            "available": False,
            "active": False,
            "raw": "",
            "rules": [],
            "message": "firewall-cmd introuvable",
            "needs_elevation": False,
            "backend": "firewalld",
        }
    cmd_base = ["firewall-cmd"]
    if privileged:
        if shutil.which("pkexec") is None:
            raise FirewallError("pkexec introuvable")
        cmd_base = ["pkexec", "firewall-cmd"]
    try:
        state = subprocess.run(
            [*cmd_base, "--state"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "available": True,
            "active": False,
            "raw": "",
            "rules": [],
            "message": str(exc),
            "needs_elevation": not privileged,
            "backend": "firewalld",
        }
    out = (state.stdout or state.stderr or "").strip().lower()
    active = out == "running"
    needs_elevation = (not privileged) and (
        state.returncode != 0 or _needs_root(state.stdout or "") or _needs_root(state.stderr or "")
    )
    rules: list[str] = []
    raw = (state.stdout or "").strip()
    if active and not needs_elevation:
        for args in (
            ["--list-all"],
            ["--list-services"],
            ["--list-ports"],
        ):
            try:
                completed = subprocess.run(
                    [*cmd_base, *args],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            text = (completed.stdout or "").strip()
            if text:
                raw = text
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        rules.append(line[:120])
                break
    return {
        "available": True,
        "active": active,
        "raw": raw,
        "rules": rules[:80],
        "message": "firewalld exige les droits admin" if needs_elevation else "",
        "needs_elevation": needs_elevation,
        "backend": "firewalld",
    }


def status(*, privileged: bool = False) -> dict[str, Any]:
    backend = detect_backend()
    if backend == "firewalld":
        return _firewalld_status(privileged=privileged)
    if backend != "ufw":
        return {
            "available": False,
            "active": False,
            "raw": "",
            "rules": [],
            "message": _MISSING_ANY,
            "needs_elevation": False,
            "backend": "none",
        }

    raw = ""
    active: bool | None = None
    message = ""
    needs_elevation = False

    active = _systemd_ufw_active()

    try:
        raw, _code = _run_ufw_status(privileged=False)
        parsed = _parse_active(raw)
        if parsed is not None:
            active = parsed
        if _needs_root(raw):
            needs_elevation = True
            raw = ""
            if not privileged:
                message = "UFW exige les droits admin pour lister les règles"
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = str(exc)

    if (needs_elevation or active is None or not raw) and privileged:
        try:
            raw, _code = _run_ufw_status(privileged=True)
            parsed = _parse_active(raw)
            if parsed is not None:
                active = parsed
            needs_elevation = False
            if _needs_root(raw):
                message = "Impossible de lire UFW même avec élévation"
            else:
                message = ""
        except FirewallError as exc:
            message = str(exc)
        except (OSError, subprocess.TimeoutExpired) as exc:
            message = str(exc)

    if active is None:
        active = False
        if not message:
            message = "Impossible de déterminer l'état UFW"

    rules = _extract_rules(raw) if raw and not _needs_root(raw) else []
    if needs_elevation and not rules and not message:
        message = "UFW exige les droits admin pour lister les règles"

    return {
        "available": True,
        "active": bool(active),
        "raw": raw,
        "rules": rules,
        "message": message,
        "needs_elevation": needs_elevation,
        "backend": "ufw",
    }


def set_enabled(enabled: bool) -> None:
    backend = detect_backend()
    if backend == "firewalld":
        if shutil.which("pkexec") is None:
            raise FirewallError("pkexec introuvable")
        action = "--set-default-zone=public" if enabled else None
        # Start/stop firewalld service
        unit_action = "start" if enabled else "stop"
        completed = subprocess.run(
            ["pkexec", "systemctl", unit_action, "firewalld"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode != 0:
            raise FirewallError(
                (completed.stderr or completed.stdout or "échec firewalld").strip()
            )
        if enabled and action:
            subprocess.run(
                ["pkexec", "firewall-cmd", "--reload"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        return
    if backend != "ufw":
        raise FirewallError(_MISSING_ANY)
    if shutil.which("pkexec") is None:
        raise FirewallError("pkexec introuvable")
    cmd = ["pkexec", "ufw", "--force", "enable"] if enabled else ["pkexec", "ufw", "disable"]
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FirewallError(str(exc)) from exc
    if completed.returncode != 0:
        raise FirewallError((completed.stderr or completed.stdout or "échec ufw").strip())
