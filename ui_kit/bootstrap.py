# SPDX-License-Identifier: GPL-3.0-or-later
"""Ensure app root is on sys.path so ``import ui_kit`` works."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_ui_kit_on_path(app_root: Path | None = None) -> Path:
    root = (app_root or Path.cwd()).resolve()
    entry = str(root)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    return root
