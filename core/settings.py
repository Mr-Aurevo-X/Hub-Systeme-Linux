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
}


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
