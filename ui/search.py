# SPDX-License-Identifier: GPL-3.0-or-later
"""Global search (Ctrl+K)."""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from core import i18n
from ui.nav import flat_nav_items


def present(win: Any) -> None:
    dialog = Gtk.Dialog(transient_for=win, modal=True, title=i18n.t("search_title"))
    dialog.set_default_size(480, 360)
    content = dialog.get_content_area()
    content.set_margin_top(12)
    content.set_margin_bottom(12)
    content.set_margin_start(12)
    content.set_margin_end(12)
    entry = Gtk.SearchEntry()
    entry.set_hexpand(True)
    content.append(entry)
    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.add_css_class("boxed-list")
    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    scroll.set_min_content_height(240)
    scroll.set_child(listbox)
    content.append(scroll)

    pages = flat_nav_items()

    def refill() -> None:
        while True:
            row = listbox.get_row_at_index(0)
            if row is None:
                break
            listbox.remove(row)
        needle = (entry.get_text() or "").strip().lower()
        for key, label, _icon in pages:
            if needle and needle not in label.lower() and needle not in key.lower():
                continue
            row = Adw.ActionRow()
            row.set_name(key)
            row.set_title(label)
            row.set_subtitle(key)
            listbox.append(row)

    def on_activate(_lb: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        key = row.get_name()
        if key:
            dialog.close()
            win._goto_page(key)

    entry.connect("search-changed", lambda *_: refill())
    listbox.connect("row-activated", on_activate)
    refill()
    dialog.add_button(i18n.t("cancel"), Gtk.ResponseType.CANCEL)
    dialog.present()
