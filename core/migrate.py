# SPDX-License-Identifier: GPL-3.0-or-later
"""One-shot migration from legacy config paths."""

from __future__ import annotations

import shutil
from pathlib import Path

from core.paths import config_dir, legacy_config_dirs, settings_path

_MIGRATED_FLAG = ".migrated"


def _copy_legacy_tree(target: Path, sources: list[Path]) -> bool:
    target.mkdir(parents=True, exist_ok=True)
    if (target / "settings.json").is_file():
        return False
    for src_root in sources:
        expanded = src_root.expanduser()
        if not expanded.is_dir():
            continue
        if not (expanded / "settings.json").is_file() and not any(expanded.iterdir()):
            continue
        copied = False
        for item in expanded.iterdir():
            dest = target / item.name
            if dest.exists():
                continue
            try:
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
                copied = True
            except OSError:
                continue
        if copied:
            return True
    return False


def run_first_launch_migration() -> None:
    flag = config_dir() / _MIGRATED_FLAG
    if flag.exists():
        return
    _copy_legacy_tree(config_dir(), legacy_config_dirs())
    flag.touch()
