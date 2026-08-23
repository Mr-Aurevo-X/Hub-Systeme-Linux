# SPDX-License-Identifier: GPL-3.0-or-later
"""systemd timers page."""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from core import i18n, timers
from ui.adw_compat import make_message_dialog, set_placeholder_text
from ui.components import confirm_dialog, run_in_thread, show_toast


def build(win: Any) -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    bar.add_css_class("page-toolbar")
    title = Gtk.Label(label=i18n.t("timers_title"), xalign=0)
    title.add_css_class("heading")
    title.set_hexpand(True)
    win._timers_spinner = Gtk.Spinner()
    win._timers_spinner.set_visible(False)
    win._timers_search = Gtk.SearchEntry()
    win._timers_search.set_hexpand(True)
    set_placeholder_text(win._timers_search, i18n.t("filter_timers"))
    win._timers_search.connect("search-changed", lambda *_: render(win))
    refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
    refresh_btn.connect("clicked", lambda *_: refresh(win, show_spinner=True))
    bar.append(title)
    bar.append(win._timers_search)
    bar.append(win._timers_spinner)
    bar.append(refresh_btn)
    root.append(bar)

    win._timers_list = Gtk.ListBox()
    win._timers_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    win._timers_list.add_css_class("boxed-list")
    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    clamp = Adw.Clamp(maximum_size=1000)
    clamp.set_margin_start(12)
    clamp.set_margin_end(12)
    clamp.set_margin_bottom(16)
    clamp.set_child(win._timers_list)
    scroll.set_child(clamp)
    root.append(scroll)
    win._timers_cache: list[dict[str, Any]] = []
    return root


def render(win: Any) -> None:
    while True:
        row = win._timers_list.get_row_at_index(0)
        if row is None:
            break
        win._timers_list.remove(row)
    needle = (win._timers_search.get_text() or "").strip().lower()
    items = list(win._timers_cache or [])
    if needle:
        items = [item for item in items if needle in str(item.get("unit") or "").lower()]
    if not items:
        empty = Adw.ActionRow()
        empty.set_title(i18n.t("timers_empty"))
        empty.set_activatable(False)
        win._timers_list.append(empty)
        return
    for item in items:
        unit = str(item.get("unit") or "?")
        row = Adw.ActionRow()
        row.set_name(unit)
        row.set_title(unit)
        row.set_subtitle(
            f"{i18n.t('timers_next')}: {item.get('next') or '—'} · "
            f"{i18n.t('timers_last')}: {item.get('last') or '—'} · "
            f"{item.get('enabled') or '—'}"
        )
        enabled = str(item.get("enabled") or "").lower() == "enabled"
        start_btn = Gtk.Button(label=i18n.t("timers_start"))
        start_btn.set_valign(Gtk.Align.CENTER)
        start_btn.connect("clicked", lambda *_a, u=unit: _control(win, u, "start"))
        stop_btn = Gtk.Button(label=i18n.t("timers_stop"))
        stop_btn.set_valign(Gtk.Align.CENTER)
        stop_btn.connect("clicked", lambda *_a, u=unit: _control(win, u, "stop"))
        toggle = Gtk.Button(
            label=i18n.t("timers_disable") if enabled else i18n.t("timers_enable")
        )
        toggle.set_valign(Gtk.Align.CENTER)
        toggle.connect("clicked", lambda *_a, u=unit, en=enabled: _toggle(win, u, en))
        row.add_suffix(start_btn)
        row.add_suffix(stop_btn)
        row.add_suffix(toggle)
        win._timers_list.append(row)


def refresh(win: Any, *, show_spinner: bool = False) -> None:
    if show_spinner and hasattr(win, "_timers_spinner"):
        win._timers_spinner.set_visible(True)

    def work() -> list[dict[str, Any]]:
        return timers.list_timers()

    def done(data: list[dict[str, Any]] | None, error: BaseException | None) -> None:
        if hasattr(win, "_timers_spinner"):
            win._timers_spinner.set_visible(False)
        if error is not None:
            show_toast(win._toast_overlay, i18n.t("timers_error", detail=str(error)))
            return
        win._timers_cache = list(data or [])
        render(win)

    run_in_thread(work, done)


def _control(win: Any, unit: str, action: str) -> None:
    labels = {
        "start": i18n.t("timers_start"),
        "stop": i18n.t("timers_stop"),
        "enable": i18n.t("timers_enable"),
        "disable": i18n.t("timers_disable"),
    }
    label = labels.get(action, action)

    def on_confirm() -> None:
        def work() -> None:
            timers.control_timer(unit, action)

        def done(_ok: object, error: BaseException | None) -> None:
            if error is not None:
                show_toast(win._toast_overlay, i18n.t("timers_error", detail=str(error)))
                return
            refresh(win, show_spinner=True)

        run_in_thread(work, done)

    confirm_dialog(
        win,
        label,
        unit,
        destructive=action in {"stop", "disable"},
        on_confirm=on_confirm,
    )


def _toggle(win: Any, unit: str, currently_enabled: bool) -> None:
    _control(win, unit, "disable" if currently_enabled else "enable")
