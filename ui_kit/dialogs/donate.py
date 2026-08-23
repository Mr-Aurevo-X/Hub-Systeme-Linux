# SPDX-License-Identifier: GPL-3.0-or-later
"""Donate panel — Discord · Revolut · PayPal."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from ui_kit import chrome_config
from ui_kit.compat import open_external_uri, set_bin_child, toolbar_view
from ui_kit.strings import normalize_language, t


def build_panel(code: str | None = None) -> Gtk.Widget:
    """Reusable donate content (legal tab or standalone dialog)."""
    lang = normalize_language(code or chrome_config.UI_LANGUAGE)
    body = chrome_config.DONATE_MESSAGE.get(lang) or chrome_config.DONATE_MESSAGE["fr"]
    urls = chrome_config.DONATE_URLS

    lbl = Gtk.Label(label=body, wrap=True, xalign=0)
    lbl.set_margin_start(16)
    lbl.set_margin_end(16)
    lbl.set_margin_top(12)

    btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_row.set_margin_start(16)
    btn_row.set_margin_end(16)
    btn_row.set_margin_top(12)
    btn_row.set_margin_bottom(16)
    btn_row.set_halign(Gtk.Align.START)

    pairs = [
        ("discord", t("don_discord", lang), urls.get("discord") or ""),
        ("revolut", t("don_revolut", lang), urls.get("revolut") or ""),
        ("paypal", t("don_paypal", lang), urls.get("paypal") or ""),
    ]
    for _key, label, url in pairs:
        if not url:
            continue
        btn = Gtk.Button(label=label)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda *_u, u=url: open_external_uri(u))
        btn_row.append(btn)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.append(lbl)
    box.append(btn_row)
    return box


def present(parent: Gtk.Window, lang: str | None = None) -> None:
    code = normalize_language(lang or chrome_config.UI_LANGUAGE)

    win = Adw.Window()
    win.set_transient_for(parent)
    win.set_modal(True)
    win.set_title(t("don_title", code))
    win.set_default_size(480, 360)

    header = Adw.HeaderBar()
    header.add_css_class("uni-titlebar")
    close_btn = Gtk.Button(label=t("close", code))
    close_btn.connect("clicked", lambda *_: win.close())
    header.pack_end(close_btn)

    set_bin_child(win, toolbar_view(header, build_panel(code)))
    win.present()
