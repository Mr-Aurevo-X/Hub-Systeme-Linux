# SPDX-License-Identifier: GPL-3.0-or-later
"""Sessions page."""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from core import i18n, sessions
from ui.components import run_in_thread, show_toast


def build(win: Any) -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    bar.add_css_class("page-toolbar")
    title = Gtk.Label(label=i18n.t("sessions_title"), xalign=0)
    title.add_css_class("heading")
    title.set_hexpand(True)
    win._sessions_spinner = Gtk.Spinner()
    win._sessions_spinner.set_visible(False)
    refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
    refresh_btn.connect("clicked", lambda *_: refresh(win, show_spinner=True))
    bar.append(title)
    bar.append(win._sessions_spinner)
    bar.append(refresh_btn)
    root.append(bar)

    win._sessions_list = Gtk.ListBox()
    win._sessions_list.set_selection_mode(Gtk.SelectionMode.NONE)
    win._sessions_list.add_css_class("boxed-list")
    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    clamp = Adw.Clamp(maximum_size=900)
    clamp.set_margin_start(12)
    clamp.set_margin_end(12)
    clamp.set_margin_bottom(16)
    clamp.set_child(win._sessions_list)
    scroll.set_child(clamp)
    root.append(scroll)
    return root


def render(win: Any, items: list[dict[str, Any]]) -> None:
    while True:
        row = win._sessions_list.get_row_at_index(0)
        if row is None:
            break
        win._sessions_list.remove(row)
    if not items:
        empty = Adw.ActionRow()
        empty.set_title(i18n.t("sessions_empty"))
        empty.set_activatable(False)
        win._sessions_list.append(empty)
        return
    for item in items:
        row = Adw.ActionRow()
        row.set_title(str(item.get("user") or "?"))
        row.set_subtitle(
            f"{item.get('session') or '—'} · {item.get('seat') or '—'} · {item.get('state') or '—'}"
        )
        win._sessions_list.append(row)


def refresh(win: Any, *, show_spinner: bool = False) -> None:
    if show_spinner:
        win._sessions_spinner.set_visible(True)
        win._sessions_spinner.start()

    def work() -> list[dict[str, Any]]:
        return sessions.list_sessions()

    def done(data: list[dict[str, Any]] | None, error: BaseException | None) -> None:
        win._sessions_spinner.stop()
        win._sessions_spinner.set_visible(False)
        if error is not None:
            show_toast(win._toast_overlay, i18n.t("sessions_error", detail=str(error)))
            return
        render(win, list(data or []))

    run_in_thread(work, done)
