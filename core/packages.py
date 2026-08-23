# SPDX-License-Identifier: GPL-3.0-or-later
"""Package detection and uninstallation (APT, DNF, pacman, Flatpak, Snap)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core import host
from core import updater

PKG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._/:@-]*$")


class PackageError(Exception):
    """Raised when a package operation fails."""


def _run(cmd: list[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def available_managers() -> dict[str, bool]:
    return {
        "apt": shutil.which("dpkg-query") is not None or shutil.which("apt-get") is not None,
        "dnf": shutil.which("dnf") is not None,
        "pacman": shutil.which("pacman") is not None,
        "flatpak": shutil.which("flatpak") is not None,
        "snap": shutil.which("snap") is not None,
    }


def _list_apt() -> list[dict[str, Any]]:
    if shutil.which("dpkg-query") is None:
        return []
    try:
        completed = _run(
            ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"],
            timeout=60.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []

    packages: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, version, status = parts[0], parts[1], parts[2]
        if "installed" not in status:
            continue
        packages.append(
            {
                "name": name,
                "version": version,
                "manager": "apt",
                "id": name,
                "description": "",
            }
        )
    return packages


def _list_flatpak() -> list[dict[str, Any]]:
    if shutil.which("flatpak") is None:
        return []
    try:
        completed = _run(
            ["flatpak", "list", "--columns=application,name,version,branch"],
            timeout=60.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []

    packages: list[dict[str, Any]] = []
    lines = completed.stdout.splitlines()
    # Skip header if present
    start = 1 if lines and "Application" in lines[0] else 0
    for line in lines[start:]:
        parts = line.split("\t")
        if len(parts) < 1 or not parts[0].strip():
            # flatpak may use multiple spaces
            parts = re.split(r"\s{2,}", line.strip())
        if not parts or not parts[0]:
            continue
        app_id = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else app_id
        version = parts[2].strip() if len(parts) > 2 else ""
        packages.append(
            {
                "name": name,
                "version": version,
                "manager": "flatpak",
                "id": app_id,
                "description": app_id,
            }
        )
    return packages


def _list_snap() -> list[dict[str, Any]]:
    if shutil.which("snap") is None:
        return []
    try:
        completed = _run(["snap", "list"], timeout=60.0)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []

    packages: list[dict[str, Any]] = []
    lines = completed.stdout.splitlines()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        name, version = parts[0], parts[1]
        packages.append(
            {
                "name": name,
                "version": version,
                "manager": "snap",
                "id": name,
                "description": "",
            }
        )
    return packages



def _list_dnf() -> list[dict[str, Any]]:
    if shutil.which("rpm") is None:
        return []
    try:
        completed = _run(
            ["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\n"],
            timeout=120.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    packages: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        packages.append(
            {
                "name": parts[0],
                "version": parts[1],
                "manager": "dnf",
                "id": parts[0],
                "description": "",
            }
        )
    return packages


def _list_pacman() -> list[dict[str, Any]]:
    if shutil.which("pacman") is None:
        return []
    try:
        completed = _run(["pacman", "-Q"], timeout=120.0)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    packages: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        packages.append(
            {
                "name": parts[0],
                "version": parts[1],
                "manager": "pacman",
                "id": parts[0],
                "description": "",
            }
        )
    return packages


def list_packages(*, managers: list[str] | None = None) -> list[dict[str, Any]]:
    """List installed packages from selected managers (default: all available)."""
    avail = available_managers()
    wanted = managers or [m for m, ok in avail.items() if ok]
    packages: list[dict[str, Any]] = []
    if "apt" in wanted and avail.get("apt"):
        packages.extend(_list_apt())
    if "dnf" in wanted and avail.get("dnf"):
        packages.extend(_list_dnf())
    if "pacman" in wanted and avail.get("pacman"):
        packages.extend(_list_pacman())
    if "flatpak" in wanted and avail.get("flatpak"):
        packages.extend(_list_flatpak())
    if "snap" in wanted and avail.get("snap"):
        packages.extend(_list_snap())
    packages.sort(key=lambda item: (item["manager"], item["name"].lower()))
    return packages


def parse_pacman_orphans(text: str) -> list[str]:
    names: list[str] = []
    for line in (text or "").splitlines():
        name = line.strip()
        if name and PKG_NAME_RE.fullmatch(name):
            names.append(name)
    return names


def parse_apt_autoremove(text: str) -> list[str]:
    names: list[str] = []
    in_block = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if "will be REMOVED" in stripped or "seront SUPPRIM" in stripped:
            in_block = True
            continue
        if stripped.startswith("Remv "):
            parts = stripped.split()
            if len(parts) >= 2 and PKG_NAME_RE.fullmatch(parts[1]):
                names.append(parts[1])
            continue
        if not in_block:
            continue
        if not stripped or stripped[0].isdigit():
            in_block = False
            continue
        for part in stripped.split():
            if PKG_NAME_RE.fullmatch(part):
                names.append(part)
    return names


def parse_dnf_unneeded(text: str) -> list[str]:
    names: list[str] = []
    for line in (text or "").splitlines():
        token = line.split()[0] if line.strip() else ""
        if token and PKG_NAME_RE.fullmatch(token):
            names.append(token)
    return names


def list_orphans() -> list[dict[str, Any]]:
    """Return unused packages per available native manager (no Flatpak/Snap)."""
    avail = available_managers()
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _add(manager: str, name: str) -> None:
        key = (manager, name)
        if key in seen:
            return
        seen.add(key)
        items.append({"name": name, "id": name, "manager": manager, "version": ""})

    if avail.get("pacman") and shutil.which("pacman"):
        try:
            completed = _run(["pacman", "-Qtdq"], timeout=60.0)
            for name in parse_pacman_orphans(completed.stdout or ""):
                _add("pacman", name)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if avail.get("apt") and shutil.which("apt-get"):
        try:
            completed = _run(["apt-get", "-s", "-y", "autoremove"], timeout=90.0)
            for name in parse_apt_autoremove(f"{completed.stdout}\n{completed.stderr}"):
                _add("apt", name)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if avail.get("dnf") and shutil.which("dnf"):
        try:
            completed = _run(["dnf", "repoquery", "--unneeded", "-q"], timeout=90.0)
            for name in parse_dnf_unneeded(completed.stdout or ""):
                _add("dnf", name)
        except (OSError, subprocess.TimeoutExpired):
            pass
    items.sort(key=lambda item: (item["manager"], item["name"].lower()))
    return items


def _validate_pkg_id(pkg_id: str) -> str:
    cleaned = pkg_id.strip()
    if not cleaned or not PKG_NAME_RE.match(cleaned):
        raise PackageError(f"Identifiant de paquet invalide: {pkg_id}")
    return cleaned


def uninstall_package(manager: str, pkg_id: str) -> dict[str, Any]:
    """Uninstall a package using the appropriate manager (privileged when needed)."""
    manager_clean = manager.strip().lower()
    ident = _validate_pkg_id(pkg_id)

    if manager_clean == "apt":
        if shutil.which("apt-get") is None:
            raise PackageError("apt-get introuvable")
        if shutil.which("pkexec") is None:
            raise PackageError("pkexec introuvable")
        cmd = ["pkexec", "apt-get", "remove", "-y", ident]
    elif manager_clean == "dnf":
        if shutil.which("dnf") is None:
            raise PackageError("dnf introuvable")
        if shutil.which("pkexec") is None:
            raise PackageError("pkexec introuvable")
        cmd = ["pkexec", "dnf", "remove", "-y", ident]
    elif manager_clean == "pacman":
        if shutil.which("pacman") is None:
            raise PackageError("pacman introuvable")
        if shutil.which("pkexec") is None:
            raise PackageError("pkexec introuvable")
        cmd = ["pkexec", "pacman", "-R", "--noconfirm", ident]
    elif manager_clean == "flatpak":
        if shutil.which("flatpak") is None:
            raise PackageError("flatpak introuvable")
        cmd = ["flatpak", "uninstall", "-y", ident]
    elif manager_clean == "snap":
        if shutil.which("snap") is None:
            raise PackageError("snap introuvable")
        if shutil.which("pkexec") is None:
            raise PackageError("pkexec introuvable")
        cmd = ["pkexec", "snap", "remove", ident]
    else:
        raise PackageError(f"Gestionnaire inconnu: {manager}")

    try:
        completed = _run(cmd, timeout=600.0)
    except subprocess.TimeoutExpired as exc:
        raise PackageError(f"Délai dépassé lors de la désinstallation de {ident}") from exc
    except OSError as exc:
        raise PackageError(f"Échec d'exécution: {exc}") from exc

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise PackageError(err or f"Désinstallation échouée ({completed.returncode})")

    return {
        "ok": True,
        "manager": manager_clean,
        "id": ident,
        "stdout": completed.stdout.strip(),
    }


def check_updates() -> dict[str, Any]:
    """Return upgradable package counts for available managers."""
    avail = available_managers()
    result: dict[str, Any] = {"apt": [], "dnf": [], "pacman": [], "flatpak": [], "snap": [], "total": 0}
    if avail.get("apt") and shutil.which("apt"):
        try:
            _run(["pkexec", "apt-get", "update"], timeout=300.0)
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            completed = _run(
                ["apt", "list", "--upgradable"],
                timeout=60.0,
            )
            for line in completed.stdout.splitlines()[1:]:
                name = line.split("/", 1)[0].strip()
                if name:
                    result["apt"].append(name)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if avail.get("dnf"):
        try:
            completed = _run(["dnf", "check-update", "-q"], timeout=180.0)
            for line in completed.stdout.splitlines():
                parts = line.split()
                if parts and not parts[0].startswith("Last"):
                    result["dnf"].append(parts[0])
        except (OSError, subprocess.TimeoutExpired):
            pass
    if avail.get("pacman"):
        try:
            _run(["pkexec", "pacman", "-Sy", "--noconfirm"], timeout=300.0)
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            completed = _run(["pacman", "-Qu"], timeout=60.0)
            for line in completed.stdout.splitlines():
                parts = line.split()
                if parts:
                    result["pacman"].append(parts[0])
        except (OSError, subprocess.TimeoutExpired):
            pass
    if avail.get("flatpak"):
        try:
            completed = _run(["flatpak", "remote-ls", "--updates"], timeout=120.0)
            for line in completed.stdout.splitlines():
                parts = line.split("\t")
                if parts and parts[0].strip():
                    result["flatpak"].append(parts[0].strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
    if avail.get("snap"):
        try:
            completed = _run(["snap", "refresh", "--list"], timeout=60.0)
            for line in completed.stdout.splitlines()[1:]:
                parts = line.split()
                if parts:
                    result["snap"].append(parts[0])
        except (OSError, subprocess.TimeoutExpired):
            pass
    result["total"] = len(result["apt"]) + len(result["dnf"]) + len(result["pacman"]) + len(result["flatpak"]) + len(result["snap"])
    return result


def apply_updates() -> dict[str, Any]:
    """Apply available updates (APT via pkexec, Flatpak, Snap)."""
    avail = available_managers()
    logs: list[str] = []
    if avail.get("apt") and shutil.which("apt-get") and shutil.which("pkexec"):
        completed = _run(["pkexec", "apt-get", "upgrade", "-y"], timeout=3600.0)
        logs.append(completed.stdout or completed.stderr or "apt done")
        if completed.returncode != 0:
            raise PackageError((completed.stderr or "apt upgrade a échoué").strip())
    if avail.get("dnf") and shutil.which("pkexec"):
        completed = _run(["pkexec", "dnf", "upgrade", "-y"], timeout=3600.0)
        logs.append(completed.stdout or completed.stderr or "dnf done")
        if completed.returncode != 0:
            raise PackageError((completed.stderr or "dnf upgrade a échoué").strip())
    if avail.get("pacman") and shutil.which("pkexec"):
        completed = _run(["pkexec", "pacman", "-Syu", "--noconfirm"], timeout=3600.0)
        logs.append(completed.stdout or completed.stderr or "pacman done")
        if completed.returncode != 0:
            raise PackageError((completed.stderr or "pacman -Syu a échoué").strip())
    if avail.get("flatpak"):
        completed = _run(["flatpak", "update", "-y"], timeout=3600.0)
        logs.append(completed.stdout or completed.stderr or "flatpak done")
        if completed.returncode not in (0, 1):
            raise PackageError((completed.stderr or "flatpak update a échoué").strip())
    if avail.get("snap") and shutil.which("pkexec"):
        completed = _run(["pkexec", "snap", "refresh"], timeout=3600.0)
        logs.append(completed.stdout or completed.stderr or "snap done")
        if completed.returncode != 0:
            raise PackageError((completed.stderr or "snap refresh a échoué").strip())
    return {"ok": True, "logs": "\n".join(logs)}


def flatpak_permissions(app_id: str) -> dict[str, Any]:
    """Return a summary of flatpak overrides / permissions for an app."""
    ident = _validate_pkg_id(app_id)
    if shutil.which("flatpak") is None:
        raise PackageError("flatpak introuvable")
    completed = _run(["flatpak", "info", "--show-permissions", ident], timeout=30.0)
    if completed.returncode != 0:
        # Fallback: plain info
        completed = _run(["flatpak", "info", ident], timeout=30.0)
    text = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0 and not text:
        raise PackageError(f"Impossible de lire les permissions de {ident}")
    return {"id": ident, "text": text}


def host_manager_labels() -> list[str]:
    """Managers the apply script will actually run (Flatpak-aware ``which``)."""
    labels: list[str] = []
    has_pkexec = bool(host.which("pkexec"))
    if has_pkexec and host.which("pacman"):
        labels.append("pacman")
    if has_pkexec and (host.which("apt-get") or host.which("apt")):
        labels.append("APT")
    if has_pkexec and host.which("dnf"):
        labels.append("DNF")
    if host.which("flatpak"):
        labels.append("Flatpak")
    if has_pkexec and host.which("snap"):
        labels.append("Snap")
    return labels


def pkg_terminal_done_path() -> Path:
    return updater.updates_dir() / "pkg-terminal.done"


def _pkg_lock_preamble() -> str:
    lock_q = updater._shell_quote(str(updater.updates_dir() / "pkg-terminal.lock"))
    done_q = updater._shell_quote(str(pkg_terminal_done_path()))
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -u",
            f"LOCK={lock_q}",
            f"DONE={done_q}",
            'rm -f "$DONE"',
            'exec 9>"$LOCK"',
            "if ! flock -n 9; then",
            '  echo "Déjà une opération paquets en cours. Fermez l’autre terminal."',
            "  exit 0",
            "fi",
            """trap 'touch "$DONE"' EXIT""",
            "",
        ]
    )


def _write_package_script(name: str, body: str) -> Path:
    script = updater.updates_dir() / name
    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    return script


def write_check_updates_script() -> Path:
    """Host terminal script: live check (no capture). ``set -u``, not ``set -e``."""
    body = _pkg_lock_preamble() + r"""echo "=========================================="
echo " Hub Système — vérification paquets"
echo "=========================================="
echo "Sortie live (pkexec peut demander le mot de passe)."
echo

if command -v pacman >/dev/null 2>&1; then
  echo "==> pacman : synchronisation (pkexec pacman -Sy)"
  if command -v pkexec >/dev/null 2>&1; then
    pkexec pacman -Sy --noconfirm || echo "(pacman -Sy a échoué)"
  else
    echo "pkexec introuvable — skip -Sy"
  fi
  echo "==> pacman : paquets à mettre à jour (pacman -Qu)"
  pacman -Qu || echo "(aucun, ou erreur)"
  echo
fi

if command -v apt-get >/dev/null 2>&1; then
  echo "==> APT : apt-get update"
  if command -v pkexec >/dev/null 2>&1; then
    pkexec apt-get update || echo "(apt-get update a échoué)"
  else
    echo "pkexec introuvable — skip apt-get update"
  fi
  echo "==> APT : apt list --upgradable"
  apt list --upgradable 2>/dev/null || true
  echo
fi

if command -v dnf >/dev/null 2>&1; then
  echo "==> DNF : dnf check-update"
  dnf check-update || true
  echo
fi

if command -v flatpak >/dev/null 2>&1; then
  echo "==> Flatpak : remote-ls --updates"
  flatpak remote-ls --updates || echo "(aucun, ou erreur)"
  echo
fi

if command -v snap >/dev/null 2>&1; then
  echo "==> Snap : snap refresh --list"
  snap refresh --list || echo "(aucun, ou erreur)"
  echo
fi

echo "Vérification terminée."
"""
    return _write_package_script("run-pkg-check.sh", body)


def write_apply_updates_script() -> Path:
    """Host terminal script: live upgrade. ``set -u``, not ``set -e``."""
    body = _pkg_lock_preamble() + r"""echo "=========================================="
echo " Hub Système — mise à jour paquets"
echo "=========================================="
echo "Sortie live (pkexec peut demander le mot de passe)."
echo

if command -v pacman >/dev/null 2>&1; then
  echo "==> pacman : pkexec pacman -Syu --noconfirm"
  if command -v pkexec >/dev/null 2>&1; then
    pkexec pacman -Syu --noconfirm || echo "(pacman -Syu a échoué)"
  else
    echo "pkexec introuvable — skip pacman"
  fi
  echo
fi

if command -v apt-get >/dev/null 2>&1; then
  echo "==> APT : pkexec apt-get upgrade -y"
  if command -v pkexec >/dev/null 2>&1; then
    pkexec apt-get upgrade -y || echo "(apt-get upgrade a échoué)"
  else
    echo "pkexec introuvable — skip APT"
  fi
  echo
fi

if command -v dnf >/dev/null 2>&1; then
  echo "==> DNF : pkexec dnf upgrade -y"
  if command -v pkexec >/dev/null 2>&1; then
    pkexec dnf upgrade -y || echo "(dnf upgrade a échoué)"
  else
    echo "pkexec introuvable — skip DNF"
  fi
  echo
fi

if command -v flatpak >/dev/null 2>&1; then
  echo "==> Flatpak : flatpak update -y"
  flatpak update -y || echo "(flatpak update a échoué)"
  echo
fi

if command -v snap >/dev/null 2>&1; then
  echo "==> Snap : pkexec snap refresh"
  if command -v pkexec >/dev/null 2>&1; then
    pkexec snap refresh || echo "(snap refresh a échoué)"
  else
    echo "pkexec introuvable — skip Snap"
  fi
  echo
fi

echo "Mises à jour paquets terminées."
"""
    return _write_package_script("run-pkg-apply.sh", body)


def launch_check_updates_terminal() -> Path:
    script = write_check_updates_script()
    updater.open_terminal_script(script)
    return script


def launch_apply_updates_terminal() -> Path:
    script = write_apply_updates_script()
    updater.open_terminal_script(script)
    return script
