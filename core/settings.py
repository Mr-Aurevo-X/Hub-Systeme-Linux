# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent settings and alert thresholds."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from core import i18n
from core.paths import config_dir, settings_path

DEFAULTS: dict[str, Any] = {
    "language": "fr",
    "language_chosen": False,
    "alerts_enabled": True,
    "auto_update_on_startup": True,
    "thresholds": {
        "cpu_percent": 90.0,
        "ram_percent": 90.0,
        "temp_celsius": 85.0,
        "disk_percent": 90.0,
    },
    "history_points": 90,
    "alert_cooldown_s": 60,
    "connection_allowlist": [],
    "nav_groups_expanded": {},
    "alert_history": [],
    "log_filter_presets": [],
    "last_page": "dashboard",
}

LOG_PRESET_MAX = 10
LOG_PRESET_NAME_MAX = 40
LOG_PRESET_PRIORITIES = frozenset({"err", "warning", "info", "all"})


class LogPresetError(Exception):
    """Raised when a journal filter preset is rejected."""


THRESHOLD_PROFILES: dict[str, dict[str, float]] = {
    "desktop": {
        "cpu_percent": 90.0,
        "ram_percent": 90.0,
        "temp_celsius": 85.0,
        "disk_percent": 90.0,
    },
    "server": {
        "cpu_percent": 80.0,
        "ram_percent": 85.0,
        "temp_celsius": 80.0,
        "disk_percent": 80.0,
    },
    "vm": {
        "cpu_percent": 95.0,
        "ram_percent": 95.0,
        "temp_celsius": 90.0,
        "disk_percent": 95.0,
    },
}


def _normalize_log_preset(name: str, priority: str, grep: str) -> dict[str, str]:
    cleaned = str(name or "").strip()[:LOG_PRESET_NAME_MAX].strip()
    if not cleaned:
        raise LogPresetError("Nom de preset invalide")
    pri = str(priority or "all").strip()
    if pri not in LOG_PRESET_PRIORITIES:
        pri = "all"
    return {"name": cleaned, "priority": pri, "grep": str(grep or "")}


def add_log_preset(
    settings: dict[str, Any],
    name: str,
    priority: str,
    grep: str,
) -> dict[str, str]:
    item = _normalize_log_preset(name, priority, grep)
    presets = [
        p
        for p in list(settings.get("log_filter_presets") or [])
        if isinstance(p, dict) and p.get("name") != item["name"]
    ]
    if len(presets) >= LOG_PRESET_MAX:
        raise LogPresetError("Maximum 10 presets.")
    presets.append(item)
    settings["log_filter_presets"] = presets
    return item


def lookup_log_preset(settings: dict[str, Any], name: str) -> dict[str, str] | None:
    cleaned = str(name or "").strip()
    for item in settings.get("log_filter_presets") or []:
        if isinstance(item, dict) and item.get("name") == cleaned:
            return {
                "name": str(item.get("name")),
                "priority": str(item.get("priority") or "all"),
                "grep": str(item.get("grep") or ""),
            }
    return None


def remove_log_preset(settings: dict[str, Any], name: str) -> bool:
    cleaned = str(name or "").strip()
    presets = list(settings.get("log_filter_presets") or [])
    kept = [
        item
        for item in presets
        if not (isinstance(item, dict) and item.get("name") == cleaned)
    ]
    settings["log_filter_presets"] = kept
    return len(kept) != len(presets)


def apply_threshold_profile(settings: dict[str, Any], name: str) -> dict[str, Any]:
    """Copy a named profile into ``settings["thresholds"]``. Unknown names are ignored."""
    profile = THRESHOLD_PROFILES.get(name)
    if profile is None:
        return settings
    settings["thresholds"] = dict(profile)
    return settings


def coerce_page(value: object) -> str:
    from ui.pages import PAGE_KEYS

    key = str(value or "dashboard").strip()
    return key if key in PAGE_KEYS else "dashboard"


def coerce_language(value: object) -> str:
    raw = str(value or "fr").strip().lower().replace("_", "-")
    code = raw.split("-", 1)[0]
    return code if code in {"fr", "en"} else "fr"


def needs_language_prompt(settings: dict[str, Any] | None = None) -> bool:
    if settings is None:
        return True
    return not bool(settings.get("language_chosen"))


def load_settings() -> dict[str, Any]:
    path = settings_path()
    data = deepcopy(DEFAULTS)
    raw: dict[str, Any] | None = None
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                raw = parsed
                data.update(
                    {
                        k: v
                        for k, v in parsed.items()
                        if k in DEFAULTS or k in {"thresholds", "nav_groups_expanded", "alert_history", "log_filter_presets"}
                    }
                )
                if isinstance(parsed.get("thresholds"), dict):
                    data["thresholds"] = {**DEFAULTS["thresholds"], **parsed["thresholds"]}
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    data["language"] = coerce_language(data.get("language"))
    if raw is None:
        data["language_chosen"] = False
    else:
        data["language_chosen"] = bool(raw.get("language_chosen", False))
    return data


def save_settings(settings: dict[str, Any]) -> None:
    merged = deepcopy(DEFAULTS)
    merged.update(settings)
    if "thresholds" in settings and isinstance(settings["thresholds"], dict):
        merged["thresholds"] = {**DEFAULTS["thresholds"], **settings["thresholds"]}
    merged["language"] = coerce_language(merged.get("language"))
    merged["language_chosen"] = bool(merged.get("language_chosen"))
    if not isinstance(merged.get("nav_groups_expanded"), dict):
        merged["nav_groups_expanded"] = {}
    if not isinstance(merged.get("alert_history"), list):
        merged["alert_history"] = []
    if not isinstance(merged.get("log_filter_presets"), list):
        merged["log_filter_presets"] = []
    path = settings_path()
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def evaluate_alerts(metrics: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    """Return human-readable alert messages for breached thresholds."""
    if not settings.get("alerts_enabled", True):
        return []
    th = settings.get("thresholds") or DEFAULTS["thresholds"]
    messages: list[str] = []
    cpu = float((metrics.get("cpu") or {}).get("percent_total") or 0)
    ram = float((metrics.get("ram") or {}).get("percent") or 0)
    if cpu >= float(th.get("cpu_percent", 90)):
        messages.append(i18n.t("alert_cpu", value=f"{cpu:.0f}"))
    if ram >= float(th.get("ram_percent", 90)):
        messages.append(i18n.t("alert_ram", value=f"{ram:.0f}"))
    temps = (metrics.get("cpu") or {}).get("temperatures_c") or []
    if temps:
        temp_c = float(temps[0].get("current") or 0)
        if temp_c >= float(th.get("temp_celsius", 85)):
            messages.append(i18n.t("alert_temp", value=f"{temp_c:.0f}"))
    for part in (metrics.get("disks") or {}).get("partitions") or []:
        pct = float(part.get("percent") or 0)
        if pct >= float(th.get("disk_percent", 90)):
            messages.append(i18n.t("alert_disk", mount=part.get("mountpoint"), value=f"{pct:.0f}"))
            break
    return messages
