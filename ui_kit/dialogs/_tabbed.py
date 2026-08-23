# SPDX-License-Identifier: GPL-3.0-or-later
"""Tabbed modal windows."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from ui_kit.compat import set_bin_child, toolbar_view


def present_tabbed(
    parent: Gtk.Window,
    title: str,
    tabs: list[tuple[str, str, str | Gtk.Widget]],
) -> Gtk.Window:
    """tabs: [(id, label, markdown_text | widget), ...]"""
    win = Adw.Window()
    win.set_transient_for(parent)
    win.set_modal(True)
    win.set_title(title)
    win.set_default_size(620, 520)

    header = Adw.HeaderBar()
    header.add_css_class("uni-titlebar")
    close_btn = Gtk.Button(label="OK")
    close_btn.connect("clicked", lambda *_: win.close())
    header.pack_end(close_btn)

    stack = Gtk.Stack()
    stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
    stack.set_vexpand(True)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    bar.set_margin_start(12)
    bar.set_margin_end(12)
    bar.set_margin_top(8)

    first_id = tabs[0][0] if tabs else ""

    for tab_id, label, body in tabs:
        if isinstance(body, str):
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_vexpand(True)
            text = Gtk.TextView()
            text.set_editable(False)
            text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            text.set_margin_start(8)
            text.set_margin_end(8)
            text.get_buffer().set_text(body)
            scroll.set_child(text)
            stack.add_named(scroll, tab_id)
        else:
            body.set_vexpand(True)
            stack.add_named(body, tab_id)

        btn = Gtk.ToggleButton(label=label)
        btn.set_active(tab_id == first_id)

        def on_tab(b: Gtk.ToggleButton, tid: str = tab_id) -> None:
            stack.set_visible_child_name(tid)
            child = bar.get_first_child()
            while child is not None:
                if isinstance(child, Gtk.ToggleButton):
                    child.set_active(child is b)
                child = child.get_next_sibling()

        btn.connect("clicked", on_tab)
        bar.append(btn)

    if first_id:
        stack.set_visible_child_name(first_id)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.append(bar)
    outer.append(stack)
    set_bin_child(win, toolbar_view(header, outer))
    win.present()
    return win
