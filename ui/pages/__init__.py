# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Callable
from typing import Any

PAGE_KEYS: tuple[str, ...] = (
    "dashboard",
    "machine",
    "processes",
    "services",
    "cleaner",
    "disk_usage",
    "packages",
    "logs",
    "autostart",
    "timers",
    "tools",
    "backup",
    "sessions",
)

_BUILD_ATTR = {
    "dashboard": "_build_dashboard",
    "machine": "_build_machine",
    "processes": "_build_processes",
    "services": "_build_services_page",
    "cleaner": "_build_cleaner_page",
    "disk_usage": "_build_disk_usage_page",
    "packages": "_build_packages_page",
    "logs": "_build_logs_page",
    "autostart": "_build_autostart_page",
    "timers": "_build_timers_page",
    "tools": "_build_tools_page",
    "backup": "_build_backup_page",
    "sessions": "_build_sessions_page",
}


def builders_for(win: Any) -> dict[str, Callable[[], Any]]:
    out: dict[str, Callable[[], Any]] = {}
    for key, attr in _BUILD_ATTR.items():
        out[key] = getattr(win, attr)
    return out
