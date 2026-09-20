# SPDX-License-Identifier: GPL-3.0-or-later
"""Donate panel — Discord + crypto (copy addresses)."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from ui_kit import chrome_config
from ui_kit.compat import copy_to_clipboard, open_external_uri, set_bin_child, toolbar_view
from ui_kit.donation_crypto import CRYPTO_WALLETS
from ui_kit.strings import normalize_language, t


def build_panel(code: str | None = None) -> Gtk.Widget:
    """Reusable donate content (legal tab or standalone dialog)."""
    lang = normalize_language(code or chrome_config.UI_LANGUAGE)
    body = chrome_config.DONATE_MESSAGE.get(lang) or chrome_config.DONATE_MESSAGE["fr"]
    discord_url = chrome_config.DONATE_URLS.get("discord") or ""

    lbl = Gtk.Label(label=body, wrap=True, xalign=0)
    lbl.set_margin_start(16)
    lbl.set_margin_end(16)
    lbl.set_margin_top(12)

    btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_row.set_margin_start(16)
    btn_row.set_margin_end(16)
    btn_row.set_margin_top(8)
    btn_row.set_halign(Gtk.Align.START)
    if discord_url:
        discord_btn = Gtk.Button(label=t("don_discord", lang))
        discord_btn.add_css_class("suggested-action")
        discord_btn.connect("clicked", lambda *_u, u=discord_url: open_external_uri(u))
        btn_row.append(discord_btn)

    crypto_title = Gtk.Label(label=t("don_crypto_heading", lang), xalign=0)
    crypto_title.add_css_class("heading")
    crypto_title.set_margin_start(16)
    crypto_title.set_margin_end(16)
    crypto_title.set_margin_top(12)

    crypto_hint = Gtk.Label(label=t("don_crypto_hint", lang), wrap=True, xalign=0)
    crypto_hint.add_css_class("dim-label")
    crypto_hint.set_margin_start(16)
    crypto_hint.set_margin_end(16)
    crypto_hint.set_margin_top(4)

    list_box = Gtk.ListBox()
    list_box.add_css_class("boxed-list")
    list_box.set_selection_mode(Gtk.SelectionMode.NONE)
    for wallet in CRYPTO_WALLETS:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        inner.set_margin_start(10)
        inner.set_margin_end(10)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)
        title = Gtk.Label(label=f"{wallet.symbol} — {wallet.name}", xalign=0, hexpand=True)
        title.set_tooltip_text(wallet.address)
        copy_btn = Gtk.Button(label=t("don_copy", lang))
        copy_btn.connect("clicked", lambda *_a, addr=wallet.address: copy_to_clipboard(addr))
        inner.append(title)
        inner.append(copy_btn)
        row.set_child(inner)
        list_box.append(row)

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_min_content_height(220)
    scroll.set_vexpand(True)
    scroll.set_margin_start(16)
    scroll.set_margin_end(16)
    scroll.set_margin_top(8)
    scroll.set_margin_bottom(16)
    scroll.set_child(list_box)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.append(lbl)
    if discord_url:
        box.append(btn_row)
    box.append(crypto_title)
    box.append(crypto_hint)
    box.append(scroll)
    return box


def present(parent: Gtk.Window, lang: str | None = None) -> None:
    code = normalize_language(lang or chrome_config.UI_LANGUAGE)

    win = Adw.Window()
    win.set_transient_for(parent)
    win.set_modal(True)
    win.set_title(t("don_title", code))
    win.set_default_size(520, 520)

    header = Adw.HeaderBar()
    header.add_css_class("uni-titlebar")
    close_btn = Gtk.Button(label=t("close", code))
    close_btn.connect("clicked", lambda *_: win.close())
    header.pack_end(close_btn)

    set_bin_child(win, toolbar_view(header, build_panel(code)))
    win.present()
