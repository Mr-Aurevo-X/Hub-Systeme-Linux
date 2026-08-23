# SPDX-License-Identifier: GPL-3.0-or-later
"""Dashboard page: hero summary, clickable gauges, sparklines, details, top procs."""

from __future__ import annotations

import time
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from core import alerts, health, i18n, link_status, monitoring, process, settings as app_settings
from core import backup as backup_mod
from core import smart as smart_mod
from ui.adw_compat import make_message_dialog
from ui.components import (
    CircularGauge,
    CoreBars,
    MetricRow,
    Sparkline,
    confirm_dialog,
    run_in_thread,
)


def _wrap_gauge(child: Gtk.Widget, *, on_click: Any = None) -> Gtk.Widget:
    frame = Gtk.Frame()
    frame.add_css_class("gauge-card")
    frame.add_css_class("dashboard-gauge")
    if on_click is not None:
        btn = Gtk.Button()
        btn.add_css_class("flat")
        btn.add_css_class("dashboard-gauge-btn")
        btn.set_child(child)
        btn.connect("clicked", lambda *_: on_click())
        frame.set_child(btn)
    else:
        frame.set_child(child)
    return frame


def _section(title: str, child: Gtk.Widget) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    label = Gtk.Label(label=title, xalign=0)
    label.add_css_class("title-4")
    box.append(label)
    box.append(child)
    return box


def _spark_card(title: str, spark: Sparkline) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.add_css_class("metric-card")
    lbl = Gtk.Label(label=title, xalign=0)
    lbl.add_css_class("caption")
    box.append(lbl)
    box.append(spark)
    return box


def _root_disk_percent(disks: dict[str, Any]) -> float | None:
    for part in disks.get("partitions") or []:
        if part.get("mountpoint") == "/":
            try:
                return float(part.get("percent") or 0)
            except (TypeError, ValueError):
                return None
    parts = disks.get("partitions") or []
    if not parts:
        return None
    try:
        return float(parts[0].get("percent") or 0)
    except (TypeError, ValueError):
        return None


def _cpu_temp_c(cpu: dict[str, Any]) -> float | None:
    temps = cpu.get("temperatures_c") or []
    if not temps:
        return None
    try:
        return float(temps[0].get("current"))
    except (TypeError, ValueError, IndexError):
        return None


def build(win: Any) -> Gtk.Widget:
    """Build dashboard widgets; stores references on ``win``."""
    scrolled = Gtk.ScrolledWindow()
    clamp = Adw.Clamp(maximum_size=1200)
    clamp.set_margin_top(12)
    clamp.set_margin_bottom(24)
    clamp.set_margin_start(18)
    clamp.set_margin_end(18)
    clamp.add_css_class("dashboard-root")

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)

    # Alert banner
    banner_cls = getattr(Adw, "Banner", None)
    if banner_cls is not None:
        win._dash_banner = banner_cls.new("")
        win._dash_banner.set_revealed(False)
        win._dash_banner.set_button_label(i18n.t("dash_view_processes"))
        win._dash_banner.connect("button-clicked", lambda *_: win._goto_page("processes"))
        box.append(win._dash_banner)
    else:
        win._dash_banner = None
        win._dash_alert_row = Adw.ActionRow(title=i18n.t("alerts"), subtitle="")
        win._dash_alert_row.set_visible(False)
        win._dash_alert_row.set_activatable(True)
        win._dash_alert_row.connect(
            "activated", lambda *_: present_alert_history_dialog(win)
        )
        alert_btn = Gtk.Button(label=i18n.t("dash_view_processes"))
        alert_btn.set_valign(Gtk.Align.CENTER)
        alert_btn.connect("clicked", lambda *_: win._goto_page("processes"))
        win._dash_alert_row.add_suffix(alert_btn)
        box.append(win._dash_alert_row)

    # Hero system group
    hero = Adw.PreferencesGroup()
    hero.add_css_class("dashboard-hero")
    hero.set_title(i18n.t("dash_system"))
    win._link_status_label = Gtk.Label(label=link_status.summary_line(), xalign=0)
    win._link_status_label.add_css_class("dim-label")
    win._link_status_label.set_wrap(True)
    box.append(win._link_status_label)
    win._health_row = Adw.ActionRow(title=i18n.t("health_title"), subtitle="—")
    win._health_row.set_activatable(True)
    win._health_row.connect("activated", lambda *_: win._show_health_dialog())
    win._alerts_history_row = Adw.ActionRow(title=i18n.t("alerts_history"), subtitle="—")
    win._alerts_history_row.set_activatable(True)
    win._alerts_history_row.connect(
        "activated", lambda *_: present_alert_history_dialog(win)
    )
    win._sys_host_row = Adw.ActionRow(title=i18n.t("dash_host"), subtitle="—")
    win._sys_kernel_row = Adw.ActionRow(title=i18n.t("dash_kernel"), subtitle="—")
    win._sys_uptime_row = Adw.ActionRow(title=i18n.t("dash_uptime"), subtitle="—")
    win._sys_load_row = Adw.ActionRow(title=i18n.t("dash_load"), subtitle="—")
    win._sys_batt_row = Adw.ActionRow(title=i18n.t("dash_battery"), subtitle="—")
    win._backup_reminder_row = Adw.ActionRow(title=i18n.t("dash_backup_reminder"), subtitle="—")
    win._backup_reminder_row.set_activatable(True)
    win._backup_reminder_row.connect("activated", lambda *_: win._goto_page("backup"))
    win._smart_row = Adw.ActionRow(title=i18n.t("dash_smart"), subtitle="—")
    win._smart_row.set_activatable(True)
    win._smart_row.connect("activated", lambda *_: present_smart_dialog(win))
    win._smart_items = []
    for row in (
        win._health_row,
        win._alerts_history_row,
        win._sys_host_row,
        win._sys_kernel_row,
        win._sys_uptime_row,
        win._sys_load_row,
        win._sys_batt_row,
        win._backup_reminder_row,
        win._smart_row,
    ):
        hero.add(row)
    box.append(hero)

    # Four gauges
    gauges = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
    gauges.set_halign(Gtk.Align.CENTER)
    gauges.set_homogeneous(True)
    win._cpu_gauge = CircularGauge(i18n.t("dash_cpu"), size=120)
    win._ram_gauge = CircularGauge(i18n.t("dash_ram"), size=120)
    win._ram_gauge.set_accent(0.45, 0.85, 0.55)
    win._disk_gauge = CircularGauge(i18n.t("dash_disk"), size=120)
    win._disk_gauge.set_accent(0.95, 0.72, 0.35)
    win._temp_gauge = CircularGauge(i18n.t("dash_temp"), size=120)
    win._temp_gauge.set_accent(0.95, 0.45, 0.40)
    gauges.append(_wrap_gauge(win._cpu_gauge, on_click=lambda: win._goto_page("processes")))
    gauges.append(_wrap_gauge(win._ram_gauge, on_click=lambda: win._goto_page("processes")))
    gauges.append(_wrap_gauge(win._disk_gauge, on_click=lambda: win._goto_page("cleaner")))
    gauges.append(_wrap_gauge(win._temp_gauge, on_click=lambda: win._goto_page("processes")))
    box.append(gauges)

    # Sparklines
    sparklines = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    sparklines.set_homogeneous(True)
    win._cpu_spark = Sparkline()
    win._cpu_spark.set_accent(0.35, 0.78, 0.98)
    win._ram_spark = Sparkline()
    win._ram_spark.set_accent(0.45, 0.85, 0.55)
    win._net_spark = Sparkline()
    win._net_spark.set_accent(0.95, 0.72, 0.35)
    sparklines.append(_spark_card(i18n.t("dash_hist_cpu"), win._cpu_spark))
    sparklines.append(_spark_card(i18n.t("dash_hist_ram"), win._ram_spark))
    sparklines.append(_spark_card(i18n.t("dash_hist_net"), win._net_spark))
    box.append(sparklines)

    # Details + top processes
    split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
    split.set_homogeneous(True)

    left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

    win._cpu_details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    win._cpu_details_box.add_css_class("metric-card")
    win._cpu_freq_row = MetricRow(i18n.t("dash_freq"), "—")
    win._cpu_temp_row = MetricRow(i18n.t("dash_temperature"), "—")
    win._cpu_cores_row = MetricRow(i18n.t("dash_cores"), "—")
    for row in (win._cpu_freq_row, win._cpu_temp_row, win._cpu_cores_row):
        win._cpu_details_box.append(row)
    win._core_bars = CoreBars()
    win._cpu_details_box.append(win._core_bars)
    left.append(_section(i18n.t("dash_cpu_details"), win._cpu_details_box))

    win._ram_details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    win._ram_details_box.add_css_class("metric-card")
    win._ram_used_row = MetricRow(i18n.t("dash_used"), "—")
    win._ram_free_row = MetricRow(i18n.t("dash_available"), "—")
    win._swap_row = MetricRow(i18n.t("dash_swap"), "—")
    for row in (win._ram_used_row, win._ram_free_row, win._swap_row):
        win._ram_details_box.append(row)
    left.append(_section(i18n.t("dash_memory"), win._ram_details_box))

    win._disk_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    win._disk_box.add_css_class("metric-card")
    win._disk_io_row = MetricRow(i18n.t("dash_disk_io"), "—")
    win._disk_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    win._disk_box.append(win._disk_io_row)
    win._disk_box.append(win._disk_list)
    left.append(_section(i18n.t("dash_disks"), win._disk_box))

    win._net_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    win._net_box.add_css_class("metric-card")
    win._net_down_row = MetricRow(i18n.t("dash_download"), "—")
    win._net_up_row = MetricRow(i18n.t("dash_upload"), "—")
    win._iface_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    for row in (win._net_down_row, win._net_up_row):
        win._net_box.append(row)
    iface_label = Gtk.Label(label=i18n.t("dash_interfaces"), xalign=0)
    iface_label.add_css_class("caption")
    win._net_box.append(iface_label)
    win._net_box.append(win._iface_list)
    right.append(_section(i18n.t("dash_network"), win._net_box))

    win._gpu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    win._gpu_box.add_css_class("metric-card")
    win._gpu_name_row = MetricRow(i18n.t("dash_gpu"), i18n.t("dash_na"))
    win._gpu_busy_row = MetricRow(i18n.t("dash_load_gpu"), "—")
    win._gpu_mem_row = MetricRow(i18n.t("dash_gpu_mem"), "—")
    win._gpu_empty = Gtk.Label(label=i18n.t("dash_unavailable"), xalign=0)
    win._gpu_empty.add_css_class("caption")
    win._gpu_empty.set_visible(False)
    for row in (win._gpu_name_row, win._gpu_busy_row, win._gpu_mem_row):
        win._gpu_box.append(row)
    win._gpu_box.append(win._gpu_empty)
    right.append(_section(i18n.t("dash_gpu_section"), win._gpu_box))

    win._sensors_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    win._sensors_box.add_css_class("metric-card")
    win._sensors_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    win._sensors_empty = Gtk.Label(label=i18n.t("dash_unavailable"), xalign=0)
    win._sensors_empty.add_css_class("caption")
    win._sensors_box.append(win._sensors_list)
    win._sensors_box.append(win._sensors_empty)
    right.append(_section(i18n.t("dash_sensors"), win._sensors_box))

    # Top processes card
    win._top_procs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    win._top_procs_box.add_css_class("metric-card")
    win._top_procs_list = Gtk.ListBox()
    win._top_procs_list.set_selection_mode(Gtk.SelectionMode.NONE)
    win._top_procs_list.add_css_class("boxed-list")
    win._top_procs_box.append(win._top_procs_list)
    more_btn = Gtk.Button(label=i18n.t("dash_view_processes"))
    more_btn.add_css_class("flat")
    more_btn.set_halign(Gtk.Align.END)
    more_btn.connect("clicked", lambda *_: win._goto_page("processes"))
    win._top_procs_box.append(more_btn)
    right.append(_section(i18n.t("dash_top_procs"), win._top_procs_box))

    split.append(left)
    split.append(right)
    box.append(split)

    clamp.set_child(box)
    scrolled.set_child(clamp)

    # Kick off top-procs refresh shortly after build
    win._top_procs_busy = False
    return scrolled


def _update_metric_list(
    win: Any,
    container: Gtk.Box,
    store: list[MetricRow],
    items: list[tuple[str, str]],
) -> None:
    while len(store) < len(items):
        row = MetricRow("—", "—")
        store.append(row)
        container.append(row)
    for idx, row in enumerate(store):
        if idx < len(items):
            key, value = items[idx]
            row.set_key(key)
            row.set_value(value)
            row.set_visible(True)
        else:
            row.set_visible(False)


def _refresh_top_procs(win: Any) -> None:
    import time

    if getattr(win, "_top_procs_busy", False):
        return
    now = time.monotonic()
    last = float(getattr(win, "_top_procs_last", 0.0) or 0.0)
    if now - last < 5.0:
        return
    win._top_procs_last = now
    win._top_procs_busy = True

    def work() -> list[dict[str, Any]]:
        return process.list_processes(limit=5)

    def done(result: Any, error: BaseException | None) -> None:
        win._top_procs_busy = False
        if not hasattr(win, "_top_procs_list"):
            return
        while True:
            row = win._top_procs_list.get_row_at_index(0)
            if row is None:
                break
            win._top_procs_list.remove(row)
        if error is not None:
            empty = Adw.ActionRow(title=i18n.t("dash_unavailable"), subtitle=str(error)[:80])
            win._top_procs_list.append(empty)
            return
        rows = list(result or [])
        if not rows:
            win._top_procs_list.append(
                Adw.ActionRow(title=i18n.t("dash_no_procs"), subtitle="—")
            )
            return
        for item in rows:
            name = str(item.get("name") or "?")
            pid = item.get("pid", "?")
            cpu = float(item.get("cpu") or 0)
            ram = float(item.get("ram_mib") or 0)
            row = Adw.ActionRow()
            row.set_title(name)
            row.set_subtitle(f"PID {pid} · CPU {cpu:.1f}% · RAM {ram:.0f} MiB")
            row.set_activatable(True)
            row.connect("activated", lambda *_: win._goto_page("processes"))
            win._top_procs_list.append(row)

    run_in_thread(work, done)


def update(win: Any, metrics: dict[str, Any]) -> None:
    """Push metrics into dashboard widgets owned by ``win``."""
    if not hasattr(win, "_cpu_gauge"):
        return

    link_label = getattr(win, "_link_status_label", None)
    if link_label is not None:
        link_label.set_text(link_status.summary_line())

    cpu = metrics.get("cpu", {})
    ram = metrics.get("ram", {})
    disks = metrics.get("disks", {})
    net = metrics.get("network", {})
    gpu = metrics.get("gpu", {})
    system = metrics.get("system") or {}
    history = metrics.get("history") or {}

    win._cpu_gauge.set_value(cpu.get("percent_total", 0))
    win._ram_gauge.set_value(ram.get("percent", 0))

    disk_pct = _root_disk_percent(disks)
    if disk_pct is None:
        win._disk_gauge.set_unavailable(i18n.t("dash_na"))
    else:
        win._disk_gauge.set_value(disk_pct)

    temp_c = _cpu_temp_c(cpu)
    if temp_c is None:
        win._temp_gauge.set_unavailable(i18n.t("dash_na"))
        win._cpu_temp_row.set_value(i18n.t("dash_na"))
    else:
        gauge_pct = max(0.0, min(100.0, (temp_c - 30.0) * (100.0 / 70.0)))
        win._temp_gauge.set_value(gauge_pct, display=f"{temp_c:.0f}°")
        win._cpu_temp_row.set_value(f"{temp_c:.1f} °C")

    win._cpu_spark.set_values(list(history.get("cpu") or []))
    win._ram_spark.set_values(list(history.get("ram") or []))
    win._net_spark.set_values(list(history.get("net_down") or []))

    freqs = cpu.get("frequencies_mhz") or []
    if freqs:
        cur = freqs[0].get("current", 0)
        win._cpu_freq_row.set_value(f"{cur:.0f} MHz")
    else:
        win._cpu_freq_row.set_value("—")

    win._cpu_cores_row.set_value(
        f"{cpu.get('physical_cores', 0)} phys. / {cpu.get('logical_cores', 0)} log."
    )
    win._core_bars.set_values(list(cpu.get("percent_per_core") or []))

    win._ram_used_row.set_value(
        f"{ram.get('used_gib', 0):.2f} / {ram.get('total_gib', 0):.2f} Go"
    )
    win._ram_free_row.set_value(f"{ram.get('free_gib', 0):.2f} Go")
    win._swap_row.set_value(
        f"{ram.get('swap_used_gib', 0):.2f} / {ram.get('swap_total_gib', 0):.2f} Go "
        f"({ram.get('swap_percent', 0):.0f}%)"
    )
    win._disk_io_row.set_value(
        f"↓ {disks.get('io_read_mibs', 0):.2f} Mo/s  ↑ {disks.get('io_write_mibs', 0):.2f} Mo/s"
    )

    disk_items: list[tuple[str, str]] = []
    for part in disks.get("partitions") or []:
        disk_items.append(
            (
                f"{part.get('mountpoint')} ({part.get('device')})",
                f"{part.get('free_gib', 0):.1f} Go libres / {part.get('total_gib', 0):.1f} Go "
                f"({part.get('percent', 0):.0f}%)",
            )
        )
    _update_metric_list(win, win._disk_list, win._disk_rows, disk_items)

    win._net_down_row.set_value(f"{net.get('download_mibs', 0):.2f} Mo/s")
    win._net_up_row.set_value(f"{net.get('upload_mibs', 0):.2f} Mo/s")

    iface_items: list[tuple[str, str]] = []
    for iface in net.get("interfaces") or []:
        addrs = list(iface.get("ipv4") or []) + list(iface.get("ipv6") or [])
        addr_txt = ", ".join(addrs[:3]) if addrs else i18n.t("dash_no_ip")
        state = "up" if iface.get("is_up") else "down"
        iface_items.append((str(iface.get("name")), f"{state} · {addr_txt}"))
    _update_metric_list(win, win._iface_list, win._iface_rows, iface_items)

    sensor_items: list[tuple[str, str]] = []
    for sensor in metrics.get("sensors") or []:
        label = str(sensor.get("label") or sensor.get("kind") or "?")
        value = sensor.get("value")
        unit = sensor.get("unit") or ""
        if value is None:
            continue
        sensor_items.append((label, f"{float(value):.1f} {unit}".strip()))
    if sensor_items:
        win._sensors_empty.set_visible(False)
        _update_metric_list(win, win._sensors_list, win._sensor_rows, sensor_items[:24])
    else:
        _update_metric_list(win, win._sensors_list, win._sensor_rows, [])
        win._sensors_empty.set_visible(True)

    hostname = system.get("hostname") or metrics.get("hostname") or "—"
    win._sys_host_row.set_subtitle(str(hostname))
    win._sys_kernel_row.set_subtitle(str(system.get("kernel") or "—"))
    win._sys_uptime_row.set_subtitle(monitoring.format_uptime(metrics.get("boot_time", 0)))
    loadavg = system.get("loadavg") or []
    if loadavg:
        win._sys_load_row.set_subtitle(" / ".join(f"{v:.2f}" for v in loadavg))
    else:
        win._sys_load_row.set_subtitle("—")
    batt = system.get("battery")
    if batt:
        plug = i18n.t("dash_ac") if batt.get("plugged") else i18n.t("dash_on_battery")
        win._sys_batt_row.set_subtitle(
            f"{batt.get('percent', 0):.0f}% · {plug} · {batt.get('time_left', '—')}"
        )
        win._sys_batt_row.set_visible(True)
    else:
        win._sys_batt_row.set_visible(False)

    reminder = backup_mod.reminder_status()
    if reminder.get("visible"):
        win._backup_reminder_row.set_visible(True)
        if reminder.get("needs_admin"):
            win._backup_reminder_row.set_subtitle(i18n.t("dash_backup_snapper"))
        elif reminder.get("ok"):
            win._backup_reminder_row.set_subtitle(
                f"{i18n.t('dash_backup_ok')} ({reminder.get('count', 0)})"
            )
        else:
            win._backup_reminder_row.set_subtitle(i18n.t("dash_backup_stale"))
    else:
        win._backup_reminder_row.set_visible(False)

    now = time.monotonic()
    last_extra = float(getattr(win, "_dash_extra_last", 0.0) or 0.0)
    if now - last_extra >= 120.0:
        win._dash_extra_last = now
        if smart_mod.is_available():
            try:
                items = smart_mod.summarize()
                win._smart_items = list(items)
                summary = smart_mod.status_summary(items)
                if summary["kind"] == "bad":
                    win._smart_row.set_subtitle(summary["text"])
                elif summary["kind"] == "ok":
                    win._smart_row.set_subtitle(i18n.t("dash_smart_ok"))
                else:
                    win._smart_row.set_subtitle(i18n.t("dash_smart_none"))
                win._smart_row.set_visible(True)
            except (OSError, RuntimeError, smart_mod.SmartError):
                win._smart_items = []
                win._smart_row.set_subtitle(i18n.t("dash_smart_error"))
                win._smart_row.set_visible(True)
        else:
            win._smart_items = []
            win._smart_row.set_subtitle(i18n.t("dash_smart_unavailable"))
            win._smart_row.set_visible(True)
    elif not hasattr(win, "_smart_row"):
        pass

    devices = gpu.get("devices") or []
    if devices:
        win._gpu_empty.set_visible(False)
        for row in (win._gpu_name_row, win._gpu_busy_row, win._gpu_mem_row):
            row.set_visible(True)
        dev = devices[0]
        win._gpu_name_row.set_value(f"{dev.get('vendor')} — {dev.get('name')}")
        win._gpu_busy_row.set_value(f"{dev.get('busy_percent', 0):.0f} %")
        temp = dev.get("temperature_c")
        mem = f"{dev.get('mem_used_mib', 0):.0f} / {dev.get('mem_total_mib', 0):.0f} Mio"
        if temp is not None:
            mem = f"{mem} · {temp:.0f} °C"
        win._gpu_mem_row.set_value(mem)
    else:
        for row in (win._gpu_name_row, win._gpu_busy_row, win._gpu_mem_row):
            row.set_visible(False)
        win._gpu_empty.set_visible(True)

    # Banner alerts
    messages = app_settings.evaluate_alerts(metrics, win._settings)
    report = health.evaluate(metrics, win._settings)
    win._health_report = report
    health_row = getattr(win, "_health_row", None)
    if health_row is not None:
        recs = report.get("recommendations") or []
        if recs:
            health_row.set_subtitle(
                i18n.t(
                    "health_subtitle_issues",
                    score=report["score"],
                    grade=report["grade"],
                    count=len(recs),
                )
            )
        else:
            health_row.set_subtitle(
                i18n.t(
                    "health_subtitle_ok",
                    score=report["score"],
                    grade=report["grade"],
                )
            )
    history_row = getattr(win, "_alerts_history_row", None)
    if history_row is not None:
        history = alerts.format_history_entries(list(win._settings.get("alert_history") or []))
        if history:
            last = history[-1]
            history_row.set_subtitle(f"{last['when']} · {last['body']}"[:160])
        else:
            history_row.set_subtitle(i18n.t("alerts_history_empty"))
    banner = getattr(win, "_dash_banner", None)
    if banner is not None:
        if messages:
            banner.set_title(" · ".join(messages)[:200])
            banner.set_revealed(True)
        else:
            banner.set_revealed(False)
    else:
        alert_row = getattr(win, "_dash_alert_row", None)
        if alert_row is not None:
            if messages:
                alert_row.set_subtitle(" · ".join(messages)[:200])
                alert_row.set_visible(True)
            else:
                alert_row.set_visible(False)

    _refresh_top_procs(win)


def _rows_extra_child(rows: list[tuple[str, str]]) -> Gtk.Widget:
    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.NONE)
    listbox.add_css_class("boxed-list")
    for title, subtitle in rows:
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        row.set_activatable(False)
        listbox.append(row)
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_min_content_height(160)
    scrolled.set_max_content_height(360)
    scrolled.set_child(listbox)
    return scrolled


def present_alert_history_dialog(win: Any) -> None:
    entries = alerts.format_history_entries(list(win._settings.get("alert_history") or []))
    extra = None
    body = i18n.t("alerts_history_empty")
    if entries:
        body = ""
        extra = _rows_extra_child([(item["when"], item["body"]) for item in entries])
    dialog = make_message_dialog(win, i18n.t("alerts_history"), body, extra_child=extra)
    dialog.add_response("close", i18n.t("update_close"))
    if entries:
        dialog.add_response("clear", i18n.t("alerts_history_clear"))
    dialog.set_default_response("close")
    dialog.set_close_response("close")

    def on_response(_dialog: object, response: str) -> None:
        if response != "clear":
            return
        confirm_dialog(
            win,
            i18n.t("alerts_history"),
            i18n.t("alerts_history_clear"),
            confirm_label=i18n.t("alerts_history_clear"),
            on_confirm=lambda: _clear_alert_history(win),
        )

    dialog.connect("response", on_response)
    dialog.present(win)


def _clear_alert_history(win: Any) -> None:
    win._settings["alert_history"] = []
    app_settings.save_settings(win._settings)


def present_smart_dialog(win: Any) -> None:
    items = list(getattr(win, "_smart_items", None) or [])
    if not items and smart_mod.is_available():
        try:
            items = smart_mod.summarize()
            win._smart_items = list(items)
        except (OSError, RuntimeError, smart_mod.SmartError):
            items = []
    rows = smart_mod.format_dialog_rows(items)
    extra = None
    body = i18n.t("dash_smart_empty")
    if rows:
        body = ""
        extra = _rows_extra_child(
            [
                (
                    item["device"],
                    item["detail"] or i18n.t("dash_smart_error"),
                )
                for item in rows
            ]
        )
    dialog = make_message_dialog(win, i18n.t("dash_smart_dialog_title"), body, extra_child=extra)
    dialog.add_response("close", i18n.t("update_close"))
    dialog.set_default_response("close")
    dialog.set_close_response("close")
    dialog.present(win)
