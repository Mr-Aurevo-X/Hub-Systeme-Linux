# SPDX-License-Identifier: GPL-3.0-or-later
"""System snapshots: Timeshift and/or Snapper with auto backend detection."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

from core import snapper as snapper_mod

Backend = Literal["timeshift", "snapper", "none"]

_SNAP_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")
_MISSING_TIMESHIFT = (
    "Timeshift n'est pas installé sur l'hôte (sudo apt install timeshift)."
)
SNAPSHOT_COMMENT_DEFAULT = "Hub Système"
_TIMESHIFT_DELETE_UNSUPPORTED = (
    "Suppression Timeshift non supportée depuis Hub Système (utilisez Timeshift)."
)


def sanitize_snapshot_comment(comments: str | None) -> str:
    comment = (comments or SNAPSHOT_COMMENT_DEFAULT).strip()[:200]
    return re.sub(r"[^\w\s\-.:@/]+", "", comment) or SNAPSHOT_COMMENT_DEFAULT


class BackupError(Exception):
    """Raised when a snapshot operation fails."""


def _run(cmd: list[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _needs_root(text: str) -> bool:
    lower = text.lower()
    return any(
        needle in lower
        for needle in (
            "must be run as root",
            "must be root",
            "you need to be root",
            "permission denied",
            "opération non permise",
            "operation not permitted",
            "failed to create directory",
            "failed to lock",
            "exclusive lock",
            "a besoin des droits",
            "droits administrateur",
            "authentication is required",
            "authentification",
        )
    )


def _root_is_btrfs() -> bool:
    try:
        for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "/" and parts[2] == "btrfs":
                return True
    except OSError:
        pass
    return False


def detect_backend() -> Backend:
    """Prefer Snapper on Btrfs when available; else Timeshift; else none."""
    has_snapper = snapper_mod.is_available()
    has_ts = shutil.which("timeshift") is not None
    if has_snapper and (_root_is_btrfs() or not has_ts):
        return "snapper"
    if has_ts:
        return "timeshift"
    if has_snapper:
        return "snapper"
    return "none"


def is_available() -> bool:
    return detect_backend() != "none"


def timeshift_available() -> bool:
    return shutil.which("timeshift") is not None


def status() -> dict[str, Any]:
    backend = detect_backend()
    info: dict[str, Any] = {
        "available": backend != "none",
        "backend": backend,
        "path": None,
        "message": "",
        "snapshot_count": 0,
        "needs_elevation": False,
        "btrfs_assistant": snapper_mod.btrfs_assistant_cmd(),
        "configs": [],
    }
    if backend == "none":
        info["message"] = (
            "Aucun backend de clichés (installez timeshift ou snapper)."
        )
        return info
    if backend == "snapper":
        st = snapper_mod.status()
        info.update(
            {
                "path": st.get("path"),
                "message": st.get("message") or "",
                "needs_elevation": True,
                "configs": st.get("configs") or [],
                "btrfs_assistant": st.get("btrfs_assistant"),
            }
        )
        return info
    # timeshift
    info["path"] = shutil.which("timeshift")
    info["message"] = "Timeshift est installé. Les clichés nécessitent les droits admin."
    info["needs_elevation"] = True
    return info


def list_snapshots(
    *,
    privileged: bool = False,
    backend: Backend | None = None,
    config: str = "root",
) -> list[dict[str, Any]]:
    be = backend or detect_backend()
    if be == "snapper":
        try:
            items = snapper_mod.list_snapshots(config, privileged=privileged)
        except snapper_mod.SnapperError as exc:
            raise BackupError(str(exc)) from exc
        for item in items:
            item["backend"] = "snapper"
            item["config"] = config
        return items
    if be == "timeshift":
        return _list_timeshift(privileged=privileged)
    raise BackupError("Aucun backend de clichés disponible")


def _list_timeshift(*, privileged: bool = False) -> list[dict[str, Any]]:
    if not timeshift_available():
        raise BackupError(_MISSING_TIMESHIFT)

    cmd = ["timeshift", "--list"]
    if privileged:
        cmd = ["pkexec", "timeshift", "--list"]
    try:
        completed = _run(cmd, timeout=180.0)
    except subprocess.TimeoutExpired as exc:
        raise BackupError("Délai dépassé lors de la liste Timeshift") from exc
    except OSError as exc:
        raise BackupError(f"Impossible d'exécuter timeshift: {exc}") from exc

    raw = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0 or _needs_root(raw):
        err = (completed.stderr or completed.stdout or "").strip()
        if not privileged and (_needs_root(raw) or completed.returncode != 0):
            raise BackupError(
                "Timeshift exige les droits administrateur pour lister les clichés. "
                "Utilisez « Charger les clichés (admin) »."
            )
        raise BackupError(err or "Échec de timeshift --list")

    snapshots: list[dict[str, Any]] = []
    for line in (completed.stdout or "").splitlines():
        match = re.search(
            r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\s+(\S+)?\s*(.*)$",
            line.strip(),
        )
        if not match:
            # Alternate: lines starting with snapshot name
            parts = line.split()
            if parts and _SNAP_NAME_RE.fullmatch(parts[0]):
                snapshots.append(
                    {
                        "id": parts[0],
                        "name": parts[0],
                        "date": parts[0].replace("_", " "),
                        "description": " ".join(parts[1:]),
                        "backend": "timeshift",
                    }
                )
            continue
        name = match.group(1)
        snapshots.append(
            {
                "id": name,
                "name": name,
                "date": name.replace("_", " "),
                "description": (match.group(3) or "").strip(),
                "backend": "timeshift",
            }
        )
    return snapshots


def create_snapshot(
    comments: str = "",
    *,
    backend: Backend | None = None,
    config: str = "root",
) -> dict[str, Any]:
    be = backend or detect_backend()
    if be == "snapper":
        try:
            return snapper_mod.create_snapshot(config, description=comments or "Hub Système")
        except snapper_mod.SnapperError as exc:
            raise BackupError(str(exc)) from exc
    if be != "timeshift":
        raise BackupError("Aucun backend de clichés disponible")
    if not timeshift_available():
        raise BackupError(_MISSING_TIMESHIFT)
    if shutil.which("pkexec") is None:
        raise BackupError("pkexec introuvable (installez policykit)")

    comment = sanitize_snapshot_comment(comments)

    cmd = ["pkexec", "timeshift", "--create", "--comments", comment]
    try:
        completed = _run(cmd, timeout=3600.0)
    except subprocess.TimeoutExpired as exc:
        raise BackupError("Délai dépassé lors de la création du cliché") from exc
    except OSError as exc:
        raise BackupError(f"Échec d'exécution Timeshift: {exc}") from exc

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise BackupError(err or f"timeshift --create a échoué ({completed.returncode})")

    return {
        "ok": True,
        "comments": comment,
        "stdout": completed.stdout.strip(),
        "backend": "timeshift",
    }


def restore_snapshot(
    name: str,
    *,
    backend: Backend | None = None,
    config: str = "root",
) -> dict[str, Any]:
    be = backend or detect_backend()
    if be == "snapper":
        try:
            return snapper_mod.rollback_snapshot(config, name)
        except snapper_mod.SnapperError as exc:
            raise BackupError(str(exc)) from exc
    if be != "timeshift":
        raise BackupError("Aucun backend de clichés disponible")
    if not timeshift_available():
        raise BackupError(_MISSING_TIMESHIFT)
    if shutil.which("pkexec") is None:
        raise BackupError("pkexec introuvable (installez policykit)")
    snap = (name or "").strip()
    if not _SNAP_NAME_RE.fullmatch(snap):
        raise BackupError("Nom de cliché invalide")

    cmd = ["pkexec", "timeshift", "--restore", "--snapshot", snap, "--yes"]
    try:
        completed = _run(cmd, timeout=3600.0)
    except subprocess.TimeoutExpired as exc:
        raise BackupError("Délai dépassé lors de la restauration Timeshift") from exc
    except OSError as exc:
        raise BackupError(f"Échec d'exécution Timeshift: {exc}") from exc

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise BackupError(err or f"timeshift --restore a échoué ({completed.returncode})")

    return {
        "ok": True,
        "snapshot": snap,
        "stdout": (completed.stdout or "").strip(),
        "backend": "timeshift",
    }


def delete_snapshot(
    name: str,
    *,
    backend: Backend | None = None,
    config: str = "root",
) -> dict[str, Any]:
    be = backend or detect_backend()
    if be == "snapper":
        try:
            return snapper_mod.delete_snapshot(config, name)
        except snapper_mod.SnapperError as exc:
            raise BackupError(str(exc)) from exc
    raise BackupError(_TIMESHIFT_DELETE_UNSUPPORTED)


def open_btrfs_assistant() -> None:
    cmd = snapper_mod.btrfs_assistant_cmd()
    if not cmd:
        raise BackupError("Btrfs Assistant introuvable")
    try:
        subprocess.Popen([cmd], start_new_session=True)  # noqa: S603
    except OSError as exc:
        raise BackupError(str(exc)) from exc


def reminder_status() -> dict[str, Any]:
    """Dashboard hint only — never triggers pkexec (Snapper needs admin)."""
    st = status()
    if not st.get("available"):
        return {"visible": False, "ok": True, "count": 0, "needs_admin": False}
    backend = str(st.get("backend") or "")
    if backend == "snapper":
        return {
            "visible": True,
            "ok": None,
            "count": 0,
            "needs_admin": True,
            "backend": backend,
        }
    try:
        snaps = list_snapshots(privileged=False)
    except BackupError:
        snaps = []
    count = len(snaps)
    return {
        "visible": True,
        "ok": count > 0,
        "count": count,
        "needs_admin": False,
        "backend": backend,
    }
