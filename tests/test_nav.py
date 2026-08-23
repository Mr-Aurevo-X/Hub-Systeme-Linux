# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from ui.nav import flat_nav_items, group_for_page, nav_groups, validate_nav_registry
from ui.pages import PAGE_KEYS


def test_nav_registry_matches_pages() -> None:
    validate_nav_registry()
    flat = [p.key for g in nav_groups() for p in g.pages]
    assert set(flat) == set(PAGE_KEYS)
    assert len(flat) == len(PAGE_KEYS)


def test_flat_nav_unique_keys() -> None:
    keys = [item[0] for item in flat_nav_items()]
    assert len(keys) == len(set(keys))


def test_group_for_known_pages() -> None:
    assert group_for_page("dashboard") == "system"
    assert group_for_page("timers") == "runtime"
    assert group_for_page("fleet") == "network"


def test_flat_nav_starts_with_dashboard_machine() -> None:
    keys = [item[0] for item in flat_nav_items()]
    assert keys[0] == "dashboard"
    assert keys[1] == "machine"
    assert "fleet" in keys
    assert "timers" in keys
