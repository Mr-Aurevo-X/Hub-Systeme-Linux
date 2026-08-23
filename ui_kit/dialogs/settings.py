# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings — thème client (+ version installée, lecture seule)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gi.repository import Adw, Gdk, Gtk

from ui_kit import chrome_config
from ui_kit.compat import choose_rgba
from ui_kit.strings import normalize_language, t
from ui_kit.theme import (
    default_preset_id,
    list_presets,
    load_merged_colors,
    load_preset,
    load_user_theme,
    save_user_theme,
    user_theme_path,
)

_COLOR_KEYS = ("text", "muted", "accent", "ok", "warn", "danger")


def _normalize_hex(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if not text.startswith("#"):
        text = f"#{text}"
    return text


def present(
    parent: Gtk.Window,
    settings: dict[str, Any],
    *,
    current_version: str,
    lang: str | None = None,
    on_save: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    code = normalize_language(lang or chrome_config.UI_LANGUAGE)
    app_id = chrome_config.CONFIG_APP_ID

    win = Adw.PreferencesWindow()
    win.set_transient_for(parent)
    win.set_modal(True)
    win.set_title(t("preferences", code))

    page = Adw.PreferencesPage()

    info = Adw.PreferencesGroup(title=t("updates", code))
    ver_row = Adw.ActionRow(
        title=t("current_version", code),
        subtitle=current_version,
    )
    hint_row = Adw.ActionRow(
        title=t("update_manual_hint", code),
        subtitle="",
    )
    info.add(ver_row)
    info.add(hint_row)
    page.add(info)

    appearance = Adw.PreferencesGroup(
        title=t("appearance", code),
        description=t("appearance_sub", code),
    )
    preset_combo = Gtk.ComboBoxText()
    presets = list_presets()
    preset_ids = [pid for pid, _ in presets]
    for pid, label in presets:
        preset_combo.append(pid, label)
    current_preset = str(
        load_user_theme(config_app_id=app_id).get("preset") or default_preset_id()
    )
    if current_preset in preset_ids:
        preset_combo.set_active_id(current_preset)
    preset_combo.set_valign(Gtk.Align.CENTER)
    preset_row = Adw.ActionRow(title=t("theme_preset", code))
    preset_row.add_suffix(preset_combo)
    appearance.add(preset_row)

    merged = load_merged_colors(config_app_id=app_id, preset_id=current_preset)
    merged_colors = merged.get("colors") or {}
    color_entries: dict[str, Gtk.Entry] = {}

    def pick_color(key: str, entry: Gtk.Entry) -> None:
        current = _normalize_hex(entry.get_text()) or str(merged_colors.get(key) or "#ffffff")
        rgba = Gdk.RGBA()
        if not rgba.parse(current):
            rgba.parse("#ffffff")
        choose_rgba(win, rgba, lambda c: entry.set_text(c.to_string()))

    for key in _COLOR_KEYS:
        entry = Gtk.Entry()
        entry.set_width_chars(10)
        entry.set_text(str(merged_colors.get(key) or ""))
        color_entries[key] = entry
        pick_btn = Gtk.Button(label=t("theme_pick", code))
        pick_btn.connect("clicked", lambda *_a, k=key, e=entry: pick_color(k, e))
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.append(entry)
        box.append(pick_btn)
        row = Adw.ActionRow(title=key)
        row.add_suffix(box)
        appearance.add(row)

    def reset_colors() -> None:
        preset = str(preset_combo.get_active_id() or default_preset_id())
        colors = load_preset(preset).get("colors") or {}
        for key, entry in color_entries.items():
            entry.set_text(str(colors.get(key) or ""))

    reset_row = Adw.ActionRow(title=t("theme_reset", code))
    reset_btn = Gtk.Button(label=t("theme_reset", code))
    reset_btn.connect("clicked", lambda *_: reset_colors())
    reset_row.add_suffix(reset_btn)
    appearance.add(reset_row)
    page.add(appearance)

    save_group = Adw.PreferencesGroup()
    save_row = Adw.ActionRow(title=t("save", code))
    save_btn = Gtk.Button(label=t("save", code))
    save_btn.add_css_class("suggested-action")

    def do_save() -> None:
        preset = str(preset_combo.get_active_id() or default_preset_id())
        overrides: dict[str, str] = {}
        base = load_preset(preset).get("colors") or {}
        for key, entry in color_entries.items():
            value = _normalize_hex(entry.get_text())
            if value and value != str(base.get(key) or ""):
                overrides[key] = value
        save_user_theme(
            user_theme_path(app_id),
            preset_id=preset,
            overrides=overrides,
        )
        from ui_kit.theme import apply_theme

        apply_theme(config_app_id=app_id, preset_id=preset)
        updated = dict(settings)
        if on_save is not None:
            on_save(updated)
        win.close()

    save_btn.connect("clicked", lambda *_: do_save())
    save_row.add_suffix(save_btn)
    save_group.add(save_row)
    page.add(save_group)

    win.add(page)
    win.present()
