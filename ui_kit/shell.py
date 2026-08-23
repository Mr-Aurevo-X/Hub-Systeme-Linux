# SPDX-License-Identifier: GPL-3.0-or-later
"""Application shell — sidebar, title chrome."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from ui_kit import chrome_config
from ui_kit.compat import split_view, toolbar_view
from ui_kit.dialogs import legal as legal_dialog
from ui_kit.dialogs import settings as settings_dialog
from ui_kit.strings import normalize_language, t

_UPDATE_ICONS = (
    "system-software-update-symbolic",
    "software-update-available-symbolic",
    "view-refresh-symbolic",
)


def format_app_line(name: str, version: str) -> str:
    return f"{name} {version}".strip()


def content_title_parts(
    page: str,
    *,
    app_name: str | None = None,
    app_version: str | None = None,
) -> tuple[str, str]:
    name = chrome_config.APP_NAME if app_name is None else app_name
    version = chrome_config.APP_VERSION if app_version is None else app_version
    return page, format_app_line(name, version)


def language_from_scale(value: float) -> str:
    return "en" if value >= 0.5 else "fr"


def scale_from_language(lang: str) -> float:
    return 1.0 if normalize_language(lang) == "en" else 0.0


def _new_update_button() -> Gtk.Button:
    for icon_name in _UPDATE_ICONS:
        btn = Gtk.Button.new_from_icon_name(icon_name)
        if btn.get_child() is not None:
            return btn
    return Gtk.Button(label="↻")


def _set_css_class(widget: Gtk.Widget, name: str, active: bool) -> None:
    """GTK 4.6 (Mint 21.3) has no Gtk.Widget.toggle_css_class."""
    toggle = getattr(widget, "toggle_css_class", None)
    if callable(toggle):
        toggle(name, active)
        return
    if active:
        widget.add_css_class(name)
    else:
        widget.remove_css_class(name)


class ShellLayout:
    """Handles built shell widgets and title state."""

    def __init__(
        self,
        *,
        split: Gtk.Widget,
        page_title: Adw.WindowTitle,
        content_header: Adw.HeaderBar,
        lang: str,
    ) -> None:
        self._split = split
        self._page_title = page_title
        self._content_header = content_header
        self._lang = lang
        self._update_btn: Gtk.Button | None = None
        self._lang_scale: Gtk.Scale | None = None
        self._lang_fr_label: Gtk.Label | None = None
        self._lang_en_label: Gtk.Label | None = None
        self._lang_scale_suppress = False

    @property
    def widget(self) -> Gtk.Widget:
        return self._split

    @property
    def content_header(self) -> Adw.HeaderBar:
        return self._content_header

    def set_page_title(self, title: str) -> None:
        page, brand = content_title_parts(title)
        self._page_title.set_title(page)
        self._page_title.set_subtitle(brand)

    def _sync_lang_slider_labels(self) -> None:
        active_fr = self._lang == "fr"
        if self._lang_fr_label is not None:
            _set_css_class(self._lang_fr_label, "uni-lang-active", active_fr)
            _set_css_class(self._lang_fr_label, "uni-muted", not active_fr)
        if self._lang_en_label is not None:
            _set_css_class(self._lang_en_label, "uni-lang-active", not active_fr)
            _set_css_class(self._lang_en_label, "uni-muted", active_fr)

    def attach_chrome_buttons(
        self,
        parent: Gtk.Window,
        *,
        on_check_updates: Callable[[], None],
        on_language_toggle: Callable[[str], None],
        current_language: str,
        settings_snapshot: dict[str, Any],
        current_version: str,
        on_settings_save: Callable[[dict[str, Any]], None],
        on_open_preferences: Callable[[], None] | None = None,
    ) -> tuple[Gtk.Button, Gtk.Widget]:
        lang = normalize_language(current_language)
        self._lang = lang

        update_btn = _new_update_button()
        update_btn.add_css_class("uni-chrome-update")
        update_btn.set_tooltip_text(t("check_updates", lang))
        update_btn.connect("clicked", lambda *_: on_check_updates())
        self._content_header.pack_end(update_btn)
        self._update_btn = update_btn

        lang_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lang_box.add_css_class("uni-chrome-lang-slider")

        fr_label = Gtk.Label(label="FR")
        fr_label.add_css_class("uni-lang-label")
        en_label = Gtk.Label(label="EN")
        en_label.add_css_class("uni-lang-label")
        self._lang_fr_label = fr_label
        self._lang_en_label = en_label

        adjustment = Gtk.Adjustment(lower=0, upper=1, step_increment=1, page_increment=1)
        lang_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        lang_scale.set_digits(0)
        lang_scale.set_draw_value(False)
        lang_scale.set_value(scale_from_language(lang))
        lang_scale.set_tooltip_text(t("lang_toggle", lang))
        lang_scale.set_size_request(72, 28)
        self._lang_scale = lang_scale

        def on_scale_changed(scale: Gtk.Scale) -> None:
            if self._lang_scale_suppress:
                return
            target = language_from_scale(scale.get_value())
            if target == self._lang:
                return
            on_language_toggle(target)

        lang_scale.connect("value-changed", on_scale_changed)

        lang_box.append(fr_label)
        lang_box.append(lang_scale)
        lang_box.append(en_label)
        self._sync_lang_slider_labels()
        self._content_header.pack_end(lang_box)

        legal_btn = Gtk.Button.new_from_icon_name("help-about-symbolic")
        legal_btn.set_tooltip_text(t("legal", lang))
        legal_btn.connect("clicked", lambda *_: legal_dialog.present(parent, lang))
        self._content_header.pack_end(legal_btn)

        prefs_btn = Gtk.Button.new_from_icon_name("preferences-system-symbolic")
        prefs_btn.set_tooltip_text(t("preferences", lang))

        def open_prefs() -> None:
            if on_open_preferences is not None:
                on_open_preferences()
                return
            settings_dialog.present(
                parent,
                settings_snapshot,
                current_version=current_version,
                lang=lang,
                on_save=on_settings_save,
            )

        prefs_btn.connect("clicked", lambda *_: open_prefs())
        self._content_header.pack_end(prefs_btn)

        return update_btn, lang_box

    def update_language_button(self, lang: str) -> None:
        self._lang = normalize_language(lang)
        self._lang_scale_suppress = True
        if self._lang_scale is not None:
            self._lang_scale.set_value(scale_from_language(self._lang))
            self._lang_scale.set_tooltip_text(t("lang_toggle", self._lang))
        self._lang_scale_suppress = False
        self._sync_lang_slider_labels()


def build_main_layout(
    nav: Gtk.Widget,
    content_stack: Gtk.Widget,
    *,
    page_title: str = "",
    lang: str | None = None,
) -> ShellLayout:
    """Build split shell: sidebar (brand + nav) + content header + stack."""
    code = normalize_language(lang or chrome_config.UI_LANGUAGE)
    brand = format_app_line(chrome_config.APP_NAME, chrome_config.APP_VERSION)

    header_s = Adw.HeaderBar()
    header_s.add_css_class("uni-titlebar")
    brand_lbl = Gtk.Label(label=brand)
    brand_lbl.add_css_class("uni-sidebar-brand")
    brand_lbl.set_xalign(0)
    brand_lbl.set_margin_start(12)
    header_s.set_title_widget(brand_lbl)

    nav_scroll = Gtk.ScrolledWindow()
    nav_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    nav_scroll.set_vexpand(True)
    nav_scroll.set_child(nav)

    sidebar_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    sidebar_panel.add_css_class("uni-sidebar")
    sidebar_panel.append(header_s)
    sidebar_panel.append(nav_scroll)

    page, brand_line = content_title_parts(page_title)
    page_title_w = Adw.WindowTitle(title=page, subtitle=brand_line)
    content_header = Adw.HeaderBar()
    content_header.add_css_class("uni-titlebar")
    content_header.set_title_widget(page_title_w)

    content_body = toolbar_view(content_header, content_stack)
    split = split_view(sidebar_panel, content_body, brand)

    return ShellLayout(
        split=split,
        page_title=page_title_w,
        content_header=content_header,
        lang=code,
    )
