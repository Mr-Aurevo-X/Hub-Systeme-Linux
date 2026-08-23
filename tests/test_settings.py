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
