# SPDX-License-Identifier: GPL-3.0-or-later
"""Reports and plugins page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from core import i18n, plugins, report
from ui.components import ActionListRow, make_spinner, run_in_thread, show_toast


def build(win: Any) -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    bar.add_css_class("page-toolbar")
    title = Gtk.Label(label=i18n.t("tools_title"), xalign=0)
    title.add_css_class("heading")
    title.set_hexpand(True)
    win._tools_spinner = make_spinner(size=18)
    win._tools_spinner.set_visible(False)
    refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
    refresh_btn.connect("clicked", lambda *_: refresh(win, show_spinner=True))
    bar.append(title)
    bar.append(win._tools_spinner)
    bar.append(refresh_btn)
    root.append(bar)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    clamp = Adw.Clamp(maximum_size=900)
    clamp.set_margin_start(12)
    clamp.set_margin_end(12)
    clamp.set_margin_bottom(12)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

    report_group = Adw.PreferencesGroup()
    report_group.set_title(i18n.t("html_report"))
    export_row = Adw.ActionRow()
    export_row.set_title(i18n.t("export_health"))
    export_row.set_subtitle(i18n.t("html_report_sub"))
    export_btn = Gtk.Button(label=i18n.t("export"))
    export_btn.add_css_class("suggested-action")
    export_btn.set_valign(Gtk.Align.CENTER)
    export_btn.connect("clicked", lambda *_: export_html_report(win))
    export_row.add_suffix(export_btn)
    report_group.add(export_row)
    box.append(report_group)

    plugins_group = Adw.PreferencesGroup()
    plugins_group.set_title(i18n.t("plugins"))
    ensure_row = Adw.ActionRow()
    ensure_row.set_title(i18n.t("create_plugin_example"))
    ensure_row.set_subtitle(str(plugins.plugins_dir()))
    ensure_btn = Gtk.Button(label=i18n.t("create_sample"))
    ensure_btn.set_valign(Gtk.Align.CENTER)
    ensure_btn.connect("clicked", lambda *_: ensure_example_plugin(win))
    ensure_row.add_suffix(ensure_btn)
    plugins_group.add(ensure_row)
    box.append(plugins_group)

    win._plugins_list = Gtk.ListBox()
    win._plugins_list.set_selection_mode(Gtk.SelectionMode.NONE)
    win._plugins_list.add_css_class("boxed-list")
    box.append(win._section(i18n.t("plugins_scripts"), win._plugins_list))

    clamp.set_child(box)
    scrolled.set_child(clamp)
    root.append(scrolled)
    return root


def export_html_report(win: Any) -> None:
    win._set_busy(True)
    show_toast(win._toast_overlay, i18n.t("tools_report_running"), timeout=2)

    def work() -> Path:
        return report.export_report(report.default_report_path())

    def done(result: Any, error: BaseException | None) -> None:
        win._set_busy(False)
        if error is not None:
            show_toast(win._toast_overlay, str(error))
            return
        show_toast(win._toast_overlay, i18n.t("tools_report_done", path=result))

    run_in_thread(work, done)


def ensure_example_plugin(win: Any) -> None:
    def work() -> Path:
        return plugins.ensure_example_plugin()

    def done(result: Any, error: BaseException | None) -> None:
        if error is not None:
            show_toast(win._toast_overlay, str(error))
            return
        show_toast(win._toast_overlay, i18n.t("tools_plugin_example", path=result))
        refresh(win)

    run_in_thread(work, done)


def run_plugin(win: Any, name: str) -> None:
    win._set_busy(True)
    show_toast(win._toast_overlay, i18n.t("tools_plugin_running", name=name), timeout=2)

    def work() -> dict[str, Any]:
        return plugins.run_plugin(name)

    def done(result: Any, error: BaseException | None) -> None:
        win._set_busy(False)
        if error is not None:
            show_toast(win._toast_overlay, str(error))
            return
        ok = bool((result or {}).get("ok"))
        out = ((result or {}).get("stdout") or "").strip()
        err = ((result or {}).get("stderr") or "").strip()
        msg = out or err or ("OK" if ok else i18n.t("tools_fail"))
        show_toast(win._toast_overlay, msg[:180], timeout=5)

    run_in_thread(work, done)


def refresh(win: Any, *, show_spinner: bool = False) -> None:
    if show_spinner:
        win._tools_spinner.set_visible(True)

    def work() -> list[dict[str, Any]]:
        plugins.ensure_example_plugin()
        return plugins.list_plugins()

    def done(result: Any, error: BaseException | None) -> None:
        win._tools_spinner.set_visible(False)
        if error is not None:
            show_toast(win._toast_overlay, i18n.t("tools_error", detail=str(error)))
            return
        win._clear_listbox(win._plugins_list)
        for item in result or []:
            row = ActionListRow(
                str(item.get("name")),
                str(item.get("path")),
                button_label=i18n.t("tools_run"),
                button_css="suggested-action",
                on_clicked=lambda n=str(item.get("name")): run_plugin(win, n),
            )
            row.set_busy(win._busy_ops > 0)
            win._plugins_list.append(row)
        if not (result or []):
            win._plugins_list.append(
                Adw.ActionRow(title=i18n.t("tools_empty"), subtitle=str(plugins.plugins_dir()))
            )

    run_in_thread(work, done)
