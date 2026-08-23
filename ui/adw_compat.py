# SPDX-License-Identifier: GPL-3.0-or-later
"""Libadwaita / GTK feature detection: modern widgets first, Mint 21.3 fallbacks last.

CachyOS (current Adw) must keep NavigationSplitView, ToolbarView, AlertDialog,
SwitchRow, SpinRow. Fallbacks run only when the type or method is missing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from ui.compat_attr import call_if_present, first_attr


def response_appearance(kind: str) -> Any:
    enum = getattr(Adw, "ResponseAppearance", None)
    if enum is None:
        return None
    return getattr(enum, kind, None)


def set_placeholder_text(widget: Gtk.Widget, text: str) -> bool:
    """Gtk.SearchEntry.set_placeholder_text exists only since GTK 4.10."""
    return call_if_present(widget, "set_placeholder_text", text)


def set_window_content(window: Gtk.Widget, child: Gtk.Widget) -> bool:
    setter = first_attr(window, "set_content", "set_child")
    if not callable(setter):
        return False
    setter(child)
    return True


def make_toolbar(header: Gtk.Widget, content: Gtk.Widget) -> Gtk.Widget:
    cls = getattr(Adw, "ToolbarView", None)
    if cls is not None:
        view = cls()
        view.add_top_bar(header)
        view.set_content(content)
        return view
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    box.append(header)
    content.set_vexpand(True)
    box.append(content)
    return box


class SplitShell:
    """NavigationSplitView + NavigationPage, or a Gtk.Box sidebar+content split."""

    def __init__(self) -> None:
        split_cls = getattr(Adw, "NavigationSplitView", None)
        page_cls = getattr(Adw, "NavigationPage", None)
        self._page_cls = page_cls
        self._content_page: Any = None
        self._title_sink: Callable[[str], None] | None = None
        if split_cls is not None and page_cls is not None:
            self.is_modern = True
            self._split = split_cls()
            call_if_present(self._split, "set_min_sidebar_width", 220)
            call_if_present(self._split, "set_max_sidebar_width", 280)
            self.widget: Gtk.Widget = self._split
        else:
            self.is_modern = False
            self._split = None
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            self._sidebar_host = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self._sidebar_host.set_size_request(240, -1)
            self._sidebar_host.set_hexpand(False)
            self._content_host = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self._content_host.set_hexpand(True)
            self._content_host.set_vexpand(True)
            sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
            box.append(self._sidebar_host)
            box.append(sep)
            box.append(self._content_host)
            self.widget = box

    def bind_title(self, sink: Callable[[str], None]) -> None:
        self._title_sink = sink

    def set_sidebar(self, child: Gtk.Widget, *, title: str) -> None:
        if self.is_modern and self._split is not None and self._page_cls is not None:
            page = self._page_cls()
            page.set_title(title)
            page.set_child(child)
            self._split.set_sidebar(page)
            return
        self._sidebar_host.append(child)

    def set_content(self, child: Gtk.Widget, *, title: str) -> None:
        if self.is_modern and self._split is not None and self._page_cls is not None:
            page = self._page_cls()
            page.set_title(title)
            page.set_child(child)
            self._split.set_content(page)
            self._content_page = page
            return
        child.set_hexpand(True)
        child.set_vexpand(True)
        self._content_host.append(child)
        self.set_content_title(title)

    def set_content_title(self, title: str) -> None:
        if self._content_page is not None:
            setter = getattr(self._content_page, "set_title", None)
            if callable(setter):
                setter(title)
        if self._title_sink is not None:
            self._title_sink(title)


def make_switch_row() -> Gtk.Widget:
    cls = getattr(Adw, "SwitchRow", None)
    if cls is not None:
        return cls()
    row = Adw.ActionRow()
    switch = Gtk.Switch()
    switch.set_valign(Gtk.Align.CENTER)
    row.add_suffix(switch)
    row.set_activatable_widget(switch)

    def get_active() -> bool:
        return bool(switch.get_active())

    def set_active(active: bool) -> None:
        switch.set_active(bool(active))

    row.get_active = get_active  # type: ignore[method-assign]
    row.set_active = set_active  # type: ignore[method-assign]
    orig_connect = row.connect

    def connect(detailed_signal: str, callback: Callable[..., Any], *args: Any) -> int:
        if detailed_signal == "notify::active":
            return int(
                switch.connect("notify::active", lambda *_a: callback(row, *_a))
            )
        return int(orig_connect(detailed_signal, callback, *args))

    row.connect = connect  # type: ignore[method-assign]
    return row


def make_spin_row(*, adjustment: Gtk.Adjustment, digits: int = 0) -> Gtk.Widget:
    cls = getattr(Adw, "SpinRow", None)
    if cls is not None:
        return cls(adjustment=adjustment, digits=digits)
    row = Adw.ActionRow()
    spin = Gtk.SpinButton(adjustment=adjustment, climb_rate=1, digits=digits)
    spin.set_valign(Gtk.Align.CENTER)
    row.add_suffix(spin)
    row.get_value = spin.get_value  # type: ignore[method-assign]
    setter = getattr(spin, "set_value", None)
    if callable(setter):
        row.set_value = setter  # type: ignore[method-assign]
    return row


class CompatDialog:
    """Unified AlertDialog / MessageDialog / Window so callers stay identical."""

    def __init__(
        self,
        impl: Any,
        *,
        present_with_parent: bool,
        on_response_hook: Callable[[Callable[..., Any]], None] | None = None,
    ) -> None:
        self._impl = impl
        self._present_with_parent = present_with_parent
        self._on_response_hook = on_response_hook

    def add_response(self, response_id: str, label: str) -> None:
        call_if_present(self._impl, "add_response", response_id, label)

    def set_response_appearance(self, response_id: str, appearance: Any) -> None:
        if appearance is None:
            return
        call_if_present(self._impl, "set_response_appearance", response_id, appearance)

    def set_default_response(self, response_id: str) -> None:
        call_if_present(self._impl, "set_default_response", response_id)

    def set_close_response(self, response_id: str) -> None:
        call_if_present(self._impl, "set_close_response", response_id)

    def connect(self, signal: str, callback: Callable[..., Any]) -> None:
        if signal == "response" and self._on_response_hook is not None:
            self._on_response_hook(callback)
            return
        self._impl.connect(signal, callback)

    def present(self, parent: Gtk.Window) -> None:
        present = getattr(self._impl, "present", None)
        if not callable(present):
            return
        if self._present_with_parent:
            try:
                present(parent)
            except TypeError:
                present()
            return
        try:
            present()
        except TypeError:
            present(parent)

    def close(self) -> None:
        closer = first_attr(self._impl, "close", "destroy")
        if callable(closer):
            closer()


def _window_dialog(
    parent: Gtk.Window,
    heading: str,
    body: str,
    extra_child: Gtk.Widget | None,
) -> CompatDialog:
    win = Adw.Window()
    win.set_transient_for(parent)
    win.set_modal(True)
    win.set_title(heading)
    win.set_default_size(480, 280)
    header = Adw.HeaderBar()
    body_lbl = Gtk.Label(label=body)
    body_lbl.set_wrap(True)
    body_lbl.set_xalign(0)
    btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_box.set_halign(Gtk.Align.END)
    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    vbox.set_margin_start(16)
    vbox.set_margin_end(16)
    vbox.set_margin_top(8)
    vbox.set_margin_bottom(16)
    vbox.append(body_lbl)
    if extra_child is not None:
        vbox.append(extra_child)
    vbox.append(btn_box)
    set_window_content(win, make_toolbar(header, vbox))

    buttons: dict[str, Gtk.Button] = {}
    response_cb: list[Callable[..., Any]] = []

    class _Impl:
        def add_response(self, response_id: str, label: str) -> None:
            btn = Gtk.Button(label=label)
            btn.set_valign(Gtk.Align.CENTER)

            def on_clicked(*_a: object) -> None:
                if response_cb:
                    response_cb[0](win, response_id)
                win.close()

            btn.connect("clicked", on_clicked)
            buttons[response_id] = btn
            btn_box.append(btn)

        def set_response_appearance(self, response_id: str, appearance: Any) -> None:
            btn = buttons.get(response_id)
            if btn is None or appearance is None:
                return
            destructive = response_appearance("DESTRUCTIVE")
            suggested = response_appearance("SUGGESTED")
            if destructive is not None and appearance == destructive:
                btn.add_css_class("destructive-action")
            elif suggested is not None and appearance == suggested:
                btn.add_css_class("suggested-action")

        def set_default_response(self, response_id: str) -> None:
            btn = buttons.get(response_id)
            if btn is not None:
                btn.add_css_class("suggested-action")

        def set_close_response(self, _response_id: str) -> None:
            return

        def present(self) -> None:
            win.present()

        def close(self) -> None:
            win.close()

        def destroy(self) -> None:
            win.destroy()

    impl = _Impl()

    def hook(callback: Callable[..., Any]) -> None:
        response_cb.clear()
        response_cb.append(callback)

    return CompatDialog(impl, present_with_parent=False, on_response_hook=hook)


def make_message_dialog(
    parent: Gtk.Window,
    heading: str,
    body: str,
    *,
    extra_child: Gtk.Widget | None = None,
) -> CompatDialog:
    alert_cls = getattr(Adw, "AlertDialog", None)
    msg_cls = getattr(Adw, "MessageDialog", None)

    def _try(cls: Any, factory: Callable[[], Any], *, with_parent: bool) -> CompatDialog | None:
        if cls is None:
            return None
        dialog = factory()
        if extra_child is not None:
            setter = getattr(dialog, "set_extra_child", None)
            if not callable(setter):
                closer = first_attr(dialog, "close", "destroy")
                if callable(closer):
                    closer()
                return None
            setter(extra_child)
        return CompatDialog(dialog, present_with_parent=with_parent)

    modern = _try(
        alert_cls,
        lambda: alert_cls.new(heading, body),
        with_parent=True,
    )
    if modern is not None:
        return modern
    legacy = _try(
        msg_cls,
        lambda: msg_cls(transient_for=parent, heading=heading, body=body),
        with_parent=False,
    )
    if legacy is not None:
        return legacy
    return _window_dialog(parent, heading, body, extra_child)


def present_about(
    parent: Gtk.Window,
    *,
    application_name: str,
    version: str,
    developer_name: str,
    copyright_line: str,
    comments: str,
    website: str,
    issue_url: str | None = None,
    license_type: Any = None,
    legal_title: str | None = None,
    legal_copyright: str | None = None,
    legal_text: str | None = None,
) -> bool:
    about_cls = first_attr(Adw, "AboutDialog", "AboutWindow")
    if about_cls is None:
        win = Adw.Window()
        win.set_transient_for(parent)
        win.set_modal(True)
        win.set_title(application_name)
        win.set_default_size(420, 320)
        header = Adw.HeaderBar()
        close_btn = Gtk.Button(label="OK")
        close_btn.add_css_class("suggested-action")
        close_btn.connect("clicked", lambda *_: win.close())
        header.pack_end(close_btn)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.set_margin_top(12)
        box.set_margin_bottom(18)
        for line in (
            application_name,
            version,
            copyright_line,
            comments,
            developer_name,
        ):
            lbl = Gtk.Label(label=line)
            lbl.set_wrap(True)
            lbl.set_xalign(0)
            box.append(lbl)
        set_window_content(win, make_toolbar(header, box))
        win.present()
        return True

    dialog = about_cls()
    call_if_present(dialog, "set_application_name", application_name)
    call_if_present(dialog, "set_version", version)
    call_if_present(dialog, "set_developer_name", developer_name)
    call_if_present(dialog, "set_developers", [developer_name])
    call_if_present(dialog, "set_copyright", copyright_line)
    if license_type is not None:
        call_if_present(dialog, "set_license_type", license_type)
    add_legal = getattr(dialog, "add_legal_section", None)
    if callable(add_legal) and legal_title and legal_text:
        try:
            add_legal(
                legal_title,
                legal_copyright or copyright_line,
                getattr(Gtk.License, "CUSTOM", Gtk.License.UNKNOWN),
                legal_text,
            )
        except (TypeError, ValueError):
            pass
    call_if_present(dialog, "set_comments", comments)
    call_if_present(dialog, "set_website", website)
    if issue_url:
        call_if_present(dialog, "set_issue_url", issue_url)
    present = getattr(dialog, "present", None)
    if callable(present):
        try:
            present(parent)
        except TypeError:
            present()
    return True


def present_text(parent: Gtk.Window, heading: str, body: str) -> None:
    """Scrollable text (MAJ / légal) without truncating install commands."""
    alert_cls = getattr(Adw, "AlertDialog", None)
    if alert_cls is not None and len(body) < 3500:
        dialog = alert_cls(heading=heading, body=body)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        choose = getattr(dialog, "choose", None)
        if callable(choose):
            choose(parent, None, lambda *_: None)
        return

    win = Adw.Window()
    win.set_transient_for(parent)
    win.set_modal(True)
    win.set_title(heading)
    win.set_default_size(560, 520)
    header = Adw.HeaderBar()
    close_btn = Gtk.Button(label="OK")
    close_btn.connect("clicked", lambda *_: win.close())
    header.pack_end(close_btn)
    text = Gtk.TextView()
    text.set_editable(False)
    text.set_cursor_visible(False)
    text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    text.set_left_margin(16)
    text.set_right_margin(16)
    text.set_top_margin(12)
    text.set_bottom_margin(12)
    text.get_buffer().set_text(body)
    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    scroll.set_child(text)
    set_window_content(win, make_toolbar(header, scroll))
    win.present()
