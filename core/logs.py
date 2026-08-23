# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only journalctl log viewer helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

PRIORITY_MAP = {
    "err": "0..3",
    "warning": "0..4",
    "info": "0..6",
    "all": "0..7",
}


class LogsError(Exception):
    """Raised when journal access fails."""


def _permission_issue(text: str) -> bool:
    lower = text.lower()
    return any(
        needle in lower
        for needle in (
            "not seeing messages",
            "systemd-journal",
            "permission denied",
            "permission refus",
            "no journal files were opened",
            "failed to open",
            "accès refusé",
            "acces refuse",
            "d'ouvrir le journal",
        )
    )


def _clean_journal_text(stdout: str) -> str:
    lines: list[str] = []
    for raw in (stdout or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Hint:"):
            continue
        if stripped.startswith("-- No entries"):
            continue
        if stripped.startswith("-- Journal begins") or stripped.startswith("-- Journal file"):
            continue
        lines.append(line)
    return ("\n".join(lines) + "\n") if lines else ""


def _run_journalctl(cmd: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def read_journal(
    *,
    lines: int = 200,
    priority: str = "all",
    grep: str = "",
    privileged: bool = False,
) -> dict[str, Any]:
    """Return journal lines with optional priority filter and text search."""
    count = max(1, min(int(lines), 2000))
    if shutil.which("journalctl") is None:
        raise LogsError(
            "journalctl introuvable sur l'hôte. Installez systemd, ou relancez "
            "Hub Système hors Flatpak (LANCER.sh)."
        )

    prio = PRIORITY_MAP.get(priority, PRIORITY_MAP["all"])
    base = [
        "journalctl",
        "-n",
        str(count),
        "--no-pager",
        "--output=short-iso",
        "-p",
        prio,
    ]

    attempts: list[tuple[str, list[str]]] = []
    if privileged:
        if shutil.which("pkexec") is None:
            raise LogsError("pkexec introuvable (installez policykit)")
        attempts.append(("système (admin)", ["pkexec", *base, "--system"]))
    else:
        attempts.append(("système + utilisateur", list(base)))
        attempts.append(("utilisateur", [*base, "--user"]))

    text = ""
    source = ""
    needs_elevation = False
    last_err = ""

    for label, cmd in attempts:
        timeout = 60.0 if cmd and cmd[0] == "pkexec" else 30.0
        try:
            completed = _run_journalctl(cmd, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise LogsError("Délai dépassé lors de la lecture du journal") from exc
        except OSError as exc:
            raise LogsError(f"Impossible de lire le journal: {exc}") from exc

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        combined = f"{stdout}\n{stderr}"
        last_err = (stderr or stdout).strip()
        cleaned = _clean_journal_text(stdout)
        denied = _permission_issue(combined)

        if cleaned:
            text = cleaned
            source = label
            if denied and not privileged:
                needs_elevation = True
            break
        if denied or completed.returncode not in (0, 1):
            needs_elevation = not privileged
            continue

    if not text.strip():
        if needs_elevation and not privileged:
            return {
                "ok": False,
                "lines_requested": count,
                "priority": priority,
                "grep": grep,
                "text": "",
                "line_count": 0,
                "source": "",
                "needs_elevation": True,
                "message": (
                    "Accès au journal système refusé. Ajoutez votre utilisateur aux groupes "
                    "adm et systemd-journal, ou cliquez « Journal système (admin) »."
                ),
            }
        raise LogsError(last_err or "journalctl n'a renvoyé aucune entrée")

    needle = (grep or "").strip().lower()
    if needle:
        filtered = [ln for ln in text.splitlines() if needle in ln.lower()]
        text = "\n".join(filtered) + ("\n" if filtered else "")

    message = ""
    if source == "utilisateur" or (needs_elevation and not privileged):
        message = (
            "Journal utilisateur uniquement (droits insuffisants pour le journal système)."
        )

    return {
        "ok": True,
        "lines_requested": count,
        "priority": priority,
        "grep": grep,
        "text": text.rstrip() + ("\n" if text else ""),
        "line_count": len([ln for ln in text.splitlines() if ln.strip()]),
        "source": source,
        "needs_elevation": needs_elevation and not privileged,
        "message": message,
    }


def export_journal(path: str | Path, *, text: str) -> Path:
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out
