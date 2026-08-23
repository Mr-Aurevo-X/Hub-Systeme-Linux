# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from core import i18n
from core import settings as app_settings
from core.paths import settings_path


def test_normalize_and_coerce_language() -> None:
    assert i18n.normalize_language("en-US") == "en"
    assert i18n.normalize_language("FR") == "fr"
    assert i18n.normalize_language("de") == "fr"
    assert app_settings.coerce_language("EN") == "en"
    assert app_settings.coerce_language("nope") == "fr"


def test_set_language_accepts_en_variants() -> None:
    previous = i18n.get_language()
    try:
        i18n.set_language("EN")
        assert i18n.get_language() == "en"
        assert i18n.t("dashboard") == "Dashboard"
        i18n.set_language("de")
        assert i18n.get_language() == "fr"
    finally:
        i18n.set_language(previous)


def test_language_prompt_first_run_and_legacy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    fresh = app_settings.load_settings()
    assert fresh["language_chosen"] is False
    assert app_settings.needs_language_prompt(fresh) is True
    fresh["language"] = "en"
    fresh["language_chosen"] = True
    app_settings.save_settings(fresh)
    again = app_settings.load_settings()
    assert again["language"] == "en"
    assert again["language_chosen"] is True
    assert app_settings.needs_language_prompt(again) is False
    path = settings_path()
    path.write_text('{"language": "fr", "alerts_enabled": true}\n', encoding="utf-8")
    old = app_settings.load_settings()
    assert old["language_chosen"] is False
    assert app_settings.needs_language_prompt(old) is True


def test_nav_includes_dashboard_machine_logs() -> None:
    previous = i18n.get_language()
    try:
        i18n.set_language("fr")
        keys = [item[0] for item in i18n.nav_items()]
        assert keys[:2] == ["dashboard", "machine"]
        assert "logs" in keys
        assert "timers" in keys
        assert "fleet" not in keys
        assert i18n.t("machine") == "Fiche"
        i18n.set_language("en")
        assert i18n.t("machine") == "Machine"
    finally:
        i18n.set_language(previous)


def test_threshold_profile_labels_bilingual() -> None:
    previous = i18n.get_language()
    try:
        i18n.set_language("fr")
        assert i18n.t("threshold_profile_desktop") == "Bureau"
        assert i18n.t("threshold_profile_server") == "Serveur"
        assert i18n.t("threshold_profile_vm") == "VM"
        i18n.set_language("en")
        assert i18n.t("threshold_profile_desktop") == "Desktop"
        assert i18n.t("threshold_profile_server") == "Server"
        assert i18n.t("threshold_profile_vm") == "VM"
    finally:
        i18n.set_language(previous)


def test_welcome_keys_bilingual() -> None:
    previous = i18n.get_language()
    try:
        i18n.set_language("fr")
        assert "Language" in i18n.t("welcome_lang")
        assert "Choose" in i18n.t("welcome_lang_body")
        i18n.set_language("en")
        assert "Language" in i18n.t("welcome_lang")
        assert "Choose" in i18n.t("welcome_lang_body")
    finally:
        i18n.set_language(previous)
