# SPDX-License-Identifier: GPL-3.0-or-later
"""GTK 4.6 / libadwaita 1.1 fallbacks — no app imports."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gi.repository import Adw, Gdk, Gio, GLib, Gtk


def set_bin_child(widget: Gtk.Widget, child: Gtk.Widget) -> None:
    for name in ("set_content", "set_child"):
        fn = getattr(widget, name, None)
        if callable(fn):
            fn(child)
            return
    raise RuntimeError("ni set_content ni set_child")


def toolbar_view(header: Gtk.Widget, body: Gtk.Widget) -> Gtk.Widget:
    cls = getattr(Adw, "ToolbarView", None)
    if cls is not None:
        view = cls()
        view.add_top_bar(header)
        view.set_content(body)
        return view
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.append(header)
    body.set_vexpand(True)
    box.append(body)
    return box


def split_view(sidebar: Gtk.Widget, content: Gtk.Widget, title: str) -> Gtk.Widget:
    split_cls = getattr(Adw, "NavigationSplitView", None)
    page_cls = getattr(Adw, "NavigationPage", None)
    if split_cls is not None and page_cls is not None:
        split = split_cls()
        set_min = getattr(split, "set_min_sidebar_width", None)
        if callable(set_min):
            set_min(44)
        split.set_sidebar(page_cls(child=sidebar, title=title))
        split.set_content(page_cls(child=content, title=title))
        return split
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    sidebar.set_size_request(220, -1)
    content.set_hexpand(True)
    content.set_vexpand(True)
    box.append(sidebar)
    box.append(content)
    return box


def set_split_sidebar_visible(split: Gtk.Widget, visible: bool) -> None:
    setter = getattr(split, "set_show_sidebar", None)
    if callable(setter):
        setter(visible)
        return
    sidebar = getattr(split, "get_sidebar", None)
    if callable(sidebar):
        page = sidebar()
        child_get = getattr(page, "get_child", None)
        if callable(child_get):
            child = child_get()
            if child is not None:
                child.set_visible(visible)


def open_external_uri(uri: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error:
        show = getattr(Gtk, "show_uri", None)
        if callable(show):
            show(None, uri, Gdk.CURRENT_TIME)


def switch_row(title: str, subtitle: str, active: bool) -> tuple[Gtk.Widget, Any]:
    cls = getattr(Adw, "SwitchRow", None)
    if cls is not None:
        row = cls(title=title, subtitle=subtitle)
        row.set_active(active)
        return row, row
    row = Adw.ActionRow(title=title, subtitle=subtitle)
    switch = Gtk.Switch()
    switch.set_active(active)
    switch.set_valign(Gtk.Align.CENTER)
    row.add_suffix(switch)
    row.set_activatable_widget(switch)
    return row, switch


def present_alert(
    parent: Gtk.Window,
    heading: str,
    body: str,
    responses: list[tuple[str, str]],
    *,
    suggested: str | None = None,
    on_response: Callable[[str], None] | None = None,
) -> None:
    alert_cls = getattr(Adw, "AlertDialog", None)
    if alert_cls is not None:
        dialog = alert_cls(heading=heading, body=body)
        for key, label in responses:
            dialog.add_response(key, label)
        if suggested:
            appearance = getattr(Adw, "ResponseAppearance", None)
            if appearance is not None:
                dialog.set_response_appearance(suggested, appearance.SUGGESTED)

        def on_adw(_d: Any, response: str) -> None:
            if on_response is not None:
                on_response(response)

        if on_response is not None:
            dialog.connect("response", on_adw)
        dialog.present(parent)
        return

    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.NONE,
        text=heading,
    )
    try:
        dialog.set_property("secondary-text", body)
    except (TypeError, GLib.Error):
        extra = Gtk.Label(label=body, wrap=True, xalign=0)
        dialog.get_content_area().append(extra)
    ids: dict[int, str] = {}
    for index, (key, label) in enumerate(responses):
        code = 100 + index
        dialog.add_button(label, code)
        ids[code] = key

    def on_gtk(_d: Gtk.MessageDialog, response: int) -> None:
        dialog.destroy()
        if on_response is not None:
            on_response(ids.get(int(response), "close"))

    dialog.connect("response", on_gtk)
    dialog.present()


def choose_rgba(
    window: Gtk.Window,
    current: Gdk.RGBA | tuple[float, float, float],
    on_color: Callable[[Gdk.RGBA], None],
) -> None:
    rgba = Gdk.RGBA()
    if isinstance(current, Gdk.RGBA):
        rgba = current
    else:
        rgba.red, rgba.green, rgba.blue, rgba.alpha = (*current, 1.0)
    color_dialog = getattr(Gtk, "ColorDialog", None)
    if color_dialog is not None:
        dialog = color_dialog()

        def finish(d: Any, res: Gio.AsyncResult) -> None:
            try:
                picked = d.choose_rgba_finish(res)
            except GLib.Error:
                return
            on_color(picked)

        dialog.choose_rgba(window, rgba, None, finish)
        return
    native_cls = getattr(Gtk, "ColorChooserNative", None)
    if native_cls is not None:
        native = native_cls.new("", window)
        native.set_rgba(rgba)

        def on_resp(dlg: Any, response: int) -> None:
            if int(response) == int(Gtk.ResponseType.ACCEPT):
                on_color(dlg.get_rgba())
            dlg.destroy()

        native.connect("response", on_resp)
        native.show()


def present_startup_error(message: str, on_close: Callable[[], None] | None = None) -> bool:
    """Show a modal error when the app fails before the main window exists."""
    from ui_kit import chrome_config

    title = chrome_config.APP_NAME
    try:
        dialog = Gtk.MessageDialog(modal=True, message_type=Gtk.MessageType.ERROR, text=title)
        try:
            dialog.set_property("secondary-text", message)
        except (TypeError, GLib.Error):
            extra = Gtk.Label(label=message, wrap=True, xalign=0)
            dialog.get_content_area().append(extra)
        dialog.add_button("OK", int(Gtk.ResponseType.CLOSE))

        def on_resp(dlg: Gtk.MessageDialog, *_args: object) -> None:
            dlg.destroy()
            if on_close is not None:
                on_close()

        dialog.connect("response", on_resp)
        dialog.present()
        return True
    except Exception:  # noqa: BLE001
        return False
