# SPDX-License-Identifier: GPL-3.0-or-later
"""Manual update dialog — copy-paste commands (no auto-install)."""

from __future__ import annotations

from gi.repository import Adw, Gdk, GLib, Gtk

from ui_kit.compat import set_bin_child
from ui_kit.strings import normalize_language, t


def build_title(
    heading: str,
    *,
    new_version: str | None = None,
    lang: str | None = None,
) -> str:
    """Window title: kit label + version when new_version is set, else heading."""
    if new_version:
        return f"{t('update_title', lang)} {new_version.strip()}"
    return heading.strip()


def _copy_text(text: str) -> None:
    display = Gdk.Display.get_default()
    if display is None:
        return
    clip = display.get_clipboard()
    setter = getattr(clip, "set", None)
    try:
        if callable(setter):
            setter(text)
        else:
            clip.set_content(Gdk.ContentProvider.new_for_value(text))
    except (TypeError, GLib.Error):
        clip.set_content(Gdk.ContentProvider.new_for_value(text))


def _build_footer(info: str, code: str) -> Gtk.Widget:
    footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    footer.add_css_class("uni-update-footer")

    hint_lbl = Gtk.Label(label=t("update_manual_hint", code), wrap=True, xalign=0)
    hint_lbl.add_css_class("uni-muted")
    footer.append(hint_lbl)

    info_text = (info or "").strip()
    if info_text:
        info_view = Gtk.TextView()
        info_view.set_editable(False)
        info_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        info_view.get_buffer().set_text(info_text)
        info_view.set_left_margin(4)
        info_view.set_right_margin(4)

        info_scroll = Gtk.ScrolledWindow()
        info_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        info_scroll.set_max_content_height(140)
        info_scroll.set_propagate_natural_height(True)
        info_scroll.set_child(info_view)
        footer.append(info_scroll)

    return footer


def _assemble_window(header: Gtk.Widget, body: Gtk.Widget, footer: Gtk.Widget | None) -> Gtk.Widget:
    toolbar_cls = getattr(Adw, "ToolbarView", None)
    if toolbar_cls is not None:
        view = toolbar_cls()
        view.add_top_bar(header)
        view.set_content(body)
        if footer is not None:
            add_bottom = getattr(view, "add_bottom_bar", None)
            if callable(add_bottom):
                add_bottom(footer)
            else:
                outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                body.set_vexpand(True)
                outer.append(body)
                outer.append(footer)
                view.set_content(outer)
        return view

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.append(header)
    body.set_vexpand(True)
    box.append(body)
    if footer is not None:
        box.append(footer)
    return box


def present(
    parent: Gtk.Window,
    heading: str,
    info: str,
    commands: str,
    *,
    new_version: str | None = None,
    lang: str | None = None,
) -> None:
    """Show commands in main area; app info in bottom bar; copy = commands only."""
    code = normalize_language(lang)
    title = build_title(heading, new_version=new_version, lang=code)

    win = Adw.Window()
    win.set_transient_for(parent)
    win.set_modal(True)
    win.set_title(title)
    win.set_default_size(640, 480)

    header = Adw.HeaderBar()
    header.add_css_class("uni-titlebar")
    header.set_title_widget(Adw.WindowTitle(title=title, subtitle=""))
    copy_btn = Gtk.Button(label=t("update_copy", code))
    copy_btn.add_css_class("suggested-action")
    copy_btn.connect("clicked", lambda *_: _copy_text(commands))
    header.pack_end(copy_btn)
    close_btn = Gtk.Button(label=t("close", code))
    close_btn.connect("clicked", lambda *_: win.close())
    header.pack_end(close_btn)

    cmd_view = Gtk.TextView()
    cmd_view.set_editable(False)
    cmd_view.set_wrap_mode(Gtk.WrapMode.NONE)
    cmd_view.get_buffer().set_text(commands)
    cmd_view.add_css_class("monospace")
    cmd_view.set_left_margin(12)
    cmd_view.set_right_margin(12)
    cmd_view.set_top_margin(8)
    cmd_view.set_bottom_margin(8)

    cmd_scroll = Gtk.ScrolledWindow()
    cmd_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    cmd_scroll.set_vexpand(True)
    cmd_scroll.set_margin_start(8)
    cmd_scroll.set_margin_end(8)
    cmd_scroll.set_margin_top(8)
    cmd_scroll.set_child(cmd_view)

    footer = _build_footer(info, code)
    set_bin_child(win, _assemble_window(header, cmd_scroll, footer))
    win.present()
