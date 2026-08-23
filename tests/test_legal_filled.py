# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legal_named_and_not_stub() -> None:
    for name in ("cgu.md", "rgpd.md", "licenses.md"):
        text = (ROOT / "ui_kit" / "legal" / name).read_text(encoding="utf-8")
        assert "À compléter après copie" not in text
        assert "Hub Système" in text
        assert "belge" in text.lower() or "Belgique" in text
