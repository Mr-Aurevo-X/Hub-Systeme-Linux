# SPDX-License-Identifier: GPL-3.0-or-later
"""Disk cleanup for APT caches, logs, browser caches and ~/.cache."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

_BYTES_PER_MIB = 1024**2


class CleanerError(Exception):
    """Raised when a cleanup operation fails."""


def _home() -> Path:
    return Path(os.path.expanduser("~")).resolve()


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    try:
        for root, _dirs, files in os.walk(path, followlinks=False):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def _human_mib(size_bytes: int) -> float:
    return round(size_bytes / _BYTES_PER_MIB, 2)


def _browser_cache_paths() -> list[tuple[str, Path]]:
    home = _home()
    candidates: list[tuple[str, Path]] = [
        ("Firefox cache", home / ".cache" / "mozilla"),
        ("Chrome cache", home / ".cache" / "google-chrome"),
        ("Chromium cache", home / ".cache" / "chromium"),
        ("Brave cache", home / ".cache" / "BraveSoftware"),
    ]
    # Firefox profile caches under ~/.mozilla
    mozilla = home / ".mozilla" / "firefox"
    if mozilla.is_dir():
        for profile in mozilla.iterdir():
            if not profile.is_dir():
                continue
            cache2 = profile / "cache2"
            if cache2.exists():
                candidates.append((f"Firefox profile {profile.name}", cache2))
    return [(label, path) for label, path in candidates if path.exists()]


TARGET_DEFS: dict[str, dict[str, Any]] = {
    "apt_cache": {
        "label": "Cache APT",
        "paths": [Path("/var/cache/apt/archives")],
        "requires_root": True,
        "method": "apt_clean",
    },
    "logs": {
        "label": "Journaux /var/log + vacuum journal",
        "paths": [Path("/var/log")],
        "requires_root": True,
        "method": "trim_logs",
    },
    "journal_vacuum": {
        "label": "Vacuum journald (7 jours)",
        "paths": [Path("/var/log/journal")],
        "requires_root": True,
        "method": "journal_vacuum",
    },
    "user_cache": {
        "label": "Cache utilisateur (~/.cache)",
        "paths": [],  # filled dynamically
        "requires_root": False,
        "method": "rm_tree_contents",
    },
    "thumbnails": {
        "label": "Miniatures (~/.cache/thumbnails)",
        "paths": [],
        "requires_root": False,
        "method": "rm_tree_contents_thumbnails",
    },
    "user_tmp": {
        "label": "Fichiers temporaires utilisateur (/tmp)",
        "paths": [Path("/tmp")],
        "requires_root": False,
        "method": "rm_user_tmp_files",
    },
    "browser_caches": {
        "label": "Caches navigateurs",
        "paths": [],
        "requires_root": False,
        "method": "rm_trees",
    },
}


def _whitelist_paths() -> dict[str, list[Path]]:
    home = _home()
    user_cache = home / ".cache"
    thumbnails = user_cache / "thumbnails"
    browsers = [path for _label, path in _browser_cache_paths()]
    journal = Path("/var/log/journal")
    return {
        "apt_cache": [Path("/var/cache/apt/archives")],
        "logs": [Path("/var/log")],
        "journal_vacuum": [journal] if journal.exists() else [Path("/var/log")],
        "user_cache": [user_cache] if user_cache.exists() else [],
        "thumbnails": [thumbnails] if thumbnails.exists() else [],
        "user_tmp": [Path("/tmp")],
        "browser_caches": browsers,
    }


def _user_tmp_size(tmp_root: Path) -> int:
    if not tmp_root.is_dir():
        return 0
    uid = os.getuid()
    total = 0
    try:
        for child in tmp_root.iterdir():
            try:
                if child.is_symlink() or not child.is_file():
                    continue
                st = child.stat()
                if st.st_uid == uid:
                    total += st.st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


def scan() -> list[dict[str, Any]]:
    """Analyze reclaimable space for known cleanup targets."""
    paths_map = _whitelist_paths()
    results: list[dict[str, Any]] = []
    for key, meta in TARGET_DEFS.items():
        paths = paths_map.get(key, [])
        if key == "user_tmp":
            size = sum(_user_tmp_size(p) for p in paths)
        else:
            size = sum(_dir_size(p) for p in paths)
        results.append(
            {
                "id": key,
                "label": meta["label"],
                "paths": [str(p) for p in paths],
                "size_bytes": size,
                "size_mib": _human_mib(size),
                "requires_root": bool(meta["requires_root"]),
                "exists": any(p.exists() for p in paths) if paths else False,
            }
        )
    return results


def _run_pkexec(args: list[str], *, timeout: float = 300.0) -> None:
    if shutil.which("pkexec") is None:
        raise CleanerError("pkexec introuvable (installez policykit)")
    try:
        completed = subprocess.run(
            ["pkexec", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CleanerError("Délai dépassé lors du nettoyage privilégié") from exc
    except OSError as exc:
        raise CleanerError(f"Échec pkexec: {exc}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise CleanerError(err or f"Commande privilégiée échouée ({completed.returncode})")


def _rm_tree_contents(path: Path) -> int:
    """Delete contents of a directory; return bytes roughly freed (pre-scan)."""
    if not path.is_dir():
        return 0
    freed = 0
    for child in list(path.iterdir()):
        try:
            size = _dir_size(child)
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=False)
            else:
                child.unlink(missing_ok=True)
            freed += size
        except OSError:
            continue
    return freed


def _is_under_whitelist(path: Path, allowed: list[Path]) -> bool:
    resolved = path.resolve()
    for base in allowed:
        try:
            resolved.relative_to(base.resolve())
            return True
        except ValueError:
            continue
        except OSError:
            continue
    return False


def _rm_user_tmp_files(tmp_root: Path) -> int:
    """Delete regular files in /tmp owned by the current user (top-level only).

    Directories, sockets, and foreign-owned files are left untouched.
    """
    if not tmp_root.is_dir():
        return 0
    uid = os.getuid()
    freed = 0
    try:
        children = list(tmp_root.iterdir())
    except OSError:
        return 0
    for child in children:
        try:
            if child.is_symlink() or not child.is_file():
                continue
            st = child.stat()
            if st.st_uid != uid:
                continue
            size = st.st_size
            child.unlink(missing_ok=True)
            freed += size
        except OSError:
            continue
    return freed


def clean(targets: list[str]) -> dict[str, Any]:
    """Clean selected whitelist targets. Never accepts arbitrary paths."""
    known = set(TARGET_DEFS)
    selected = [t for t in targets if t in known]
    if not selected:
        raise CleanerError("Aucune cible de nettoyage valide")

    paths_map = _whitelist_paths()
    details: list[dict[str, Any]] = []
    total_freed = 0

    for target_id in selected:
        meta = TARGET_DEFS[target_id]
        allowed = paths_map.get(target_id, [])
        if target_id == "user_tmp":
            before = sum(_user_tmp_size(p) for p in allowed)
        else:
            before = sum(_dir_size(p) for p in allowed)
        method = meta["method"]

        if method == "apt_clean":
            _run_pkexec(["apt-get", "clean"])
        elif method == "trim_logs":
            # Prefer argv-only vacuum; rotated logs via find in a short python helper.
            _run_pkexec(["journalctl", "--vacuum-time=7d"])
            py = (
                "import pathlib\n"
                "root=pathlib.Path('/var/log')\n"
                "for p in root.rglob('*'):\n"
                "  if not p.is_file():\n"
                "    continue\n"
                "  n=p.name\n"
                "  if n.endswith(('.gz','.xz','.old')) or n.endswith(tuple('.'+str(i) for i in range(1,8))):\n"
                "    try: p.unlink()\n"
                "    except OSError: pass\n"
            )
            _run_pkexec(["python3", "-c", py])
        elif method == "journal_vacuum":
            _run_pkexec(["journalctl", "--vacuum-time=7d"])
        elif method == "rm_tree_contents":
            for path in allowed:
                if not _is_under_whitelist(path, [_home() / ".cache"]):
                    raise CleanerError(f"Chemin hors liste blanche: {path}")
                total_freed += _rm_tree_contents(path)
        elif method == "rm_tree_contents_thumbnails":
            thumb_root = _home() / ".cache" / "thumbnails"
            for path in allowed:
                if not _is_under_whitelist(path, [thumb_root]):
                    raise CleanerError(f"Chemin hors liste blanche: {path}")
                total_freed += _rm_tree_contents(path)
        elif method == "rm_user_tmp_files":
            for path in allowed:
                if path.resolve() != Path("/tmp").resolve():
                    raise CleanerError(f"Chemin hors liste blanche: {path}")
                total_freed += _rm_user_tmp_files(path)
        elif method == "rm_trees":
            home = _home()
            browser_roots = [
                home / ".cache" / "mozilla",
                home / ".cache" / "google-chrome",
                home / ".cache" / "chromium",
                home / ".cache" / "BraveSoftware",
                home / ".mozilla" / "firefox",
            ]
            for path in allowed:
                if not _is_under_whitelist(path, browser_roots):
                    raise CleanerError(f"Chemin hors liste blanche: {path}")
                try:
                    size = _dir_size(path)
                    if path.is_dir():
                        shutil.rmtree(path, ignore_errors=False)
                    elif path.is_file():
                        path.unlink()
                    total_freed += size
                except OSError as exc:
                    raise CleanerError(f"Échec suppression {path}: {exc}") from exc
        else:
            raise CleanerError(f"Méthode inconnue: {method}")

        after_paths = paths_map.get(target_id, [])
        if target_id == "user_tmp":
            after = sum(_user_tmp_size(p) for p in after_paths)
        else:
            after = sum(_dir_size(p) for p in after_paths)
        freed = max(before - after, 0)
        if method in {"apt_clean", "trim_logs", "journal_vacuum"}:
            total_freed += freed
        details.append(
            {
                "id": target_id,
                "label": meta["label"],
                "freed_bytes": freed,
                "freed_mib": _human_mib(freed),
            }
        )

    return {
        "ok": True,
        "targets": selected,
        "freed_bytes": total_freed,
        "freed_mib": _human_mib(total_freed),
        "details": details,
    }
