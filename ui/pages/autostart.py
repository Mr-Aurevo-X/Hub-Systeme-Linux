# SPDX-License-Identifier: GPL-3.0-or-later
"""Autostart page."""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from core import autostart, i18n
from ui.components import make_spinner, run_in_thread, show_toast


def build(win: Any) -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    bar.add_css_class("page-toolbar")
    title = Gtk.Label(label=i18n.t("autostart_title"), xalign=0)
    title.add_css_class("heading")
    title.set_hexpand(True)
    win._autostart_spinner = make_spinner(size=18)
    win._autostart_spinner.set_visible(False)
    refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
    refresh_btn.connect("clicked", lambda *_: refresh(win, show_spinner=True))
    bar.append(title)
    bar.append(win._autostart_spinner)
    bar.append(refresh_btn)
    root.append(bar)

    win._autostart_scrolled = Gtk.ScrolledWindow()
    win._autostart_scrolled.set_vexpand(True)
    win._autostart_list = Gtk.ListBox()
    win._autostart_list.set_selection_mode(Gtk.SelectionMode.NONE)
    win._autostart_list.add_css_class("boxed-list")
    win._autostart_scrolled.set_child(win._autostart_list)
    clamp = Adw.Clamp(maximum_size=1000)
    clamp.set_margin_start(12)
    clamp.set_margin_end(12)
    clamp.set_margin_bottom(12)
    clamp.set_child(win._autostart_scrolled)
    root.append(clamp)
    return root


def refresh(win: Any, *, show_spinner: bool = False) -> None:
    if show_spinner:
        win._autostart_spinner.set_visible(True)

    def work() -> list[dict[str, Any]]:
        return autostart.list_all()

    def done(result: Any, error: BaseException | None) -> None:
        win._autostart_spinner.set_visible(False)
        if error is not None:
            show_toast(win._toast_overlay, i18n.t("autostart_error", detail=str(error)))
            return
        win._clear_listbox(win._autostart_list)
        for item in result or []:
            kind = item.get("kind")
            title = str(item.get("name") or item.get("id"))
            desc = str(item.get("description") or "")
            kind_lbl = (
                i18n.t("autostart_kind_desktop")
                if kind == "desktop"
                else i18n.t("autostart_kind_user")
            )
            row = Adw.ActionRow()
            row.set_title(title)
            row.set_subtitle(f"{kind_lbl} · {desc}".strip(" ·"))
            switch = Gtk.Switch()
            switch.set_valign(Gtk.Align.CENTER)
            guard = {"block": True}

            def on_toggle(
                sw: Gtk.Switch,
                _p: object,
                it: dict[str, Any] = item,
                g: dict[str, bool] = guard,
            ) -> None:
                if g["block"]:
                    return
                _toggle(win, it, sw.get_active())

            switch.connect("notify::active", on_toggle)
            switch.set_active(bool(item.get("enabled")))
            guard["block"] = False
            row.add_suffix(switch)
            win._autostart_list.append(row)

    run_in_thread(work, done)


def _toggle(win: Any, item: dict[str, Any], enabled: bool) -> None:
    kind = item.get("kind")
    ident = str(item.get("id") or "")
    win._set_busy(True)

    def work() -> None:
        if kind == "desktop":
            autostart.set_desktop_enabled(ident, enabled)
        else:
            autostart.toggle_user_service(ident, enabled)

    def done(_result: Any, error: BaseException | None) -> None:
        win._set_busy(False)
        if error is not None:
            show_toast(win._toast_overlay, str(error))
            refresh(win)
            return
        key = "autostart_enabled" if enabled else "autostart_disabled"
        show_toast(win._toast_overlay, i18n.t(key, id=ident))

    run_in_thread(work, done)
