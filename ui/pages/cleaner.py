# SPDX-License-Identifier: GPL-3.0-or-later
"""Cleaner page."""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from core import cleaner, i18n
from ui.components import confirm_dialog, make_spinner, run_in_thread, show_toast


def build(win: Any) -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    root.set_margin_top(18)
    root.set_margin_bottom(18)
    root.set_margin_start(18)
    root.set_margin_end(18)

    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    scan_btn = Gtk.Button(label=i18n.t("scan"))
    scan_btn.add_css_class("suggested-action")
    scan_btn.connect("clicked", lambda *_: refresh(win, show_spinner=True))
    select_all_btn = Gtk.Button(label=i18n.t("select_all"))
    select_all_btn.connect("clicked", lambda *_: select_all(win, True))
    select_none_btn = Gtk.Button(label=i18n.t("select_none"))
    select_none_btn.connect("clicked", lambda *_: select_all(win, False))
    clean_btn = Gtk.Button(label=i18n.t("clean_selection"))
    clean_btn.add_css_class("destructive-action")
    clean_btn.connect("clicked", lambda *_: confirm_clean(win))
    win._track_privileged(clean_btn)
    win._cleaner_spinner = make_spinner(size=18)
    win._cleaner_spinner.set_visible(False)
    controls.append(scan_btn)
    controls.append(select_all_btn)
    controls.append(select_none_btn)
    controls.append(clean_btn)
    controls.append(win._cleaner_spinner)
    root.append(controls)

    win._cleaner_total = Gtk.Label(label=i18n.t("reclaimable", size="—"), xalign=0)
    win._cleaner_total.add_css_class("title-4")
    root.append(win._cleaner_total)

    win._cleaner_checks: dict[str, Gtk.CheckButton] = {}
    win._cleaner_list = Gtk.ListBox()
    win._cleaner_list.set_selection_mode(Gtk.SelectionMode.NONE)
    win._cleaner_list.add_css_class("boxed-list")
    clamp = Adw.Clamp(maximum_size=900)
    clamp.set_child(win._cleaner_list)
    root.append(clamp)
    return root


def select_all(win: Any, active: bool) -> None:
    for check in win._cleaner_checks.values():
        check.set_active(active)


def refresh(win: Any, *, show_spinner: bool = False) -> None:
    if show_spinner:
        win._cleaner_spinner.set_visible(True)
        win._set_busy(True)

    def work() -> list[dict[str, Any]]:
        return cleaner.scan()

    def done(result: Any, error: BaseException | None) -> None:
        if show_spinner:
            win._set_busy(False)
        win._cleaner_spinner.set_visible(False)
        if error is not None:
            show_toast(win._toast_overlay, i18n.t("clean_error", detail=str(error)))
            return
        win._clear_listbox(win._cleaner_list)
        win._cleaner_checks.clear()
        total = 0.0
        for item in result or []:
            total += float(item.get("size_mib") or 0)
            row = Adw.ActionRow()
            row.set_title(item["label"])
            paths = ", ".join(item.get("paths") or []) or "—"
            root_tag = " · root" if item.get("requires_root") else ""
            row.set_subtitle(f"{item.get('size_mib', 0):.2f} Mio · {paths}{root_tag}")
            check = Gtk.CheckButton()
            check.set_active(item.get("size_mib", 0) > 0)
            check.set_valign(Gtk.Align.CENTER)
            row.add_prefix(check)
            win._cleaner_checks[item["id"]] = check
            win._cleaner_list.append(row)
        win._cleaner_total.set_text(i18n.t("reclaimable", size=f"{total:.2f} Mio"))

    run_in_thread(work, done)


def confirm_clean(win: Any) -> None:
    selected = [key for key, check in win._cleaner_checks.items() if check.get_active()]
    if not selected:
        show_toast(win._toast_overlay, i18n.t("clean_none"))
        return
    confirm_dialog(
        win,
        i18n.t("clean_confirm_title"),
        i18n.t("clean_confirm_body"),
        confirm_label=i18n.t("clean_confirm"),
        on_confirm=lambda: _do_clean(win, selected),
    )


def _do_clean(win: Any, targets: list[str]) -> None:
    win._set_busy(True)
    show_toast(win._toast_overlay, i18n.t("clean_running"), timeout=4)

    def work() -> dict[str, Any]:
        return cleaner.clean(targets)

    def done(result: Any, error: BaseException | None) -> None:
        win._set_busy(False)
        if error is not None:
            show_toast(win._toast_overlay, str(error))
            return
        freed = result.get("freed_mib", 0) if isinstance(result, dict) else 0
        show_toast(win._toast_overlay, i18n.t("clean_done", freed=f"{freed:.2f}"))
        refresh(win)

    run_in_thread(work, done)
