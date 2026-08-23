# SPDX-License-Identifier: GPL-3.0-or-later
"""Machine sheet page — read-only inventory + export."""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from core import i18n, machine_sheet
from ui.components import run_in_thread, show_toast


def _row(title: str) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title, subtitle="—")
    row.set_activatable(False)
    return row


def _add_group(page: Adw.PreferencesPage, title: str, rows: list[Adw.ActionRow]) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup()
    group.set_title(title)
    for row in rows:
        group.add(row)
    page.add(group)
    return group


def build(win: Any) -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    bar.add_css_class("page-toolbar")
    win._machine_spinner = Gtk.Spinner()
    win._machine_spinner.set_visible(False)
    refresh_btn = Gtk.Button(label=i18n.t("refresh"))
    refresh_btn.connect("clicked", lambda *_: refresh(win, show_spinner=True))
    copy_btn = Gtk.Button(label=i18n.t("machine_copy"))
    copy_btn.connect("clicked", lambda *_: copy_summary(win))
    json_btn = Gtk.Button(label=i18n.t("machine_export_json"))
    json_btn.connect("clicked", lambda *_: export_sheet(win, "json"))
    csv_btn = Gtk.Button(label=i18n.t("machine_export_csv"))
    csv_btn.connect("clicked", lambda *_: export_sheet(win, "csv"))
    bar.append(refresh_btn)
    bar.append(copy_btn)
    bar.append(json_btn)
    bar.append(csv_btn)
    bar.append(win._machine_spinner)
    root.append(bar)

    page = Adw.PreferencesPage()
    win._machine_host = _row(i18n.t("machine_hostname"))
    win._machine_os = _row(i18n.t("machine_os"))
    win._machine_version = _row(i18n.t("machine_version"))
    win._machine_kernel = _row(i18n.t("machine_kernel"))
    win._machine_arch = _row(i18n.t("machine_arch"))
    _add_group(
        page,
        i18n.t("machine_identity"),
        [
            win._machine_host,
            win._machine_os,
            win._machine_version,
            win._machine_kernel,
            win._machine_arch,
        ],
    )

    win._machine_cpu = _row(i18n.t("machine_cpu"))
    win._machine_ram = _row(i18n.t("machine_ram"))
    win._machine_gpu = _row(i18n.t("machine_gpu"))
    _add_group(
        page,
        i18n.t("machine_hardware"),
        [win._machine_cpu, win._machine_ram, win._machine_gpu],
    )

    win._machine_storage_group = Adw.PreferencesGroup()
    win._machine_storage_group.set_title(i18n.t("machine_storage"))
    win._machine_storage_rows: list[Adw.ActionRow] = []
    page.add(win._machine_storage_group)

    win._machine_gateway = _row(i18n.t("machine_gateway"))
    win._machine_dns = _row(i18n.t("machine_dns"))
    win._machine_net_group = Adw.PreferencesGroup()
    win._machine_net_group.set_title(i18n.t("machine_network"))
    win._machine_net_group.add(win._machine_gateway)
    win._machine_net_group.add(win._machine_dns)
    win._machine_iface_rows: list[Adw.ActionRow] = []
    page.add(win._machine_net_group)

    win._machine_uptime = _row(i18n.t("machine_uptime"))
    win._machine_tz = _row(i18n.t("machine_timezone"))
    win._machine_dt = _row(i18n.t("machine_datetime"))
    _add_group(
        page,
        i18n.t("machine_time"),
        [win._machine_uptime, win._machine_tz, win._machine_dt],
    )

    win._machine_pending = _row(i18n.t("machine_pending"))
    updates = Adw.PreferencesGroup()
    updates.set_title(i18n.t("machine_updates"))
    updates.set_description(i18n.t("machine_updates_hint"))
    updates.add(win._machine_pending)
    page.add(updates)

    win._machine_snap = _row(i18n.t("machine_snap_detected"))
    snaps = Adw.PreferencesGroup()
    snaps.set_title(i18n.t("machine_snapshots"))
    snaps.add(win._machine_snap)
    page.add(snaps)

    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    clamp = Adw.Clamp(maximum_size=900)
    clamp.set_margin_start(12)
    clamp.set_margin_end(12)
    clamp.set_margin_bottom(16)
    clamp.set_child(page)
    scroll.set_child(clamp)
    root.append(scroll)
    win._machine_sheet = None
    return root


def _fill_dynamic(group: Adw.PreferencesGroup, store: list[Adw.ActionRow], items: list[tuple[str, str]]) -> None:
    while len(store) < len(items):
        row = _row("—")
        store.append(row)
        group.add(row)
    for idx, row in enumerate(store):
        if idx < len(items):
            title, value = items[idx]
            row.set_title(title)
            row.set_subtitle(value or "—")
            row.set_visible(True)
        else:
            row.set_visible(False)


def render(win: Any, sheet: dict[str, Any]) -> None:
    win._machine_sheet = sheet
    ident = sheet.get("identity") or {}
    win._machine_host.set_subtitle(str(ident.get("hostname") or "—"))
    os_line = str(ident.get("pretty_name") or "—")
    if ident.get("os_id"):
        os_line = f"{os_line} ({ident.get('os_id')})"
    win._machine_os.set_subtitle(os_line)
    win._machine_version.set_subtitle(str(ident.get("version") or "—"))
    win._machine_kernel.set_subtitle(str(ident.get("kernel") or "—"))
    win._machine_arch.set_subtitle(str(ident.get("arch") or "—"))
    cpu = sheet.get("cpu") or {}
    cores = i18n.t("machine_cores", n=cpu.get("logical_cores") or 0)
    win._machine_cpu.set_subtitle(f"{cpu.get('model') or '—'} · {cores}")
    ram = sheet.get("ram") or {}
    win._machine_ram.set_subtitle(
        f"{ram.get('used_gib', 0)} / {ram.get('total_gib', 0)} Gio ({ram.get('percent', 0)}%)"
    )
    gpu = sheet.get("gpu") or {}
    devices = gpu.get("devices") or []
    if devices:
        win._machine_gpu.set_subtitle(
            " · ".join(f"{item.get('vendor') or ''} {item.get('name') or ''}".strip() for item in devices)
        )
    else:
        win._machine_gpu.set_subtitle("—")
    storage_items = [
        (
            str(part.get("mountpoint") or "?"),
            f"{part.get('used_gib', 0)} / {part.get('total_gib', 0)} Gio "
            f"({part.get('percent', 0)}% · {part.get('free_gib', 0)} libre)",
        )
        for part in sheet.get("storage") or []
    ]
    _fill_dynamic(win._machine_storage_group, win._machine_storage_rows, storage_items)
    net = sheet.get("network") or {}
    win._machine_gateway.set_subtitle(str(net.get("gateway") or "—"))
    dns = ", ".join(net.get("dns") or []) or "—"
    win._machine_dns.set_subtitle(dns)
    iface_items: list[tuple[str, str]] = []
    for iface in net.get("interfaces") or []:
        addrs = list(iface.get("ipv4") or []) + list(iface.get("ipv6") or [])
        iface_items.append((str(iface.get("name") or "?"), ", ".join(addrs) or "—"))
    _fill_dynamic(win._machine_net_group, win._machine_iface_rows, iface_items)
    tinfo = sheet.get("time") or {}
    win._machine_uptime.set_subtitle(str(tinfo.get("uptime") or "—"))
    win._machine_tz.set_subtitle(str(tinfo.get("timezone") or "—"))
    win._machine_dt.set_subtitle(str(tinfo.get("datetime") or "—"))
    updates = sheet.get("updates") or {}
    win._machine_pending.set_subtitle(str(updates.get("pending", 0)))
    snaps = sheet.get("snapshots") or {}
    yes = i18n.t("machine_yes") if snaps.get("detected") else i18n.t("machine_no")
    win._machine_snap.set_subtitle(f"{yes} ({snaps.get('backend') or 'none'})")


def refresh(win: Any, *, show_spinner: bool = False) -> None:
    if show_spinner:
        win._machine_spinner.set_visible(True)
        win._machine_spinner.start()

    def work() -> dict[str, Any]:
        return machine_sheet.collect_sheet()

    def done(result: Any, error: BaseException | None) -> None:
        win._machine_spinner.stop()
        win._machine_spinner.set_visible(False)
        if error is not None:
            show_toast(win._toast_overlay, i18n.t("machine_error", detail=str(error)))
            return
        render(win, result or {})

    run_in_thread(work, done)


def copy_summary(win: Any) -> None:
    sheet = getattr(win, "_machine_sheet", None)
    if not isinstance(sheet, dict):
        show_toast(win._toast_overlay, i18n.t("conn_no_export"))
        return
    display = Gdk.Display.get_default() if hasattr(Gdk, "Display") else None
    getter = getattr(display, "get_clipboard", None) if display is not None else None
    clipboard = getter() if callable(getter) else None
    setter = getattr(clipboard, "set", None)
    if not callable(setter):
        show_toast(win._toast_overlay, i18n.t("conn_no_clipboard"))
        return
    setter(machine_sheet.to_text(sheet))
    show_toast(win._toast_overlay, i18n.t("machine_copied"))


def export_sheet(win: Any, kind: str) -> None:
    sheet = getattr(win, "_machine_sheet", None)
    if not isinstance(sheet, dict):
        show_toast(win._toast_overlay, i18n.t("conn_no_export"))
        return
    path = machine_sheet.default_export_path(kind)
    payload = machine_sheet.to_json(sheet) if kind == "json" else machine_sheet.to_csv(sheet)

    def work() -> Any:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        return path

    def done(result: Any, error: BaseException | None) -> None:
        if error is not None:
            show_toast(win._toast_overlay, i18n.t("machine_error", detail=str(error)))
            return
        show_toast(win._toast_overlay, i18n.t("machine_exported", path=str(result)))

    run_in_thread(work, done)
