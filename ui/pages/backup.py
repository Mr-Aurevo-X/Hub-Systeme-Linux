# SPDX-License-Identifier: GPL-3.0-or-later
"""Snapshots page (Timeshift / Snapper)."""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from core import backup, i18n
from ui.components import confirm_dialog, make_spinner, run_in_thread, show_toast


def build(win: Any) -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    win._backup_stack = Gtk.Stack()
    win._backup_stack.set_vexpand(True)

    win._backup_status_page = Adw.StatusPage()
    win._backup_status_page.set_icon_name("drive-harddisk-symbolic")
    win._backup_status_page.set_title(i18n.t("snapshots"))
    win._backup_status_page.set_description(i18n.t("backup_checking"))
    status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    status_box.set_halign(Gtk.Align.CENTER)
    refresh_missing = Gtk.Button(label=i18n.t("refresh"))
    refresh_missing.connect("clicked", lambda *_: refresh(win, show_spinner=True))
    status_box.append(refresh_missing)
    win._backup_status_page.set_child(status_box)
    win._backup_stack.add_named(win._backup_status_page, "status")

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content.set_margin_top(18)
    content.set_margin_bottom(18)
    content.set_margin_start(18)
    content.set_margin_end(18)

    win._backup_status = Gtk.Label(label=f"{i18n.t('snapshots')}: —", xalign=0)
    win._backup_status.add_css_class("title-4")
    content.append(win._backup_status)

    controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    refresh_btn = Gtk.Button(label=i18n.t("refresh"))
    refresh_btn.connect("clicked", lambda *_: refresh(win, show_spinner=True))
    load_btn = Gtk.Button(label=i18n.t("load_snapshots_admin"))
    load_btn.connect(
        "clicked",
        lambda *_: refresh(win, show_spinner=True, privileged=True),
    )
    create_btn = Gtk.Button(label=i18n.t("create_snapshot"))
    create_btn.add_css_class("suggested-action")
    create_btn.connect("clicked", lambda *_: confirm_snapshot(win))
    win._track_privileged(load_btn)
    win._track_privileged(create_btn)
    win._backup_spinner = make_spinner(size=18)
    win._backup_spinner.set_visible(False)
    win._btrfs_assistant_btn = Gtk.Button(label=i18n.t("open_btrfs_assistant"))
    win._btrfs_assistant_btn.set_visible(False)
    win._btrfs_assistant_btn.connect(
        "clicked",
        lambda *_: open_btrfs_assistant(win),
    )
    controls.append(refresh_btn)
    controls.append(load_btn)
    controls.append(create_btn)
    controls.append(win._btrfs_assistant_btn)
    controls.append(win._backup_spinner)
    content.append(controls)

    win._snapshot_list = Gtk.ListBox()
    win._snapshot_list.set_selection_mode(Gtk.SelectionMode.NONE)
    win._snapshot_list.add_css_class("boxed-list")
    clamp = Adw.Clamp(maximum_size=900)
    clamp.set_child(win._snapshot_list)
    content.append(clamp)
    win._backup_stack.add_named(content, "content")

    root.append(win._backup_stack)
    return root


def refresh(win: Any, *, show_spinner: bool = False, privileged: bool = False) -> None:
    if show_spinner:
        win._backup_spinner.set_visible(True)
    if privileged:
        show_toast(
            win._toast_overlay,
            i18n.t("load_snapshots_admin"),
            timeout=4,
        )

    def work() -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        st = backup.status()
        snaps: list[dict[str, Any]] = []
        list_error = ""
        if st.get("available"):
            try:
                snaps = backup.list_snapshots(privileged=privileged)
                list_error = ""
            except backup.BackupError as exc:
                snaps = []
                list_error = str(exc)
        return st, snaps, list_error

    def done(result: Any, error: BaseException | None) -> None:
        win._backup_spinner.set_visible(False)
        if error is not None:
            show_toast(win._toast_overlay, f"{i18n.t('snapshots')}: {error}")
            win._backup_status_page.set_title(i18n.t("snapshots"))
            win._backup_status_page.set_description(str(error))
            win._backup_stack.set_visible_child_name("status")
            return
        st, snaps, list_error = result
        if not st.get("available"):
            win._backup_status_page.set_icon_name("dialog-warning-symbolic")
            win._backup_status_page.set_title(i18n.t("snapshots"))
            win._backup_status_page.set_description(
                st.get("message") or i18n.t("snapshots_desc")
            )
            win._backup_stack.set_visible_child_name("status")
            return

        win._backup_stack.set_visible_child_name("content")
        status_msg = str(st.get("message") or "").strip()
        if list_error:
            status_msg = list_error
        elif snaps:
            status_msg = i18n.t("snapshots_n", count=len(snaps))
        backend = str(st.get("backend") or "?")
        if hasattr(win, "_btrfs_assistant_btn"):
            win._btrfs_assistant_btn.set_visible(bool(st.get("btrfs_assistant")))
        win._backup_status.set_text(f"{i18n.t('backend')}: {backend} — {status_msg}")
        win._clear_listbox(win._snapshot_list)
        if not snaps:
            row = Adw.ActionRow()
            row.set_title(i18n.t("no_snapshot"))
            row.set_subtitle(
                list_error
                or i18n.t("backup_empty_hint", action=i18n.t("load_snapshots_admin"))
            )
            win._snapshot_list.append(row)
            return
        for snap in snaps:
            name = str(snap.get("name") or "")
            row = Adw.ActionRow()
            row.set_title(name or "?")
            row.set_subtitle(
                f"{snap.get('date', '')} · {snap.get('type', snap.get('tags', ''))} · "
                f"{snap.get('description', '')}"
            )
            restore_btn = Gtk.Button(label=i18n.t("backup_restore"))
            restore_btn.add_css_class("destructive-action")
            restore_btn.set_valign(Gtk.Align.CENTER)
            restore_btn.set_sensitive(win._busy_ops == 0)
            restore_btn.connect("clicked", lambda *_a, n=name: confirm_restore(win, n))
            row.add_suffix(restore_btn)
            if snap.get("backend") == "snapper" and name not in {"0", ""}:
                del_btn = Gtk.Button(label=i18n.t("backup_delete"))
                del_btn.set_valign(Gtk.Align.CENTER)
                del_btn.connect("clicked", lambda *_a, n=name: confirm_delete(win, n))
                row.add_suffix(del_btn)
            win._snapshot_list.append(row)

    run_in_thread(work, done)


def confirm_snapshot(win: Any) -> None:
    confirm_dialog(
        win,
        i18n.t("create_snapshot"),
        i18n.t("snapshots_desc"),
        confirm_label=i18n.t("create"),
        destructive=False,
        on_confirm=lambda: _do_create(win),
    )


def _do_create(win: Any) -> None:
    win._set_busy(True)
    show_toast(win._toast_overlay, i18n.t("snapshot_creating"), timeout=5)

    def work() -> dict[str, Any]:
        return backup.create_snapshot(i18n.t("snapshot_comment"))

    def done(_result: Any, error: BaseException | None) -> None:
        win._set_busy(False)
        if error is not None:
            show_toast(win._toast_overlay, str(error))
            return
        show_toast(win._toast_overlay, i18n.t("snapshot_created"))
        refresh(win, privileged=True)

    run_in_thread(work, done)


def confirm_restore(win: Any, name: str) -> None:
    if not name:
        show_toast(win._toast_overlay, i18n.t("backup_invalid"))
        return
    confirm_dialog(
        win,
        i18n.t("backup_restore_title", name=name),
        i18n.t("backup_restore_body"),
        confirm_label=i18n.t("backup_restore"),
        destructive=True,
        on_confirm=lambda: _do_restore(win, name),
    )


def _do_restore(win: Any, name: str) -> None:
    win._set_busy(True)
    show_toast(win._toast_overlay, i18n.t("backup_restoring", name=name), timeout=8)

    def work() -> dict[str, Any]:
        return backup.restore_snapshot(name)

    def done(_result: Any, error: BaseException | None) -> None:
        win._set_busy(False)
        if error is not None:
            show_toast(win._toast_overlay, str(error))
            return
        show_toast(win._toast_overlay, i18n.t("backup_restore_done"), timeout=8)
        refresh(win, privileged=True)

    run_in_thread(work, done)


def open_btrfs_assistant(win: Any) -> None:
    try:
        backup.open_btrfs_assistant()
    except backup.BackupError as exc:
        show_toast(win._toast_overlay, str(exc))


def confirm_delete(win: Any, name: str) -> None:
    confirm_dialog(
        win,
        i18n.t("backup_delete_title", name=name),
        i18n.t("backup_delete_body"),
        confirm_label=i18n.t("backup_delete"),
        destructive=True,
        on_confirm=lambda: _do_delete(win, name),
    )


def _do_delete(win: Any, name: str) -> None:
    win._set_busy(True)

    def work() -> dict[str, Any]:
        return backup.delete_snapshot(name)

    def done(_result: Any, error: BaseException | None) -> None:
        win._set_busy(False)
        if error is not None:
            show_toast(win._toast_overlay, str(error))
            return
        show_toast(win._toast_overlay, i18n.t("backup_deleted", name=name))
        refresh(win, privileged=True)

    run_in_thread(work, done)
