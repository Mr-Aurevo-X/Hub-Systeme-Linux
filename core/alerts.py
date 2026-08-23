# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop alert history and notifications."""

from __future__ import annotations

import time
from typing import Any

_MAX_HISTORY = 50


def append_history(settings: dict[str, Any], messages: list[str]) -> list[dict[str, Any]]:
    if not messages:
        return list(settings.get("alert_history") or [])
    history = list(settings.get("alert_history") or [])
    history.append({"ts": time.time(), "messages": list(messages)})
    return history[-_MAX_HISTORY:]


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
