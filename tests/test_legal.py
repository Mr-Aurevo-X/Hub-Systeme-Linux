# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from core import legal


def test_copyright_line() -> None:
    assert "Mr-Aurevo-X" in legal.copyright_line()
    assert "2026" in legal.copyright_line()
    assert legal.copyright_line().startswith("©")


def test_legal_markdown_fr_en() -> None:
    fr = legal.legal_markdown("fr")
    en = legal.legal_markdown("en")
    assert "Copyright © 2026 Mr-Aurevo-X" in fr
    assert "RGPD" in fr
    assert "Conditions d’utilisation" in fr or "Conditions d'utilisation" in fr
    assert "Copyright © 2026 Mr-Aurevo-X" in en
    assert "GDPR" in en
    assert "Terms of use" in en
    assert "<!-- lang:" not in fr
    assert "<!-- lang:" not in en
    assert "ss" in fr
    assert "ss" in en
