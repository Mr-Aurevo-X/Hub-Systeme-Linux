# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from ui_kit import chrome_config


def test_hub_systeme_chrome_is_filled() -> None:
    version = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
    assert chrome_config.APP_NAME == "Hub Système"
    assert chrome_config.CONFIG_APP_ID == "hub-systeme"
    assert chrome_config.APP_VERSION == version
