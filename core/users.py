# SPDX-License-Identifier: GPL-3.0-or-later
"""Local users and groups (read + limited pkexec actions)."""

from __future__ import annotations

import grp
import pwd
import re
import shutil
import subprocess
from typing import Any

USER_RE = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$")


class UsersError(Exception):
    """Raised when user operations fail."""


def list_users(*, human_only: bool = True) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    for entry in pwd.getpwall():
        if human_only and (entry.pw_uid < 1000 or entry.pw_shell.endswith("nologin") or entry.pw_shell.endswith("false")):
            # Keep uid 1000+ with real shells
            if entry.pw_uid < 1000:
                continue
            if entry.pw_shell.rstrip("/").endswith(("nologin", "false")):
                continue
        users.append(
            {
                "name": entry.pw_name,
                "uid": entry.pw_uid,
                "gid": entry.pw_gid,
                "home": entry.pw_dir,
                "shell": entry.pw_shell,
                "gecos": entry.pw_gecos,
            }
        )
    users.sort(key=lambda u: u["uid"])
    return users


def list_groups() -> list[dict[str, Any]]:
    groups = [
        {"name": g.gr_name, "gid": g.gr_gid, "members": list(g.gr_mem)}
        for g in grp.getgrall()
    ]
    groups.sort(key=lambda g: g["gid"])
    return groups[:300]


def lock_user(username: str, lock: bool = True) -> None:
    if not USER_RE.match(username):
        raise UsersError("Nom d'utilisateur invalide")
    if shutil.which("pkexec") is None:
        raise UsersError("pkexec introuvable")
    action = "--lock" if lock else "--unlock"
    completed = subprocess.run(
        ["pkexec", "usermod", action, username],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise UsersError((completed.stderr or completed.stdout or "échec usermod").strip())
