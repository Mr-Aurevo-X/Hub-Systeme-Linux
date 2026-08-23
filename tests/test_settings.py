# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from copy import deepcopy

from core import settings as app_settings


def test_apply_threshold_profile_server_sets_disk_percent() -> None:
    settings = {"thresholds": {"disk_percent": 90.0}}
    result = app_settings.apply_threshold_profile(settings, "server")
    assert result["thresholds"]["disk_percent"] == 80.0


def test_apply_threshold_profile_unknown_name_ignored() -> None:
    settings = {"thresholds": {"disk_percent": 90.0, "cpu_percent": 90.0}}
    before = deepcopy(settings)
    result = app_settings.apply_threshold_profile(settings, "laptop")
    assert result["thresholds"] == before["thresholds"]


def test_apply_threshold_profile_copies_desktop_values() -> None:
    settings: dict = {}
    result = app_settings.apply_threshold_profile(settings, "desktop")
    assert result["thresholds"] == app_settings.THRESHOLD_PROFILES["desktop"]
    result["thresholds"]["cpu_percent"] = 1.0
    assert app_settings.THRESHOLD_PROFILES["desktop"]["cpu_percent"] == 90.0


def test_add_log_preset_validates_and_caps() -> None:
    settings: dict = {"log_filter_presets": []}
    added = app_settings.add_log_preset(settings, "  Errors  ", "err", "kernel")
    assert added == {"name": "Errors", "priority": "err", "grep": "kernel"}
    assert settings["log_filter_presets"] == [added]
    for idx in range(9):
        app_settings.add_log_preset(settings, f"p{idx}", "all", "")
    assert len(settings["log_filter_presets"]) == 10
    try:
        app_settings.add_log_preset(settings, "overflow", "all", "")
        raise AssertionError("expected LogPresetError")
    except app_settings.LogPresetError:
        pass
    try:
        app_settings.add_log_preset({"log_filter_presets": []}, "   ", "all", "")
        raise AssertionError("expected LogPresetError")
    except app_settings.LogPresetError:
        pass


def test_remove_and_lookup_log_preset() -> None:
    settings: dict = {"log_filter_presets": []}
    app_settings.add_log_preset(settings, "warns", "warning", "usb")
    assert app_settings.lookup_log_preset(settings, "warns") == {
        "name": "warns",
        "priority": "warning",
        "grep": "usb",
    }
    assert app_settings.remove_log_preset(settings, "warns") is True
    assert settings["log_filter_presets"] == []
    assert app_settings.remove_log_preset(settings, "warns") is False
    assert app_settings.lookup_log_preset(settings, "warns") is None
