# SPDX-License-Identifier: GPL-3.0-or-later
"""Disk usage page."""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from core import disk_usage, i18n
from ui.adw_compat import set_placeholder_text
from ui.components import run_in_thread, show_toast


def build(win: Any) -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    bar.add_css_class("page-toolbar")
    title = Gtk.Label(label=i18n.t("disk_usage_title"), xalign=0)
    title.add_css_class("heading")
    title.set_hexpand(True)
    win._disk_usage_path = Gtk.Entry()
    win._disk_usage_path.set_text("/")
    set_placeholder_text(win._disk_usage_path, "/")
    win._disk_usage_path.set_hexpand(True)
    win._disk_usage_spinner = Gtk.Spinner()
    win._disk_usage_spinner.set_visible(False)
    scan_btn = Gtk.Button(label=i18n.t("disk_usage_scan"))
    scan_btn.add_css_class("suggested-action")
    scan_btn.connect("clicked", lambda *_: refresh(win, show_spinner=True))
    bar.append(title)
    bar.append(win._disk_usage_path)
    bar.append(win._disk_usage_spinner)
    bar.append(scan_btn)
    root.append(bar)

    win._disk_usage_list = Gtk.ListBox()
    win._disk_usage_list.set_selection_mode(Gtk.SelectionMode.NONE)
    win._disk_usage_list.add_css_class("boxed-list")
    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    clamp = Adw.Clamp(maximum_size=900)
    clamp.set_margin_start(12)
    clamp.set_margin_end(12)
    clamp.set_margin_bottom(16)
    clamp.set_child(win._disk_usage_list)
    scroll.set_child(clamp)
    root.append(scroll)
    return root


def render(win: Any, rows: list[dict[str, Any]]) -> None:
    while True:
        row = win._disk_usage_list.get_row_at_index(0)
        if row is None:
            break
        win._disk_usage_list.remove(row)
    if not rows:
        empty = Adw.ActionRow()
        empty.set_title(i18n.t("disk_usage_empty"))
        empty.set_activatable(False)
        win._disk_usage_list.append(empty)
        return
    for item in rows:
        row = Adw.ActionRow()
        row.set_title(str(item.get("path") or "?"))
        row.set_subtitle(disk_usage.format_bytes(int(item.get("bytes") or 0)))
        win._disk_usage_list.append(row)


def refresh(win: Any, *, show_spinner: bool = False) -> None:
    path = win._disk_usage_path.get_text() or "/"
    if show_spinner:
        win._disk_usage_spinner.set_visible(True)
        win._disk_usage_spinner.start()

    def work() -> list[dict[str, Any]]:
        return disk_usage.scan_top(path)

    def done(data: list[dict[str, Any]] | None, error: BaseException | None) -> None:
        win._disk_usage_spinner.stop()
        win._disk_usage_spinner.set_visible(False)
        if error is not None:
            show_toast(win._toast_overlay, i18n.t("disk_usage_error", detail=str(error)))
            return
        render(win, list(data or []))

    run_in_thread(work, done)
