# SPDX-License-Identifier: GPL-3.0-or-later
"""CPU frequency governor / power profile helpers."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ALLOWED_GOVERNORS = frozenset(
    {"performance", "powersave", "schedutil", "ondemand", "conservative", "userspace"}
)


class PowerError(Exception):
    """Raised when power profile changes fail."""


def list_governors() -> dict[str, Any]:
    paths = sorted(glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"))
    current = None
    available: list[str] = []
    if paths:
        try:
            current = Path(paths[0]).read_text(encoding="utf-8").strip()
        except OSError:
            current = None
        avail_path = Path(paths[0]).with_name("scaling_available_governors")
        try:
            if avail_path.exists():
                available = avail_path.read_text(encoding="utf-8").split()
        except OSError:
            available = []
    # powerprofilesctl if present
    profile = None
    profiles: list[str] = []
    if shutil.which("powerprofilesctl"):
        try:
            out = subprocess.run(
                ["powerprofilesctl", "get"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            profile = (out.stdout or "").strip() or None
            lst = subprocess.run(
                ["powerprofilesctl", "list"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in (lst.stdout or "").splitlines():
                line = line.strip()
                if line.startswith("*") or line.endswith(":"):
                    name = line.lstrip("* ").rstrip(":")
                    if name:
                        profiles.append(name)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {
        "governor": current,
        "available_governors": available,
        "cpu_paths": len(paths),
        "power_profile": profile,
        "power_profiles": profiles,
    }


def set_governor(name: str) -> None:
    clean = name.strip().lower()
    if clean not in ALLOWED_GOVERNORS:
        raise PowerError(f"Governor invalide: {name}")
    if shutil.which("pkexec") is None:
        raise PowerError("pkexec introuvable")
    # Validated whitelist value only — argv pkexec + python3 (no bash -c).
    code = (
        "import pathlib,glob\n"
        f"g={clean!r}\n"
        "for p in glob.glob('/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor'):\n"
        "    pathlib.Path(p).write_text(g+'\\n')\n"
    )
    completed = subprocess.run(
        ["pkexec", "python3", "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise PowerError((completed.stderr or completed.stdout or "échec governor").strip())


def set_power_profile(name: str) -> None:
    clean = re_sub_profile(name)
    if shutil.which("powerprofilesctl") is None:
        raise PowerError("powerprofilesctl introuvable")
    completed = subprocess.run(
        ["powerprofilesctl", "set", clean],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise PowerError((completed.stderr or completed.stdout or "échec profil").strip())


def re_sub_profile(name: str) -> str:
    import re

    clean = name.strip().lower()
    if not re.match(r"^[a-z0-9_-]+$", clean):
        raise PowerError("Profil invalide")
    return clean
