# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable page chrome: filter chips, clamped lists, threaded refresh."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from ui.adw_compat import set_placeholder_text
from ui.components import make_spinner, run_in_thread, show_toast


def make_filter_chips(
    items: list[tuple[str, str]],
    *,
    active_key: str,
    on_change: Callable[[str], None],
) -> tuple[Gtk.Box, dict[str, Gtk.ToggleButton]]:
    """Linked toggle chips. ``items`` = (key, label). Calls ``on_change(key)``."""
    chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    chips.add_css_class("linked")
    chips.set_margin_start(12)
    chips.set_margin_end(12)
    chips.set_margin_bottom(8)
    buttons: dict[str, Gtk.ToggleButton] = {}

    def _toggled(key: str, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            if buttons.get(key) is button:
                # Keep at least one active — caller may re-activate
                button.set_active(True)
            return
        for k, btn in buttons.items():
            if k != key and btn.get_active():
                btn.set_active(False)
        on_change(key)

    for key, label in items:
        btn = Gtk.ToggleButton(label=label)
        btn.add_css_class("filter-chip")
        btn.set_active(key == active_key)
        btn.connect("toggled", lambda b, k=key: _toggled(k, b))
        buttons[key] = btn
        chips.append(btn)
    return chips, buttons


def make_search_refresh_bar(
    *,
    placeholder: str,
    on_search: Callable[[], None],
    on_refresh: Callable[[], None],
    debounce_ms: int = 220,
) -> tuple[Gtk.Box, Gtk.SearchEntry, Gtk.Widget]:
    from ui.components import debounce

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    bar.set_margin_start(12)
    bar.set_margin_end(12)
    bar.set_margin_top(12)
    bar.set_margin_bottom(8)
    search = Gtk.SearchEntry()
    search.set_hexpand(True)
    set_placeholder_text(search, placeholder)
    debounced = debounce(debounce_ms, on_search)
    search.connect("search-changed", lambda *_: debounced())
    spinner = make_spinner(size=18)
    spinner.set_visible(False)
    refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
    refresh_btn.connect("clicked", lambda *_: on_refresh())
    bar.append(search)
    bar.append(spinner)
    bar.append(refresh_btn)
    return bar, search, spinner


def make_clamped_list(
    listbox: Gtk.ListBox,
    *,
    max_size: int = 1000,
) -> Adw.Clamp:
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.set_child(listbox)
    clamp = Adw.Clamp(maximum_size=max_size)
    clamp.set_margin_start(12)
    clamp.set_margin_end(12)
    clamp.set_margin_bottom(12)
    clamp.set_child(scrolled)
    return clamp


def threaded_refresh(
    *,
    work: Callable[[], Any],
    on_ok: Callable[[Any], None],
    on_error: Callable[[BaseException], None] | None = None,
    spinner: Gtk.Widget | None = None,
    toast_overlay: Adw.ToastOverlay | None = None,
    error_prefix: str = "",
) -> None:
    if spinner is not None:
        spinner.set_visible(True)

    def done(result: Any, error: BaseException | None) -> None:
        if spinner is not None:
            spinner.set_visible(False)
        if error is not None:
            if on_error is not None:
                on_error(error)
            elif toast_overlay is not None:
                msg = f"{error_prefix}{error}" if error_prefix else str(error)
                show_toast(toast_overlay, msg)
            return
        on_ok(result)

    run_in_thread(work, done)
