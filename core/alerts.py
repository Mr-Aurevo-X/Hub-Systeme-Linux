# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop alert history and notifications."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

_MAX_HISTORY = 50


def append_history(settings: dict[str, Any], messages: list[str]) -> list[dict[str, Any]]:
    if not messages:
        return list(settings.get("alert_history") or [])
    history = list(settings.get("alert_history") or [])
    history.append({"ts": time.time(), "messages": list(messages)})
    return history[-_MAX_HISTORY:]


def format_history_entries(history: list[Any]) -> list[dict[str, str]]:
    """Normalize persisted alert_history rows for the UI."""
    rows: list[dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        messages = item.get("messages")
        if not isinstance(messages, list):
            continue
        texts = [str(msg).strip() for msg in messages if str(msg).strip()]
        if not texts:
            continue
        when = ""
        raw_ts = item.get("ts")
        try:
            ts = float(raw_ts)
            when = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime(
                "%Y-%m-%d %H:%M"
            )
        except (TypeError, ValueError, OSError):
            when = "—"
        rows.append({"when": when, "body": " · ".join(texts)})
    return rows


def send_desktop_notification(
    app: Any,
    *,
    title: str,
    body: str,
) -> None:
    if app is None:
        return
    try:
        from gi.repository import Gio

        notification = Gio.Notification.new(title)
        notification.set_body(body)
        app.send_notification("hub-systeme-alert", notification)
    except (AttributeError, TypeError, ValueError, ImportError):
        return
