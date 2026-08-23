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


_PASS1_KEYS = (
    "dash_smart_ok",
    "dash_smart_none",
    "dash_smart_unavailable",
    "process_terminate",
    "process_details",
    "process_empty",
    "process_error",
    "svc_restart",
    "svc_stop",
    "svc_start",
    "svc_state_active",
    "svc_state_inactive",
    "svc_no_description",
    "svc_empty",
    "svc_error",
    "logs_err",
    "logs_warning",
    "logs_info",
    "logs_all",
    "logs_empty",
    "logs_error",
    "logs_status_lines",
    "logs_status_refreshed",
    "logs_status_error",
    "pkg_managers_detected",
    "pkg_managers_none",
    "snapshot_comment",
    "svc_failed",
    "sort_cpu",
    "sort_ram",
    "sort_name",
    "dash_smart_dialog_title",
    "logs_preset_save",
    "logs_preset_name",
    "logs_preset_delete",
    "logs_preset_saved",
)


def test_pkg_user_strings_have_no_gest() -> None:
    previous = i18n.get_language()
    try:
        for lang in ("fr", "en"):
            i18n.set_language(lang)
            for key in (
                "pkg_terminal_opening",
                "pkg_console_opening",
                "pkg_apply_body",
            ):
                text = i18n.t(key, managers="pacman")
                assert "Gest" not in text, f"{lang}:{key} still mentions Gest"
                assert "Hub Système" in text or "Hub Systeme" in text or "Hub" in text
    finally:
        i18n.set_language(previous)


def test_pass1_keys_present_fr_en() -> None:
    previous = i18n.get_language()
    try:
        for key in _PASS1_KEYS:
            i18n.set_language("fr")
            fr = i18n.t(key)
            i18n.set_language("en")
            en = i18n.t(key)
            assert fr != key, f"missing fr key {key}"
            assert en != key, f"missing en key {key}"
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
