# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from core import services


def _unit(name: str, *, active: str = "inactive", enabled: str = "disabled", desc: str = "") -> dict:
    return {
        "name": f"{name}.service",
        "short_name": name,
        "active": active,
        "is_active": active == "active",
        "enabled": enabled,
        "is_enabled": enabled == "enabled",
        "description": desc,
    }


def test_filter_services_failed_chip() -> None:
    items = [
        _unit("ok", active="active", enabled="enabled", desc="web"),
        _unit("boom", active="failed", desc="crash"),
        _unit("idle"),
    ]
    failed = services.filter_services(items, chip="failed", needle="")
    assert [item["short_name"] for item in failed] == ["boom"]
    active = services.filter_services(items, chip="active", needle="")
    assert [item["short_name"] for item in active] == ["ok"]
    searched = services.filter_services(items, chip="all", needle="crash")
    assert [item["short_name"] for item in searched] == ["boom"]
