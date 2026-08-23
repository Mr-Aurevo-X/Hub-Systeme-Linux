#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the GTK window then quit. Needs a display (xvfb-run on CI)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import HubSystemeApp  # noqa: E402
from gi.repository import GLib  # noqa: E402


def main() -> int:
    app = HubSystemeApp()

    def stop() -> bool:
        app.quit()
        return False

    GLib.timeout_add(500, stop)
    return int(app.run([]))


if __name__ == "__main__":
    raise SystemExit(main())
