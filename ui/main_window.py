# SPDX-License-Identifier: GPL-3.0-or-later
"""Main application window with sidebar navigation."""

from __future__ import annotations

import signal
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from core import (
    alerts,
    autostart,
    backup,
    cleaner,
    compat,
    connections,
    firewall,
    health,
    i18n,
    jobs,
    logs,
    monitoring,
    network_ctl,
    packages,
    plugins,
    power,
    process,
    report,
    services,
    settings as app_settings,
    updater,
    users,
)
from ui import job_console
from ui import pages as ui_pages
from ui.adw_compat import (
    make_message_dialog,
    make_spin_row,
    make_switch_row,
    response_appearance,
    set_placeholder_text,
)
from ui.components import (
    ActionListRow,
    CircularGauge,
    CoreBars,
    MetricRow,
    Sparkline,
    apply_app_css,
    confirm_dialog,
    debounce,
    make_spinner,
    run_in_thread,
    show_toast,
)
from ui.compat_attr import call_if_present
from ui.page_helpers import make_filter_chips
from ui.nav import NavSidebar, page_titles
from ui.search import present as present_search
from ui_kit.shell import ShellLayout, build_main_layout
from ui_kit.strings import t as kit_t


def _nav_items() -> list[tuple[str, str, str]]:
    return i18n.nav_items()


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        display = updater.app_display_name()
        super().__init__(application=application, title=display)
        self.add_css_class("uni-window")
        self.set_default_size(1200, 780)
        apply_app_css()

        self._settings = app_settings.load_settings()
        i18n.set_language(app_settings.coerce_language(self._settings.get("language")))
        self._nav_items = _nav_items()
        self._last_alert_time = 0.0
        self._last_alert_msgs: set[str] = set()
        self._layout: ShellLayout | None = None

        self._monitor_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._current_page = app_settings.coerce_page(self._settings.get("last_page"))
        self._process_filter = ""
        self._process_sort = "cpu"
        self._process_empty_row: Gtk.Widget | None = None
        self._service_filter = ""
        self._service_chip = "active"  # active | enabled | failed | all
        self._package_filter = ""
        self._package_manager = "all"  # all | apt | flatpak | snap
        self._logs_priority = "all"
        self._logs_grep = ""
        self._logs_text_cache = ""
        self._logs_preset_guard = False
        self._network_chip = "wifi"
        self._connection_items: list[dict[str, Any]] = []
        self._busy_ops = 0
        self._pending_metrics: dict[str, Any] | None = None
        self._metrics_flush_scheduled = False
        self._disk_rows: list[MetricRow] = []
        self._iface_rows: list[MetricRow] = []
        self._sensor_rows: list[MetricRow] = []
        self._process_rows: dict[int, ActionListRow] = {}
        self._process_data_cache: list[dict[str, Any]] = []
        self._service_data_cache: list[dict[str, Any]] = []
        self._package_data_cache: list[dict[str, Any]] = []
        self._privileged_buttons: list[Gtk.Widget] = []
        self._update_in_progress = False
        self._pkg_terminal_open = False

        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        self._build_ui()
        self._install_actions()
        self._show_page(self._current_page)
        # Non-blocking first paint: start monitoring after the window is mapped.
        GLib.idle_add(self._start_monitoring)
        GLib.timeout_add(700, self._check_startup_compatibility)
        if not app_settings.needs_language_prompt(self._settings):
            GLib.timeout_add(2000, self._maybe_check_updates)
        self._logged_mapped = False
        self.connect("map", self._on_window_mapped)
        self.connect("close-request", self._on_close)

    def _on_window_mapped(self, *_args: object) -> None:
        if self._logged_mapped:
            return
        self._logged_mapped = True
        print("fenêtre ouverte", flush=True)
        if app_settings.needs_language_prompt(self._settings):
            GLib.idle_add(self._prompt_language)

    # --- actions / shortcuts ---

    def _install_actions(self) -> None:
        refresh = Gio.SimpleAction.new("refresh", None)
        refresh.connect("activate", lambda *_: self._refresh_current_page())
        self.add_action(refresh)

        prefs = Gio.SimpleAction.new("preferences", None)
        prefs.connect("activate", lambda *_: self._open_preferences())
        self.add_action(prefs)

        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", lambda *_: self._open_legal_kit())
        self.add_action(about)

        search = Gio.SimpleAction.new("search", None)
        search.connect("activate", lambda *_: present_search(self))
        self.add_action(search)

        for idx, (key, _label, _icon) in enumerate(self._nav_items, start=1):
            action = Gio.SimpleAction.new(f"page{idx}", None)
            action.connect("activate", lambda *_a, k=key: self._goto_page(k))
            self.add_action(action)

        app = self.get_application()
        if app is not None:
            app.set_accels_for_action("win.refresh", ["F5"])
            app.set_accels_for_action("win.preferences", ["<Control>comma"])
            app.set_accels_for_action("win.search", ["<Control>k"])
            app.set_accels_for_action("app.quit", ["<Control>q"])
            for idx in range(1, min(10, len(self._nav_items) + 1)):
                app.set_accels_for_action(f"win.page{idx}", [f"<Control>{idx}"])

    def _goto_page(self, key: str) -> None:
        if hasattr(self, "_nav_sidebar"):
            self._nav_sidebar.select_page(key, notify=True)

    def _on_nav_page_selected(self, key: str) -> None:
        self._show_page(key)

    def _on_nav_groups_changed(self, expanded: dict[str, bool]) -> None:
        self._settings["nav_groups_expanded"] = expanded
        app_settings.save_settings(self._settings)

    def _show_health_dialog(self) -> None:
        data = getattr(self, "_health_report", None)
        if not isinstance(data, dict):
            data = health.evaluate({}, self._settings)
        recs = list(data.get("recommendations") or [])
        if recs:
            body = "\n".join(f"• {item.get('label')}" for item in recs)
        else:
            body = i18n.t("health_ok")
        dialog = make_message_dialog(self, i18n.t("health_dialog_title"), body)
        dialog.add_response("close", i18n.t("update_close"))
        first_page = str(recs[0].get("page") or "") if recs else ""
        if first_page:
            dialog.add_response("go", i18n.t("health_open_page"))
            dialog.set_default_response("go")
        else:
            dialog.set_default_response("close")
        dialog.set_close_response("close")

        def on_response(_dialog: object, response: str) -> None:
            if response == "go" and first_page:
                self._goto_page(first_page)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _refresh_current_page(self) -> None:
        key = self._current_page
        if key == "dashboard":
            show_toast(self._toast_overlay, i18n.t("dash_refreshing"), timeout=1)
            return
        if key == "machine":
            self._refresh_machine(show_spinner=True)
        elif key == "fleet":
            self._refresh_fleet(show_spinner=True)
        elif key == "processes":
            self._refresh_processes(show_spinner=True)
        elif key == "services":
            self._refresh_services(show_spinner=True)
        elif key == "cleaner":
            self._refresh_cleaner(show_spinner=True)
        elif key == "disk_usage":
            self._refresh_disk_usage(show_spinner=True)
        elif key == "packages":
            self._refresh_packages(show_spinner=True)
        elif key == "logs":
            self._refresh_logs(show_spinner=True)
        elif key == "autostart":
            self._refresh_autostart(show_spinner=True)
        elif key == "timers":
            self._refresh_timers(show_spinner=True)
        elif key == "network":
            self._refresh_network(show_spinner=True)
        elif key == "security":
            self._refresh_security(show_spinner=True)
        elif key == "tools":
            self._refresh_tools(show_spinner=True)
        elif key == "backup":
            self._refresh_backup(show_spinner=True)
        elif key == "sessions":
            self._refresh_sessions(show_spinner=True)

    def _set_busy(self, busy: bool) -> None:
        self._busy_ops = max(0, self._busy_ops + (1 if busy else -1))
        enabled = self._busy_ops == 0
        for widget in self._privileged_buttons:
            widget.set_sensitive(enabled)
        for row in self._process_rows.values():
            row.set_busy(not enabled)
        if hasattr(self, "_header_spinner"):
            self._header_spinner.set_visible(self._busy_ops > 0)

    def _track_privileged(self, widget: Gtk.Widget) -> Gtk.Widget:
        self._privileged_buttons.append(widget)
        return widget

    # --- layout ---

    def _build_ui(self) -> None:
        self._nav_sidebar = NavSidebar(
            settings=self._settings,
            on_page_selected=self._on_nav_page_selected,
            on_groups_changed=self._on_nav_groups_changed,
        )
        nav_scroll = self._nav_sidebar.widget

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(180)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)

        self._page_builders = ui_pages.builders_for(self)
        self._built_pages: set[str] = set()
        self._ensure_page("dashboard")

        layout = build_main_layout(
            nav_scroll,
            self._stack,
            page_title=i18n.t("dashboard"),
            lang=i18n.get_language(),
        )
        self._header_spinner = make_spinner(size=18)
        self._header_spinner.set_visible(False)
        layout.content_header.pack_end(self._header_spinner)

        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self._refresh_header_btn = refresh_btn
        refresh_btn.set_tooltip_text(f"{i18n.t('refresh')} (F5)")
        refresh_btn.connect("clicked", lambda *_: self._refresh_current_page())
        layout.content_header.pack_end(refresh_btn)

        layout.attach_chrome_buttons(
            self,
            on_check_updates=self._chrome_check_updates,
            on_language_toggle=self._apply_language,
            current_language=i18n.get_language(),
            settings_snapshot=self._settings,
            current_version=updater.local_version(),
            on_settings_save=self._save_prefs_from_kit,
            on_open_preferences=self._open_preferences,
        )
        self._layout = layout
        self._toast_overlay.set_child(layout.widget)
        self._nav_sidebar.select_page(self._current_page, notify=False)

    def _ensure_page(self, key: str) -> Gtk.Widget:
        child = self._stack.get_child_by_name(key)
        if child is not None:
            return child
        builder = self._page_builders.get(key)
        if builder is None:
            raise KeyError(key)
        widget = builder()
        self._stack.add_named(widget, key)
        self._built_pages.add(key)
        return widget

    def _show_page(self, key: str) -> None:
        self._current_page = key
        titles = page_titles()
        if self._layout is not None:
            self._layout.set_page_title(titles.get(key, key))
        if hasattr(self, "_nav_sidebar"):
            self._nav_sidebar.select_page(key, notify=False)
        self._ensure_page(key)
        self._stack.set_visible_child_name(key)
        self._settings["last_page"] = key
        app_settings.save_settings(self._settings)
        if key == "machine":
            self._refresh_machine()
        elif key == "fleet":
            self._refresh_fleet()
        elif key == "processes":
            self._refresh_processes()
        elif key == "services":
            self._refresh_services()
        elif key == "cleaner":
            self._refresh_cleaner()
        elif key == "disk_usage":
            self._refresh_disk_usage()
        elif key == "packages":
            self._refresh_packages()
        elif key == "logs":
            self._refresh_logs()
        elif key == "autostart":
            self._refresh_autostart()
        elif key == "timers":
            self._refresh_timers()
        elif key == "network":
            self._refresh_network()
        elif key == "security":
            self._refresh_security()
        elif key == "tools":
            self._refresh_tools()
        elif key == "backup":
            self._refresh_backup()
        elif key == "sessions":
            self._refresh_sessions()

    def _clear_listbox(self, listbox: Gtk.ListBox) -> None:
        while True:
            row = listbox.get_row_at_index(0)
            if row is None:
                break
            listbox.remove(row)

    def _preserve_scroll(self, scrolled: Gtk.ScrolledWindow) -> tuple[float, Callable[[], None]]:
        vadj = scrolled.get_vadjustment()
        value = vadj.get_value() if vadj is not None else 0.0

        def restore() -> None:
            adj = scrolled.get_vadjustment()
            if adj is not None:
                adj.set_value(value)

        return value, restore

    # --- preferences ---

    def _open_preferences(self) -> None:
        from ui_kit.dialogs import settings as kit_settings

        win = Adw.PreferencesWindow()
        win.set_transient_for(self)
        win.set_modal(True)
        win.set_title(i18n.t("preferences"))

        page = Adw.PreferencesPage()
        page.set_title(i18n.t("preferences"))
        page.set_icon_name("preferences-system-symbolic")

        general = Adw.PreferencesGroup()
        general.set_title(i18n.t("general"))

        alerts_row = make_switch_row()
        alerts_row.set_title(i18n.t("alerts"))
        alerts_row.set_active(bool(self._settings.get("alerts_enabled", True)))
        general.add(alerts_row)
        page.add(general)

        appearance = Adw.PreferencesGroup()
        appearance.set_title(kit_t("appearance", i18n.get_language()))
        appearance.set_description(kit_t("appearance_sub", i18n.get_language()))
        theme_row = ActionListRow(
            kit_t("theme_preset", i18n.get_language()),
            kit_t("appearance_sub", i18n.get_language()),
            button_label=kit_t("preferences", i18n.get_language()),
            button_css="flat",
            on_clicked=lambda: kit_settings.present(
                self,
                self._settings,
                current_version=updater.local_version(),
                lang=i18n.get_language(),
                on_save=self._save_prefs_from_kit,
            ),
        )
        appearance.add(theme_row)
        page.add(appearance)

        updates = Adw.PreferencesGroup()
        updates.set_title(i18n.t("updates"))
        updates.set_description(i18n.t("updates_group_desc"))

        update_row = make_switch_row()
        update_row.set_title(i18n.t("auto_update"))
        update_row.set_subtitle(i18n.t("auto_update_subtitle"))
        update_row.set_active(bool(self._settings.get("auto_update_on_startup", True)))

        def on_auto_update_toggle(_row: Gtk.Widget, *_args: object) -> None:
            self._set_auto_update_enabled(update_row.get_active())

        update_row.connect("notify::active", on_auto_update_toggle)
        updates.add(update_row)
        page.add(updates)

        thresholds = Adw.PreferencesGroup()
        thresholds.set_title(i18n.t("alert_thresholds"))
        th = dict(self._settings.get("thresholds") or app_settings.DEFAULTS["thresholds"])

        def _spin_row(title: str, value: float, *, upper: float = 100.0) -> Gtk.Widget:
            adj = Gtk.Adjustment(
                value=float(value),
                lower=1.0,
                upper=upper,
                step_increment=1.0,
                page_increment=5.0,
            )
            row = make_spin_row(adjustment=adj, digits=0)
            row.set_title(title)
            return row

        cpu_row = _spin_row(i18n.t("cpu_pct"), float(th.get("cpu_percent", 90)))
        ram_row = _spin_row(i18n.t("ram_pct"), float(th.get("ram_percent", 90)))
        temp_row = _spin_row(i18n.t("temp_c"), float(th.get("temp_celsius", 85)), upper=120.0)
        disk_row = _spin_row(i18n.t("disk_pct"), float(th.get("disk_percent", 90)))

        def _refresh_threshold_spins() -> None:
            current = dict(self._settings.get("thresholds") or app_settings.DEFAULTS["thresholds"])
            cpu_row.set_value(float(current.get("cpu_percent", 90)))
            ram_row.set_value(float(current.get("ram_percent", 90)))
            temp_row.set_value(float(current.get("temp_celsius", 85)))
            disk_row.set_value(float(current.get("disk_percent", 90)))

        def _apply_threshold_preset(name: str) -> None:
            app_settings.apply_threshold_profile(self._settings, name)
            app_settings.save_settings(self._settings)
            self._settings = app_settings.load_settings()
            _refresh_threshold_spins()

        preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        preset_box.add_css_class("linked")
        for key, label_key in (
            ("desktop", "threshold_profile_desktop"),
            ("server", "threshold_profile_server"),
            ("vm", "threshold_profile_vm"),
        ):
            btn = Gtk.Button(label=i18n.t(label_key))
            btn.add_css_class("flat")
            btn.connect("clicked", lambda *_a, n=key: _apply_threshold_preset(n))
            preset_box.append(btn)
        if not call_if_present(thresholds, "set_header_suffix", preset_box):
            header_row = Adw.ActionRow(title=i18n.t("threshold_profiles"))
            header_row.add_suffix(preset_box)
            thresholds.add(header_row)
        for row in (cpu_row, ram_row, temp_row, disk_row):
            thresholds.add(row)
        page.add(thresholds)

        save_group = Adw.PreferencesGroup()
        save_btn = Gtk.Button(label=i18n.t("save"))
        save_btn.add_css_class("suggested-action")
        save_btn.set_halign(Gtk.Align.END)
        save_btn.set_margin_top(8)
        save_btn.set_margin_bottom(8)

        def on_save(*_a: object) -> None:
            new_settings = dict(self._settings)
            new_settings.update(
                {
                    "alerts_enabled": alerts_row.get_active(),
                    "auto_update_on_startup": update_row.get_active(),
                    "thresholds": {
                        "cpu_percent": float(cpu_row.get_value()),
                        "ram_percent": float(ram_row.get_value()),
                        "temp_celsius": float(temp_row.get_value()),
                        "disk_percent": float(disk_row.get_value()),
                    },
                }
            )
            app_settings.save_settings(new_settings)
            self._settings = app_settings.load_settings()
            show_toast(self._toast_overlay, i18n.t("prefs_saved"))
            win.close()

        save_btn.connect("clicked", on_save)
        save_group.add(save_btn)
        page.add(save_group)

        win.add(page)
        win.present()

    def _open_legal_kit(self) -> None:
        from ui_kit.dialogs import legal as legal_dialog

        legal_dialog.present(self, i18n.get_language())

    def _save_prefs_from_kit(self, _settings: dict[str, Any]) -> None:
        show_toast(self._toast_overlay, i18n.t("prefs_saved"))

    def _chrome_check_updates(self) -> None:
        self._manual_check_updates()

    def _relabel_sidebar(self) -> None:
        if hasattr(self, "_nav_sidebar"):
            self._nav_sidebar.update_settings(self._settings)
            self._nav_sidebar.relabel()
        titles = page_titles()
        if self._layout is not None:
            self._layout.set_page_title(titles.get(self._current_page, self._current_page))

    def _relabel_header(self) -> None:
        if hasattr(self, "_refresh_header_btn"):
            self._refresh_header_btn.set_tooltip_text(f"{i18n.t('refresh')} (F5)")

    def _prompt_language(self) -> bool:
        if not app_settings.needs_language_prompt(self._settings):
            return False
        dialog = make_message_dialog(self, i18n.t("welcome_lang"), i18n.t("welcome_lang_body"))
        dialog.add_response("fr", "Français")
        dialog.add_response("en", "English")
        dialog.set_response_appearance("fr", response_appearance("SUGGESTED"))

        def on_response(_d: object, response: str) -> None:
            if response not in {"fr", "en"}:
                return
            self._apply_language(response)
            GLib.timeout_add(400, self._maybe_check_updates)

        dialog.connect("response", on_response)
        dialog.present(self)
        return False

    def _apply_language(self, lang: object) -> None:
        code = app_settings.coerce_language(lang)
        same_ui = i18n.get_language() == code and str(self._settings.get("language") or "") == code
        self._settings["language"] = code
        self._settings["language_chosen"] = True
        app_settings.save_settings(self._settings)
        self._settings = app_settings.load_settings()
        if same_ui:
            return
        i18n.set_language(code)
        self._rebuild_pages()
        if self._layout is not None:
            self._layout.update_language_button(code)

    def _rebuild_pages(self) -> None:
        current = self._current_page
        for name in list(self._built_pages):
            child = self._stack.get_child_by_name(name)
            if child is not None:
                self._stack.remove(child)
        self._built_pages.clear()
        self._privileged_buttons.clear()
        self._process_rows.clear()
        self._process_empty_row = None
        self._disk_rows.clear()
        self._iface_rows.clear()
        self._sensor_rows.clear()
        self._nav_items = _nav_items()
        self._relabel_sidebar()
        self._relabel_header()
        self._ensure_page(current)
        self._show_page(current)

    # --- dashboard ---

    def _build_dashboard(self) -> Gtk.Widget:
        from ui.pages import dashboard as dash_page

        return dash_page.build(self)

    def _build_machine(self) -> Gtk.Widget:
        from ui.pages import machine as machine_page

        return machine_page.build(self)

    def _refresh_machine(self, *, show_spinner: bool = False) -> None:
        from ui.pages import machine as machine_page

        machine_page.refresh(self, show_spinner=show_spinner)

    def _build_fleet(self) -> Gtk.Widget:
        from ui.pages import fleet as fleet_page

        return fleet_page.build(self)

    def _refresh_fleet(self, *, show_spinner: bool = False) -> None:
        from ui.pages import fleet as fleet_page

        fleet_page.refresh(self, show_spinner=show_spinner)

    def _build_timers_page(self) -> Gtk.Widget:
        from ui.pages import timers as timers_page

        return timers_page.build(self)

    def _refresh_timers(self, *, show_spinner: bool = False) -> None:
        from ui.pages import timers as timers_page

        timers_page.refresh(self, show_spinner=show_spinner)

    def _build_disk_usage_page(self) -> Gtk.Widget:
        from ui.pages import disk_usage as disk_usage_page

        return disk_usage_page.build(self)

    def _refresh_disk_usage(self, *, show_spinner: bool = False) -> None:
        from ui.pages import disk_usage as disk_usage_page

        disk_usage_page.refresh(self, show_spinner=show_spinner)

    def _wrap_card(self, child: Gtk.Widget) -> Gtk.Widget:
        frame = Gtk.Frame()
        frame.add_css_class("gauge-card")
        frame.set_child(child)
        return frame

    def _section(self, title: str, child: Gtk.Widget) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("title-4")
        box.append(label)
        box.append(child)
        return box

    def _update_metric_list(
        self,
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

    def _evaluate_and_toast_alerts(self, metrics: dict[str, Any]) -> None:
        messages = app_settings.evaluate_alerts(metrics, self._settings)
        if not messages:
            return
        cooldown = float(self._settings.get("alert_cooldown_s") or 60)
        now = time.monotonic()
        msg_set = set(messages)
        if now - self._last_alert_time < cooldown and msg_set == self._last_alert_msgs:
            return
        self._last_alert_time = now
        self._last_alert_msgs = msg_set
        show_toast(self._toast_overlay, " · ".join(messages), timeout=5)
        self._settings["alert_history"] = alerts.append_history(self._settings, messages)
        app_settings.save_settings(self._settings)
        alerts.send_desktop_notification(
            self.get_application(),
            title=i18n.t("alerts"),
            body=" · ".join(messages),
        )

    def _update_dashboard(self, metrics: dict[str, Any]) -> None:
        from ui.pages import dashboard as dash_page

        dash_page.update(self, metrics)
        self._evaluate_and_toast_alerts(metrics)

    # --- processes ---

    def _build_processes(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("page-toolbar")
        self._process_search = Gtk.SearchEntry()
        self._process_search.set_hexpand(True)
        set_placeholder_text(self._process_search, i18n.t("filter_processes"))
        self._debounced_process_search = debounce(220, self._apply_process_filter)
        self._process_search.connect("search-changed", lambda *_: self._debounced_process_search())
        self._process_spinner = make_spinner(size=18)
        self._process_spinner.set_visible(False)
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text(i18n.t("refresh"))
        refresh_btn.connect("clicked", lambda *_: self._refresh_processes(show_spinner=True))
        bar.append(self._process_search)
        bar.append(self._process_spinner)
        bar.append(refresh_btn)
        root.append(bar)

        chips, self._process_sort_buttons = make_filter_chips(
            (
                ("cpu", i18n.t("sort_cpu")),
                ("ram", i18n.t("sort_ram")),
                ("name", i18n.t("sort_name")),
            ),
            active_key=self._process_sort,
            on_change=self._set_process_sort,
        )
        root.append(chips)

        self._process_scrolled = Gtk.ScrolledWindow()
        self._process_scrolled.set_vexpand(True)
        self._process_list = Gtk.ListBox()
        self._process_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._process_list.add_css_class("boxed-list")
        self._process_scrolled.set_child(self._process_list)
        clamp = Adw.Clamp(maximum_size=1000)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        clamp.set_margin_bottom(12)
        clamp.set_child(self._process_scrolled)
        root.append(clamp)
        return root

    def _set_process_sort(self, key: str) -> None:
        self._process_sort = key
        self._render_processes(self._process_data_cache)

    def _apply_process_filter(self) -> None:
        self._process_filter = self._process_search.get_text().strip().lower()
        self._render_processes(self._process_data_cache)

    def _refresh_processes(self, *, show_spinner: bool = False) -> None:
        if show_spinner:
            self._process_spinner.set_visible(True)

        def work() -> list[dict[str, Any]]:
            return process.list_processes(limit=250)

        def done(result: Any, error: BaseException | None) -> None:
            self._process_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, i18n.t("process_error", detail=str(error)))
                return
            self._process_data_cache = list(result or [])
            self._render_processes(self._process_data_cache)

        run_in_thread(work, done)

    def _render_processes(self, items: list[dict[str, Any]]) -> None:
        _, restore = self._preserve_scroll(self._process_scrolled)
        needle = self._process_filter
        filtered: list[dict[str, Any]] = []
        for item in items:
            hay = f"{item['name']} {item['user']} {item['pid']}".lower()
            if needle and needle not in hay:
                continue
            filtered.append(item)
        filtered = process.sort_processes(filtered, self._process_sort)

        if self._process_empty_row is not None:
            self._process_list.remove(self._process_empty_row)
            self._process_empty_row = None

        wanted_pids = {int(item["pid"]) for item in filtered}
        for pid in list(self._process_rows):
            if pid not in wanted_pids:
                row = self._process_rows.pop(pid)
                self._process_list.remove(row)

        if not filtered:
            empty = Adw.ActionRow()
            empty.set_title(i18n.t("process_empty"))
            empty.set_activatable(False)
            self._process_empty_row = empty
            self._process_list.append(empty)
            GLib.idle_add(lambda: restore() or False)
            return

        for item in filtered:
            pid = int(item["pid"])
            title = f"{item['name']}  ·  PID {pid}"
            subtitle = (
                f"CPU {item['cpu']:.1f}%  ·  RAM {item['ram_mib']:.1f} Mio  ·  "
                f"{item['user']}  ·  {item['status']}"
            )
            row = self._process_rows.get(pid)
            if row is None:
                row = ActionListRow(
                    title,
                    subtitle,
                    button_label=i18n.t("process_terminate"),
                    on_clicked=lambda p=pid: self._confirm_kill(p),
                )
                row.set_activatable(True)
                row.connect("activated", lambda *_a, p=pid: self._show_process_detail(p))
                details_btn = Gtk.Button.new_from_icon_name("dialog-information-symbolic")
                details_btn.set_valign(Gtk.Align.CENTER)
                details_btn.set_tooltip_text(i18n.t("process_details"))
                details_btn.connect("clicked", lambda *_a, p=pid: self._show_process_detail(p))
                row.add_suffix(details_btn)
                self._process_rows[pid] = row
                self._process_list.append(row)
            else:
                row.set_title(title)
                row.set_subtitle(subtitle)

        GLib.idle_add(lambda: restore() or False)

    def _show_process_detail(self, pid: int) -> None:
        def work() -> dict[str, Any]:
            return process.process_tree(pid)

        def done(result: Any, error: BaseException | None) -> None:
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            self._present_process_dialog(result)

        run_in_thread(work, done)

    def _present_process_dialog(self, info: dict[str, Any]) -> None:
        pid = int(info["pid"])
        parent = info.get("parent")
        children = info.get("children") or []
        parent_txt = (
            f"{parent.get('name')} (PID {parent.get('pid')})"
            if parent
            else i18n.t("process_none")
        )
        children_txt = (
            ", ".join(f"{c.get('name')} ({c.get('pid')})" for c in children[:12])
            if children
            else i18n.t("process_none")
        )
        if len(children) > 12:
            children_txt += f" … (+{len(children) - 12})"

        body = (
            f"{i18n.t('process_cmd', value=info.get('cmdline'))}\n"
            f"{i18n.t('process_cwd', value=info.get('cwd'))}\n"
            f"{i18n.t('process_user_state', user=info.get('user'), status=info.get('status'))}\n"
            f"{i18n.t('process_nice_threads', nice=info.get('nice'), threads=info.get('num_threads'))}\n"
            f"{i18n.t('process_open_files', value=info.get('open_files'))}\n"
            f"{i18n.t('process_cpu_ram', cpu=info.get('cpu'), ram=info.get('ram_mib'))}\n"
            f"{i18n.t('process_parent', value=parent_txt)}\n"
            f"{i18n.t('process_children', value=children_txt)}"
        )
        extra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        extra.set_halign(Gtk.Align.CENTER)
        nice_lbl = Gtk.Label(label="Nice")
        adj = Gtk.Adjustment(
            value=float(info.get("nice") or 0),
            lower=-20,
            upper=19,
            step_increment=1,
            page_increment=5,
        )
        nice_spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
        apply_nice = Gtk.Button(label=i18n.t("process_apply_nice"))
        apply_nice.add_css_class("suggested-action")

        def on_renice(*_a: object) -> None:
            value = int(nice_spin.get_value())
            self._set_busy(True)

            def work() -> None:
                process.renice_process(pid, value)

            def done(_result: Any, error: BaseException | None) -> None:
                self._set_busy(False)
                if error is not None:
                    show_toast(self._toast_overlay, str(error))
                    return
                show_toast(
                    self._toast_overlay,
                    i18n.t("process_nice_applied", value=value, pid=pid),
                )
                dialog.close()
                self._refresh_processes()

            run_in_thread(work, done)

        apply_nice.connect("clicked", on_renice)
        extra.append(nice_lbl)
        extra.append(nice_spin)
        extra.append(apply_nice)
        dialog = make_message_dialog(
            self,
            f"{info.get('name')} (PID {pid})",
            body,
            extra_child=extra,
        )

        dialog.add_response("close", i18n.t("process_close"))
        dialog.add_response("term", "SIGTERM")
        dialog.add_response("kill", "SIGKILL")
        dialog.set_response_appearance("term", response_appearance("SUGGESTED"))
        dialog.set_response_appearance("kill", response_appearance("DESTRUCTIVE"))
        dialog.set_default_response("close")
        dialog.set_close_response("close")

        def on_response(_d: object, response: str) -> None:
            if response == "term":
                self._do_kill(pid, signal.SIGTERM)
            elif response == "kill":
                self._do_kill(pid, signal.SIGKILL)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _confirm_kill(self, pid: int) -> None:
        confirm_dialog(
            self,
            i18n.t("process_confirm_title"),
            i18n.t("process_confirm_body", pid=pid),
            confirm_label=i18n.t("process_terminate"),
            on_confirm=lambda: self._do_kill(pid, signal.SIGTERM),
        )

    def _do_kill(self, pid: int, sig: int) -> None:
        self._set_busy(True)

        def work() -> None:
            process.kill_process(pid, sig)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, i18n.t("process_signal_sent", pid=pid))
            self._refresh_processes()

        run_in_thread(work, done)

    # --- services ---

    def _build_services_page(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("page-toolbar")
        self._service_search = Gtk.SearchEntry()
        self._service_search.set_hexpand(True)
        set_placeholder_text(self._service_search, i18n.t("filter_services"))
        self._debounced_service_search = debounce(220, self._apply_service_filter)
        self._service_search.connect("search-changed", lambda *_: self._debounced_service_search())
        self._service_spinner = make_spinner(size=18)
        self._service_spinner.set_visible(False)
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.connect("clicked", lambda *_: self._refresh_services(show_spinner=True))
        bar.append(self._service_search)
        bar.append(self._service_spinner)
        bar.append(refresh_btn)
        root.append(bar)

        chips, self._service_chip_buttons = make_filter_chips(
            (
                ("active", i18n.t("svc_active")),
                ("enabled", i18n.t("svc_enabled")),
                ("failed", i18n.t("svc_failed")),
                ("all", i18n.t("svc_all")),
            ),
            active_key=self._service_chip,
            on_change=self._set_service_chip,
        )
        root.append(chips)

        self._service_scrolled = Gtk.ScrolledWindow()
        self._service_scrolled.set_vexpand(True)
        self._service_list = Gtk.ListBox()
        self._service_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._service_list.add_css_class("boxed-list")
        self._service_scrolled.set_child(self._service_list)
        clamp = Adw.Clamp(maximum_size=1000)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        clamp.set_margin_bottom(12)
        clamp.set_child(self._service_scrolled)
        root.append(clamp)
        return root

    def _set_service_chip(self, key: str) -> None:
        self._service_chip = key
        self._render_services(self._service_data_cache)

    def _apply_service_filter(self) -> None:
        self._service_filter = self._service_search.get_text().strip().lower()
        self._render_services(self._service_data_cache)

    def _refresh_services(self, *, show_spinner: bool = False) -> None:
        if show_spinner:
            self._service_spinner.set_visible(True)

        def work() -> list[dict[str, Any]]:
            return services.list_services()

        def done(result: Any, error: BaseException | None) -> None:
            self._service_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, i18n.t("svc_error", detail=str(error)))
                return
            self._service_data_cache = list(result or [])
            self._render_services(self._service_data_cache)

        run_in_thread(work, done)

    def _render_services(self, items: list[dict[str, Any]]) -> None:
        _, restore = self._preserve_scroll(self._service_scrolled)
        self._clear_listbox(self._service_list)
        visible = services.filter_services(
            items, chip=self._service_chip, needle=self._service_filter
        )
        if not visible:
            empty = Adw.ActionRow()
            empty.set_title(i18n.t("svc_empty"))
            empty.set_activatable(False)
            self._service_list.append(empty)
            GLib.idle_add(lambda: restore() or False)
            return
        for item in visible:
            state = (
                i18n.t("svc_state_active")
                if item.get("is_active")
                else i18n.t("svc_state_inactive")
            )
            enabled = item.get("enabled", "unknown")
            desc = (item.get("description") or "").strip() or i18n.t("svc_no_description")
            title = item["short_name"]
            subtitle = f"{desc}\n{state} · {item.get('sub', '')} · {enabled}"
            row = Adw.ActionRow()
            row.set_title(title)
            row.set_subtitle(subtitle)

            unit = item["name"]
            restart_btn = Gtk.Button(label=i18n.t("svc_restart"))
            restart_btn.set_valign(Gtk.Align.CENTER)
            restart_btn.set_sensitive(self._busy_ops == 0)
            restart_btn.connect("clicked", lambda *_a, u=unit: self._service_action(u, "restart"))
            row.add_suffix(restart_btn)

            if item.get("is_active"):
                btn = Gtk.Button(label=i18n.t("svc_stop"))
                btn.add_css_class("destructive-action")
                btn.connect("clicked", lambda *_a, u=unit: self._service_action(u, "stop"))
            else:
                btn = Gtk.Button(label=i18n.t("svc_start"))
                btn.add_css_class("suggested-action")
                btn.connect("clicked", lambda *_a, u=unit: self._service_action(u, "start"))
            btn.set_valign(Gtk.Align.CENTER)
            btn.set_sensitive(self._busy_ops == 0)
            row.add_suffix(btn)

            en_btn = Gtk.Button(
                label=i18n.t("disable") if item.get("is_enabled") else i18n.t("enable")
            )
            en_btn.set_valign(Gtk.Align.CENTER)
            en_btn.set_sensitive(self._busy_ops == 0)
            action = "disable" if item.get("is_enabled") else "enable"
            en_btn.connect("clicked", lambda *_a, u=unit, act=action: self._service_action(u, act))
            row.add_suffix(en_btn)
            self._service_list.append(row)

        GLib.idle_add(lambda: restore() or False)

    def _service_action_label(self, action: str) -> str:
        keys = {
            "restart": "svc_restart",
            "stop": "svc_stop",
            "start": "svc_start",
            "enable": "enable",
            "disable": "disable",
        }
        return i18n.t(keys.get(action, action))

    def _service_action(self, unit: str, action: str) -> None:
        label = self._service_action_label(action)
        confirm_dialog(
            self,
            i18n.t("svc_confirm_title", action=label),
            i18n.t("svc_confirm_body", action=action, unit=unit),
            confirm_label=label,
            destructive=action in {"stop", "disable"},
            on_confirm=lambda: self._do_service_action(unit, action),
        )

    def _do_service_action(self, unit: str, action: str) -> None:
        self._set_busy(True)
        show_toast(
            self._toast_overlay,
            i18n.t("svc_running", action=self._service_action_label(action)),
            timeout=2,
        )

        def work() -> dict[str, Any]:
            return services.toggle_service(unit, action)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(
                self._toast_overlay,
                i18n.t("svc_done", action=self._service_action_label(action), unit=unit),
            )
            self._refresh_services()

        run_in_thread(work, done)

    # --- cleaner ---

    def _build_cleaner_page(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        scan_btn = Gtk.Button(label=i18n.t("scan"))
        scan_btn.add_css_class("suggested-action")
        scan_btn.connect("clicked", lambda *_: self._refresh_cleaner(show_spinner=True))
        select_all_btn = Gtk.Button(label=i18n.t("select_all"))
        select_all_btn.connect("clicked", lambda *_: self._cleaner_select_all(True))
        select_none_btn = Gtk.Button(label=i18n.t("select_none"))
        select_none_btn.connect("clicked", lambda *_: self._cleaner_select_all(False))
        clean_btn = Gtk.Button(label=i18n.t("clean_selection"))
        clean_btn.add_css_class("destructive-action")
        clean_btn.connect("clicked", lambda *_: self._confirm_clean())
        self._track_privileged(clean_btn)
        self._cleaner_spinner = make_spinner(size=18)
        self._cleaner_spinner.set_visible(False)
        controls.append(scan_btn)
        controls.append(select_all_btn)
        controls.append(select_none_btn)
        controls.append(clean_btn)
        controls.append(self._cleaner_spinner)
        root.append(controls)

        self._cleaner_total = Gtk.Label(label=i18n.t("reclaimable", size="—"), xalign=0)
        self._cleaner_total.add_css_class("title-4")
        root.append(self._cleaner_total)

        self._cleaner_checks: dict[str, Gtk.CheckButton] = {}
        self._cleaner_list = Gtk.ListBox()
        self._cleaner_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._cleaner_list.add_css_class("boxed-list")
        clamp = Adw.Clamp(maximum_size=900)
        clamp.set_child(self._cleaner_list)
        root.append(clamp)
        return root

    def _cleaner_select_all(self, active: bool) -> None:
        for check in self._cleaner_checks.values():
            check.set_active(active)

    def _refresh_cleaner(self, *, show_spinner: bool = False) -> None:
        if show_spinner:
            self._cleaner_spinner.set_visible(True)
            self._set_busy(True)

        def work() -> list[dict[str, Any]]:
            return cleaner.scan()

        def done(result: Any, error: BaseException | None) -> None:
            if show_spinner:
                self._set_busy(False)
            self._cleaner_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, f"Nettoyage: {error}")
                return
            self._clear_listbox(self._cleaner_list)
            self._cleaner_checks.clear()
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
                self._cleaner_checks[item["id"]] = check
                self._cleaner_list.append(row)
            self._cleaner_total.set_text(i18n.t("reclaimable", size=f"{total:.2f} Mio"))

        run_in_thread(work, done)

    def _confirm_clean(self) -> None:
        selected = [key for key, check in self._cleaner_checks.items() if check.get_active()]
        if not selected:
            show_toast(self._toast_overlay, "Aucune cible sélectionnée")
            return
        confirm_dialog(
            self,
            "Lancer le nettoyage ?",
            "Les fichiers sélectionnés seront supprimés. Les actions root utilisent pkexec.",
            confirm_label="Nettoyer",
            on_confirm=lambda: self._do_clean(selected),
        )

    def _do_clean(self, targets: list[str]) -> None:
        self._set_busy(True)
        show_toast(self._toast_overlay, "Nettoyage en cours…", timeout=4)

        def work() -> dict[str, Any]:
            return cleaner.clean(targets)

        def done(result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            freed = result.get("freed_mib", 0) if isinstance(result, dict) else 0
            show_toast(self._toast_overlay, f"Nettoyage terminé — {freed:.2f} Mio libérés")
            self._refresh_cleaner()

        run_in_thread(work, done)

    # --- packages ---

    def _build_packages_page(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("page-toolbar")
        self._package_search = Gtk.SearchEntry()
        self._package_search.set_hexpand(True)
        set_placeholder_text(self._package_search, i18n.t("filter_packages"))
        self._debounced_package_search = debounce(280, self._apply_package_filter)
        self._package_search.connect("search-changed", lambda *_: self._debounced_package_search())
        self._package_spinner = make_spinner(size=18)
        self._package_spinner.set_visible(False)
        check_btn = Gtk.Button(label=i18n.t("check_pkg_updates"))
        check_btn.connect("clicked", lambda *_: self._check_package_updates())
        self._track_privileged(check_btn)
        update_btn = Gtk.Button(label=i18n.t("apply_all_updates"))
        update_btn.add_css_class("suggested-action")
        update_btn.connect("clicked", lambda *_: self._confirm_apply_updates())
        self._track_privileged(update_btn)
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.connect("clicked", lambda *_: self._refresh_packages(show_spinner=True))
        bar.append(self._package_search)
        bar.append(self._package_spinner)
        bar.append(check_btn)
        bar.append(update_btn)
        bar.append(refresh_btn)
        root.append(bar)

        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        chips.add_css_class("linked")
        chips.set_margin_start(12)
        chips.set_margin_end(12)
        chips.set_margin_bottom(4)
        self._package_chip_buttons: dict[str, Gtk.ToggleButton] = {}
        for key, label in (("all", i18n.t("pkg_all")), ("apt", "APT"), ("flatpak", "Flatpak"), ("snap", "Snap")):
            btn = Gtk.ToggleButton(label=label)
            btn.add_css_class("filter-chip")
            btn.set_active(key == self._package_manager)
            btn.connect("toggled", lambda b, k=key: self._on_package_chip(k, b))
            self._package_chip_buttons[key] = btn
            chips.append(btn)
        root.append(chips)

        self._managers_label = Gtk.Label(label="", xalign=0)
        self._managers_label.set_margin_start(16)
        self._managers_label.set_margin_bottom(8)
        self._managers_label.add_css_class("dim-label")
        root.append(self._managers_label)

        self._package_scrolled = Gtk.ScrolledWindow()
        self._package_scrolled.set_vexpand(True)
        self._package_list = Gtk.ListBox()
        self._package_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._package_list.add_css_class("boxed-list")
        self._package_scrolled.set_child(self._package_list)
        clamp = Adw.Clamp(maximum_size=1000)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        clamp.set_margin_bottom(12)
        clamp.set_child(self._package_scrolled)
        root.append(clamp)
        return root

    def _on_package_chip(self, key: str, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            if self._package_manager == key:
                button.set_active(True)
            return
        self._package_manager = key
        for k, btn in self._package_chip_buttons.items():
            if k != key and btn.get_active():
                btn.set_active(False)
        self._render_packages(self._package_data_cache)

    def _apply_package_filter(self) -> None:
        self._package_filter = self._package_search.get_text().strip().lower()
        self._render_packages(self._package_data_cache)

    def _refresh_packages(self, *, show_spinner: bool = False) -> None:
        avail = packages.available_managers()
        present = ", ".join(name for name, ok in avail.items() if ok) or i18n.t(
            "pkg_managers_none"
        )
        self._managers_label.set_text(i18n.t("pkg_managers_detected", managers=present))
        if show_spinner:
            self._package_spinner.set_visible(True)

        def work() -> list[dict[str, Any]]:
            return packages.list_packages()

        def done(result: Any, error: BaseException | None) -> None:
            self._package_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, i18n.t("pkg_error", detail=str(error)))
                return
            self._package_data_cache = list(result or [])
            self._render_packages(self._package_data_cache)

        run_in_thread(work, done)

    def _render_packages(self, items: list[dict[str, Any]]) -> None:
        _, restore = self._preserve_scroll(self._package_scrolled)
        self._clear_listbox(self._package_list)
        needle = self._package_filter
        manager = self._package_manager
        count = 0
        for item in items:
            if manager != "all" and item.get("manager") != manager:
                continue
            hay = f"{item['name']} {item['id']} {item['manager']}".lower()
            if needle and needle not in hay:
                continue
            count += 1
            if count > 400:
                break
            title = f"{item['name']}  [{item['manager']}]"
            subtitle = f"{item['id']} · {item.get('version', '')}"
            mgr = item["manager"]
            pkg_id = item["id"]
            row = ActionListRow(
                title,
                subtitle,
                button_label="Désinstaller",
                on_clicked=lambda m=mgr, i=pkg_id: self._confirm_uninstall(m, i),
            )
            row.set_busy(self._busy_ops > 0)
            if mgr == "flatpak":
                perm_btn = Gtk.Button(label="Permissions")
                perm_btn.set_valign(Gtk.Align.CENTER)
                perm_btn.connect("clicked", lambda *_a, i=pkg_id: self._show_flatpak_permissions(i))
                row.add_suffix(perm_btn)
            self._package_list.append(row)
        GLib.idle_add(lambda: restore() or False)

    def _check_package_updates(self) -> None:
        self._launch_pkg_job(
            packages.write_check_updates_script,
            i18n.t("pkg_job_check_title"),
        )

    def _confirm_apply_updates(self) -> None:
        labels = packages.host_manager_labels()
        managers = ", ".join(labels) if labels else "aucun"
        extra = (
            i18n.t("pkg_apply_snapshot")
            if backup.is_available()
            else i18n.t("pkg_apply_no_snapshot")
        )
        confirm_dialog(
            self,
            i18n.t("pkg_apply_title"),
            i18n.t("pkg_apply_body", managers=managers) + "\n\n" + extra,
            confirm_label=i18n.t("update_now"),
            destructive=False,
            on_confirm=self._do_apply_updates,
        )

    def _do_apply_updates(self) -> None:
        if self._pkg_terminal_open:
            show_toast(self._toast_overlay, i18n.t("pkg_terminal_busy"), timeout=5)
            return

        def start_job() -> None:
            self._launch_pkg_job(
                packages.write_apply_updates_script,
                i18n.t("pkg_job_apply_title"),
            )

        if not backup.is_available():
            start_job()
            return

        self._pkg_terminal_open = True
        self._set_busy(True)
        show_toast(self._toast_overlay, i18n.t("pkg_snapshot_creating"), timeout=5)

        def work() -> dict[str, Any]:
            return backup.create_snapshot("Hub Système: avant MAJ paquets")

        def done(result: Any, error: BaseException | None) -> None:
            self._pkg_terminal_open = False
            self._set_busy(False)
            if error is not None:
                show_toast(
                    self._toast_overlay,
                    i18n.t("pkg_snapshot_failed", detail=str(error)),
                    timeout=8,
                )
                return
            show_toast(self._toast_overlay, i18n.t("pkg_snapshot_ok"), timeout=4)
            start_job()

        run_in_thread(work, done)

    def _launch_pkg_job(self, writer: Callable[[], Path], title: str) -> None:
        if self._pkg_terminal_open:
            show_toast(self._toast_overlay, i18n.t("pkg_terminal_busy"), timeout=5)
            return
        self._pkg_terminal_open = True
        self._set_busy(True)
        done = packages.pkg_terminal_done_path()
        try:
            done.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            script = writer()
        except OSError as exc:
            self._pkg_terminal_open = False
            self._set_busy(False)
            show_toast(self._toast_overlay, str(exc), timeout=8)
            return
        show_toast(self._toast_overlay, i18n.t("pkg_console_opening"), timeout=4)
        try:
            job_console.present(
                self,
                title=title,
                script=script,
                on_finished=self._on_pkg_job_finished,
            )
        except jobs.JobError:
            try:
                updater.open_terminal_script(script)
            except updater.UpdateError as exc:
                self._pkg_terminal_open = False
                self._set_busy(False)
                show_toast(self._toast_overlay, str(exc), timeout=8)
                return
            self._pkg_poll_deadline = time.monotonic() + 900.0
            GLib.timeout_add(400, self._poll_pkg_terminal_done)

    def _on_pkg_job_finished(self, _code: int) -> None:
        self._pkg_terminal_open = False
        self._set_busy(False)
        self._refresh_packages()

    def _poll_pkg_terminal_done(self) -> bool:
        flag = packages.pkg_terminal_done_path()
        if flag.is_file():
            try:
                flag.unlink(missing_ok=True)
            except OSError:
                pass
            self._pkg_terminal_open = False
            self._set_busy(False)
            self._refresh_packages()
            return False
        deadline = float(getattr(self, "_pkg_poll_deadline", 0.0) or 0.0)
        if deadline and time.monotonic() > deadline:
            self._pkg_terminal_open = False
            self._set_busy(False)
            self._refresh_packages()
            return False
        if not self._pkg_terminal_open:
            return False
        return True

    def _show_flatpak_permissions(self, app_id: str) -> None:
        def work() -> dict[str, Any]:
            return packages.flatpak_permissions(app_id)

        def done(result: Any, error: BaseException | None) -> None:
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            text = (result or {}).get("text") or "(vide)"
            dialog = make_message_dialog(self, f"Permissions — {app_id}", text[:4000])
            dialog.add_response("close", "Fermer")
            dialog.set_default_response("close")
            dialog.set_close_response("close")
            dialog.present(self)

        run_in_thread(work, done)

    def _confirm_uninstall(self, manager: str, pkg_id: str) -> None:
        confirm_dialog(
            self,
            "Désinstaller le paquet ?",
            f"{manager}: {pkg_id}",
            confirm_label="Désinstaller",
            on_confirm=lambda: self._do_uninstall(manager, pkg_id),
        )

    def _do_uninstall(self, manager: str, pkg_id: str) -> None:
        self._set_busy(True)
        show_toast(self._toast_overlay, f"Désinstallation de {pkg_id}…", timeout=3)

        def work() -> dict[str, Any]:
            return packages.uninstall_package(manager, pkg_id)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, f"Désinstallé: {pkg_id}")
            self._refresh_packages()

        run_in_thread(work, done)

    # --- logs ---

    def _build_logs_page(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("page-toolbar")
        self._logs_search = Gtk.SearchEntry()
        self._logs_search.set_hexpand(True)
        set_placeholder_text(self._logs_search, i18n.t("filter_logs"))
        self._debounced_logs_search = debounce(280, self._apply_logs_filter)
        self._logs_search.connect("search-changed", lambda *_: self._debounced_logs_search())
        self._logs_spinner = make_spinner(size=18)
        self._logs_spinner.set_visible(False)
        export_btn = Gtk.Button(label=i18n.t("export"))
        export_btn.connect("clicked", lambda *_: self._export_logs())
        sys_btn = Gtk.Button(label=i18n.t("journal_system_admin"))
        sys_btn.connect(
            "clicked",
            lambda *_: self._refresh_logs(show_spinner=True, privileged=True),
        )
        self._track_privileged(sys_btn)
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text(i18n.t("refresh"))
        refresh_btn.connect("clicked", lambda *_: self._refresh_logs(show_spinner=True))
        bar.append(self._logs_search)
        bar.append(self._logs_spinner)
        bar.append(export_btn)
        bar.append(sys_btn)
        bar.append(refresh_btn)
        root.append(bar)

        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        chips.add_css_class("linked")
        chips.set_margin_start(12)
        chips.set_margin_end(12)
        chips.set_margin_bottom(4)
        self._logs_chip_buttons: dict[str, Gtk.ToggleButton] = {}
        for key, label_key in (
            ("err", "logs_err"),
            ("warning", "logs_warning"),
            ("info", "logs_info"),
            ("all", "logs_all"),
        ):
            btn = Gtk.ToggleButton(label=i18n.t(label_key))
            btn.add_css_class("filter-chip")
            btn.set_active(key == self._logs_priority)
            btn.connect("toggled", lambda b, k=key: self._on_logs_chip(k, b))
            self._logs_chip_buttons[key] = btn
            chips.append(btn)
        root.append(chips)

        preset_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        preset_bar.set_margin_start(12)
        preset_bar.set_margin_end(12)
        preset_bar.set_margin_bottom(8)
        save_preset = Gtk.Button(label=i18n.t("logs_preset_save"))
        save_preset.connect("clicked", lambda *_: self._save_log_preset())
        self._logs_preset_drop = Gtk.DropDown()
        self._logs_preset_drop.set_hexpand(True)
        self._logs_preset_drop.connect(
            "notify::selected", lambda *_a: self._on_log_preset_selected()
        )
        delete_preset = Gtk.Button(label=i18n.t("logs_preset_delete"))
        delete_preset.connect("clicked", lambda *_: self._delete_selected_log_preset())
        preset_bar.append(save_preset)
        preset_bar.append(self._logs_preset_drop)
        preset_bar.append(delete_preset)
        root.append(preset_bar)
        self._fill_log_presets()

        self._logs_status = Gtk.Label(label="—", xalign=0)
        self._logs_status.add_css_class("dim-label")
        self._logs_status.set_margin_start(16)
        self._logs_status.set_margin_bottom(8)
        root.append(self._logs_status)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_margin_start(12)
        scrolled.set_margin_end(12)
        scrolled.set_margin_bottom(12)
        self._logs_view = Gtk.TextView()
        self._logs_view.set_editable(False)
        self._logs_view.set_cursor_visible(False)
        self._logs_view.set_wrap_mode(Gtk.WrapMode.CHAR)
        self._logs_view.set_monospace(True)
        self._logs_view.add_css_class("logs-view")
        scrolled.set_child(self._logs_view)
        root.append(scrolled)
        return root

    def _on_logs_chip(self, key: str, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            if self._logs_priority == key:
                button.set_active(True)
            return
        self._logs_priority = key
        for k, btn in self._logs_chip_buttons.items():
            if k != key and btn.get_active():
                btn.set_active(False)
        self._refresh_logs(show_spinner=True)

    def _apply_logs_filter(self) -> None:
        self._logs_grep = self._logs_search.get_text().strip()
        self._refresh_logs(show_spinner=True)

    def _log_preset_names(self) -> list[str]:
        names: list[str] = []
        for item in self._settings.get("log_filter_presets") or []:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
        return names

    def _fill_log_presets(self, *, select: str | None = None) -> None:
        names = self._log_preset_names()
        model = Gtk.StringList.new(["—"] + names)
        self._logs_preset_guard = True
        self._logs_preset_drop.set_model(model)
        index = 0
        if select:
            try:
                index = names.index(select) + 1
            except ValueError:
                index = 0
        self._logs_preset_drop.set_selected(index)
        self._logs_preset_guard = False

    def _set_logs_chip(self, key: str) -> None:
        self._logs_priority = key
        for chip_key, btn in self._logs_chip_buttons.items():
            btn.set_active(chip_key == key)

    def _save_log_preset(self) -> None:
        entry = Gtk.Entry()
        set_placeholder_text(entry, i18n.t("logs_preset_name"))
        dialog = make_message_dialog(
            self,
            i18n.t("logs_preset_save"),
            i18n.t("logs_preset_name"),
            extra_child=entry,
        )
        dialog.add_response("cancel", i18n.t("cancel"))
        dialog.add_response("save", i18n.t("save"))
        dialog.set_default_response("save")

        def on_response(_d: object, response: str) -> None:
            if response != "save":
                return
            try:
                added = app_settings.add_log_preset(
                    self._settings,
                    entry.get_text(),
                    self._logs_priority,
                    self._logs_grep,
                )
            except app_settings.LogPresetError as exc:
                key = (
                    "logs_preset_full"
                    if "10" in str(exc)
                    else "logs_preset_invalid"
                )
                show_toast(self._toast_overlay, i18n.t(key))
                return
            app_settings.save_settings(self._settings)
            self._settings = app_settings.load_settings()
            self._fill_log_presets(select=added["name"])
            show_toast(self._toast_overlay, i18n.t("logs_preset_saved"))

        dialog.connect("response", on_response)
        dialog.present(self)

    def _on_log_preset_selected(self) -> None:
        if self._logs_preset_guard:
            return
        selected = int(self._logs_preset_drop.get_selected())
        if selected <= 0:
            return
        names = self._log_preset_names()
        if selected > len(names):
            return
        preset = app_settings.lookup_log_preset(self._settings, names[selected - 1])
        if preset is None:
            return
        self._logs_grep = preset["grep"]
        self._logs_search.set_text(preset["grep"])
        self._set_logs_chip(preset["priority"])
        self._refresh_logs(show_spinner=True)

    def _delete_selected_log_preset(self) -> None:
        selected = int(self._logs_preset_drop.get_selected())
        names = self._log_preset_names()
        if selected <= 0 or selected > len(names):
            return
        if not app_settings.remove_log_preset(self._settings, names[selected - 1]):
            return
        app_settings.save_settings(self._settings)
        self._settings = app_settings.load_settings()
        self._fill_log_presets()

    def _refresh_logs(self, *, show_spinner: bool = False, privileged: bool = False) -> None:
        if show_spinner:
            self._logs_spinner.set_visible(True)
        if privileged:
            show_toast(
                self._toast_overlay,
                i18n.t("logs_reading_admin"),
                timeout=4,
            )
        priority = self._logs_priority
        grep = self._logs_grep

        def work() -> dict[str, Any]:
            return logs.read_journal(
                lines=200, priority=priority, grep=grep, privileged=privileged
            )

        def done(result: Any, error: BaseException | None) -> None:
            self._logs_spinner.set_visible(False)
            buf = self._logs_view.get_buffer()
            if error is not None:
                show_toast(self._toast_overlay, i18n.t("logs_error", detail=str(error)))
                buf.set_text(str(error))
                self._logs_status.set_text(i18n.t("logs_status_error"))
                return
            text = result.get("text", "") if isinstance(result, dict) else ""
            message = str(result.get("message") or "").strip() if isinstance(result, dict) else ""
            if not text.strip() and message:
                text = message + "\n"
            if not text.strip():
                text = i18n.t("logs_empty")
            self._logs_text_cache = text
            buf.set_text(text)
            count = result.get("line_count", 0) if isinstance(result, dict) else 0
            source = str(result.get("source") or "").strip() if isinstance(result, dict) else ""
            status_bits = [i18n.t("logs_status_lines", count=count), priority]
            if source:
                status_bits.append(source)
            if message:
                status_bits.append(message)
            status_bits.append(i18n.t("logs_status_refreshed", time=time.strftime("%H:%M:%S")))
            self._logs_status.set_text(" · ".join(status_bits))
            end = buf.get_end_iter()
            self._logs_view.scroll_to_iter(end, 0.0, False, 0.0, 0.0)

        run_in_thread(work, done)

    def _export_logs(self) -> None:
        text = self._logs_text_cache
        if not text.strip() or text.strip() == i18n.t("logs_empty"):
            show_toast(self._toast_overlay, i18n.t("logs_none_export"))
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        default = Path.home() / "Documents" / f"hub-systeme-journal-{stamp}.txt"

        def work() -> Path:
            return logs.export_journal(default, text=text)

        def done(result: Any, error: BaseException | None) -> None:
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, i18n.t("logs_exported", path=result))

        run_in_thread(work, done)

    # --- autostart ---

    def _build_autostart_page(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("page-toolbar")
        title = Gtk.Label(label=i18n.t("autostart_title"), xalign=0)
        title.add_css_class("heading")
        title.set_hexpand(True)
        self._autostart_spinner = make_spinner(size=18)
        self._autostart_spinner.set_visible(False)
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.connect("clicked", lambda *_: self._refresh_autostart(show_spinner=True))
        bar.append(title)
        bar.append(self._autostart_spinner)
        bar.append(refresh_btn)
        root.append(bar)

        self._autostart_scrolled = Gtk.ScrolledWindow()
        self._autostart_scrolled.set_vexpand(True)
        self._autostart_list = Gtk.ListBox()
        self._autostart_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._autostart_list.add_css_class("boxed-list")
        self._autostart_scrolled.set_child(self._autostart_list)
        clamp = Adw.Clamp(maximum_size=1000)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        clamp.set_margin_bottom(12)
        clamp.set_child(self._autostart_scrolled)
        root.append(clamp)
        return root

    def _refresh_autostart(self, *, show_spinner: bool = False) -> None:
        if show_spinner:
            self._autostart_spinner.set_visible(True)

        def work() -> list[dict[str, Any]]:
            return autostart.list_all()

        def done(result: Any, error: BaseException | None) -> None:
            self._autostart_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, f"Démarrage: {error}")
                return
            self._clear_listbox(self._autostart_list)
            for item in result or []:
                kind = item.get("kind")
                title = str(item.get("name") or item.get("id"))
                desc = str(item.get("description") or "")
                kind_lbl = "Desktop" if kind == "desktop" else "Service utilisateur"
                row = Adw.ActionRow()
                row.set_title(title)
                row.set_subtitle(f"{kind_lbl} · {desc}".strip(" ·"))
                switch = Gtk.Switch()
                switch.set_valign(Gtk.Align.CENTER)
                guard = {"block": True}

                def on_toggle(
                    sw: Gtk.Switch,
                    _p: object,
                    it: dict[str, Any] = item,
                    g: dict[str, bool] = guard,
                ) -> None:
                    if g["block"]:
                        return
                    self._toggle_autostart(it, sw.get_active())

                switch.connect("notify::active", on_toggle)
                switch.set_active(bool(item.get("enabled")))
                guard["block"] = False
                row.add_suffix(switch)
                self._autostart_list.append(row)

        run_in_thread(work, done)

    def _toggle_autostart(self, item: dict[str, Any], enabled: bool) -> None:
        kind = item.get("kind")
        ident = str(item.get("id") or "")
        self._set_busy(True)

        def work() -> None:
            if kind == "desktop":
                autostart.set_desktop_enabled(ident, enabled)
            else:
                autostart.toggle_user_service(ident, enabled)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                self._refresh_autostart()
                return
            show_toast(
                self._toast_overlay,
                f"{'Activé' if enabled else 'Désactivé'}: {ident}",
            )

        run_in_thread(work, done)

    # --- network ---

    def _build_network_page(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("page-toolbar")
        title = Gtk.Label(label=i18n.t("network"), xalign=0)
        title.add_css_class("heading")
        title.set_hexpand(True)
        self._network_spinner = make_spinner(size=18)
        self._network_spinner.set_visible(False)
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.connect("clicked", lambda *_: self._refresh_network(show_spinner=True))
        allow_btn = Gtk.Button(label=i18n.t("conn_allowlist_add"))
        allow_btn.connect("clicked", lambda *_: self._open_allowlist_dialog())
        bar.append(title)
        bar.append(self._network_spinner)
        bar.append(allow_btn)
        bar.append(refresh_btn)
        root.append(bar)

        chips, self._network_chip_buttons = make_filter_chips(
            (
                ("wifi", i18n.t("wifi_chip")),
                ("conn", i18n.t("conn_chip")),
            ),
            active_key=self._network_chip,
            on_change=self._set_network_chip,
        )
        root.append(chips)

        self._network_stack = Gtk.Stack()
        self._network_stack.set_vexpand(True)
        self._network_stack.set_hexpand(True)

        wifi_scrolled = Gtk.ScrolledWindow()
        wifi_scrolled.set_vexpand(True)
        wifi_clamp = Adw.Clamp(maximum_size=900)
        wifi_clamp.set_margin_start(12)
        wifi_clamp.set_margin_end(12)
        wifi_clamp.set_margin_bottom(12)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        wifi_group = Adw.PreferencesGroup()
        wifi_group.set_title("Wi-Fi")
        self._wifi_switch_row = make_switch_row()
        self._wifi_switch_row.set_title(i18n.t("wifi_radio"))
        self._wifi_switch_row.set_subtitle("—")
        self._wifi_switch_row.connect("notify::active", self._on_wifi_switch)
        self._wifi_switch_guard = False
        wifi_group.add(self._wifi_switch_row)
        box.append(wifi_group)

        self._wifi_list = Gtk.ListBox()
        self._wifi_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._wifi_list.add_css_class("boxed-list")
        box.append(self._section(i18n.t("networks_found"), self._wifi_list))

        bt_group = Adw.PreferencesGroup()
        bt_group.set_title("Bluetooth")
        self._bt_switch_row = make_switch_row()
        self._bt_switch_row.set_title(i18n.t("bt_power"))
        self._bt_switch_row.set_subtitle("—")
        self._bt_switch_row.connect("notify::active", self._on_bt_switch)
        self._bt_switch_guard = False
        bt_group.add(self._bt_switch_row)
        box.append(bt_group)

        self._bt_list = Gtk.ListBox()
        self._bt_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._bt_list.add_css_class("boxed-list")
        box.append(self._section(i18n.t("devices"), self._bt_list))

        wifi_clamp.set_child(box)
        wifi_scrolled.set_child(wifi_clamp)

        conn_root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        conn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        conn_bar.set_margin_start(12)
        conn_bar.set_margin_end(12)
        conn_bar.set_margin_bottom(8)
        self._conn_status = Gtk.Label(label="—", xalign=0)
        self._conn_status.set_hexpand(True)
        self._conn_status.set_wrap(True)
        self._conn_status.add_css_class("dim-label")
        export_btn = Gtk.Button(label=i18n.t("conn_export"))
        export_btn.connect("clicked", lambda *_: self._export_connections())
        admin_btn = Gtk.Button(label=i18n.t("conn_load_admin"))
        admin_btn.connect(
            "clicked",
            lambda *_: self._refresh_connections(show_spinner=True, privileged=True),
        )
        self._track_privileged(admin_btn)
        conn_bar.append(self._conn_status)
        conn_bar.append(export_btn)
        conn_bar.append(admin_btn)
        conn_root.append(conn_bar)

        conn_scrolled = Gtk.ScrolledWindow()
        conn_scrolled.set_vexpand(True)
        conn_clamp = Adw.Clamp(maximum_size=900)
        conn_clamp.set_margin_start(12)
        conn_clamp.set_margin_end(12)
        conn_clamp.set_margin_bottom(12)
        self._conn_list = Gtk.ListBox()
        self._conn_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._conn_list.add_css_class("boxed-list")
        conn_clamp.set_child(self._conn_list)
        conn_scrolled.set_child(conn_clamp)
        conn_root.append(conn_scrolled)

        self._network_stack.add_named(wifi_scrolled, "wifi")
        self._network_stack.add_named(conn_root, "conn")
        self._network_stack.set_visible_child_name(self._network_chip)
        root.append(self._network_stack)
        return root

    def _set_network_chip(self, key: str) -> None:
        self._network_chip = key
        if hasattr(self, "_network_stack"):
            self._network_stack.set_visible_child_name(key)
        self._refresh_network(show_spinner=True)

    def _on_wifi_switch(self, row: Gtk.Widget, _pspec: object) -> None:
        if getattr(self, "_wifi_switch_guard", False):
            return
        enabled = row.get_active()
        self._set_busy(True)

        def work() -> None:
            network_ctl.set_wifi_enabled(enabled)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                self._refresh_network()
                return
            show_toast(self._toast_overlay, f"Wi-Fi {'activé' if enabled else 'désactivé'}")
            self._refresh_network()

        run_in_thread(work, done)

    def _on_bt_switch(self, row: Gtk.Widget, _pspec: object) -> None:
        if getattr(self, "_bt_switch_guard", False):
            return
        powered = row.get_active()
        self._set_busy(True)

        def work() -> None:
            network_ctl.set_bluetooth_powered(powered)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                self._refresh_network()
                return
            show_toast(self._toast_overlay, f"Bluetooth {'activé' if powered else 'désactivé'}")
            self._refresh_network()

        run_in_thread(work, done)

    def _refresh_network(self, *, show_spinner: bool = False, privileged: bool = False) -> None:
        if getattr(self, "_network_chip", "wifi") == "conn":
            self._refresh_connections(show_spinner=show_spinner, privileged=privileged)
            return
        if show_spinner:
            self._network_spinner.set_visible(True)

        def work() -> tuple[dict[str, Any], dict[str, Any]]:
            return network_ctl.wifi_status(), network_ctl.bluetooth_status()

        def done(result: Any, error: BaseException | None) -> None:
            self._network_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, f"Réseau: {error}")
                return
            wifi, bt = result
            self._wifi_switch_guard = True
            self._wifi_switch_row.set_sensitive(bool(wifi.get("available")))
            self._wifi_switch_row.set_active(bool(wifi.get("enabled")))
            msg = wifi.get("message") or (i18n.t("available") if wifi.get("available") else i18n.t("unavailable"))
            self._wifi_switch_row.set_subtitle(str(msg))
            self._wifi_switch_guard = False

            self._clear_listbox(self._wifi_list)
            for conn in wifi.get("connections") or []:
                row = Adw.ActionRow()
                ssid = str(conn.get("ssid") or "")
                title = ssid or i18n.t("hidden_ssid")
                active = f" · {i18n.t('connected')}" if conn.get("active") else ""
                row.set_title(title)
                row.set_subtitle(f"{i18n.t('signal')} {conn.get('signal')}% · {conn.get('security')}{active}")
                if ssid and not conn.get("active"):
                    conn_btn = Gtk.Button(label=i18n.t("connect"))
                    conn_btn.add_css_class("suggested-action")
                    conn_btn.set_valign(Gtk.Align.CENTER)
                    conn_btn.connect("clicked", lambda *_a, s=ssid: self._wifi_connect(s))
                    row.add_suffix(conn_btn)
                if ssid:
                    forget_btn = Gtk.Button(label=i18n.t("forget"))
                    forget_btn.set_valign(Gtk.Align.CENTER)
                    forget_btn.connect("clicked", lambda *_a, s=ssid: self._wifi_forget(s))
                    row.add_suffix(forget_btn)
                self._wifi_list.append(row)
            if not (wifi.get("connections") or []):
                empty = Adw.ActionRow(title=i18n.t("no_network"), subtitle=i18n.t("wifi_scan_hint"))
                self._wifi_list.append(empty)

            self._bt_switch_guard = True
            self._bt_switch_row.set_sensitive(bool(bt.get("available")))
            self._bt_switch_row.set_active(bool(bt.get("powered")))
            bt_msg = bt.get("message") or (i18n.t("available") if bt.get("available") else i18n.t("unavailable"))
            self._bt_switch_row.set_subtitle(str(bt_msg))
            self._bt_switch_guard = False

            self._clear_listbox(self._bt_list)
            for dev in bt.get("devices") or []:
                row = Adw.ActionRow()
                row.set_title(str(dev.get("name") or "?"))
                row.set_subtitle(str(dev.get("mac") or ""))
                self._bt_list.append(row)
            if not (bt.get("devices") or []):
                self._bt_list.append(Adw.ActionRow(title=i18n.t("no_device"), subtitle="—"))

        run_in_thread(work, done)

    def _conn_kind_label(self, kind: str) -> str:
        keys = {
            "known": "conn_kind_known",
            "unknown": "conn_kind_unknown",
            "listen": "conn_kind_listen",
        }
        return i18n.t(keys.get(kind, "conn_kind_unknown"))

    def _refresh_connections(self, *, show_spinner: bool = False, privileged: bool = False) -> None:
        if show_spinner:
            self._network_spinner.set_visible(True)
        if privileged:
            show_toast(self._toast_overlay, i18n.t("conn_reading_admin"), timeout=4)

        def work() -> dict[str, Any]:
            allowlist = list(self._settings.get("connection_allowlist") or [])
            return connections.list_connections(privileged=privileged, allowlist=allowlist)

        def done(result: Any, error: BaseException | None) -> None:
            self._network_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            data = result if isinstance(result, dict) else {}
            items = list(data.get("items") or [])
            self._connection_items = items
            self._render_connections(data)

        run_in_thread(work, done)

    def _render_connections(self, data: dict[str, Any]) -> None:
        if not hasattr(self, "_conn_list"):
            return
        self._clear_listbox(self._conn_list)
        available = bool(data.get("available"))
        message = str(data.get("message") or "").strip()
        needs_admin = bool(data.get("needs_elevation"))
        items = list(data.get("items") or [])
        status_bits: list[str] = []
        if not available:
            status_bits.append(message or i18n.t("conn_empty"))
        else:
            status_bits.append(f"{len(items)}")
            if needs_admin:
                status_bits.append(i18n.t("conn_needs_admin"))
            elif message:
                status_bits.append(message)
        self._conn_status.set_text(" · ".join(status_bits) if status_bits else "—")

        if not available:
            self._conn_list.append(
                Adw.ActionRow(title=i18n.t("conn_chip"), subtitle=message or i18n.t("conn_empty"))
            )
            return
        if not items:
            self._conn_list.append(Adw.ActionRow(title=i18n.t("conn_empty"), subtitle="—"))
            return
        for item in items:
            row = Adw.ActionRow()
            comm = str(item.get("comm") or "?")
            pid = item.get("pid")
            title = f"{comm} · PID {pid}" if pid is not None else f"{comm} · PID —"
            row.set_title(title)
            kind = str(item.get("kind") or "unknown")
            proto = str(item.get("proto") or "")
            state = str(item.get("state") or "")
            local = str(item.get("local") or "")
            remote = str(item.get("remote") or "")
            row.set_subtitle(
                f"{proto} {state} {local} → {remote} · {self._conn_kind_label(kind)}"
            )
            row.set_activatable(True)
            row.connect("activated", lambda *_a, it=item: self._show_connection_detail(it))
            if kind == "unknown":
                mark_btn = Gtk.Button(label=i18n.t("conn_mark_known"))
                mark_btn.set_valign(Gtk.Align.CENTER)
                mark_btn.connect("clicked", lambda *_a, it=item: self._mark_connection_known(it))
                row.add_suffix(mark_btn)
            self._conn_list.append(row)

    def _show_connection_detail(self, item: dict[str, Any]) -> None:
        raw = str(item.get("raw") or "").strip() or "—"
        remote = str(item.get("remote") or "")
        body = (
            f"{item.get('comm') or '?'}  PID {item.get('pid') if item.get('pid') is not None else '—'}\n"
            f"{item.get('proto') or ''} {item.get('state') or ''}\n"
            f"{item.get('local') or ''} → {remote}\n"
            f"{self._conn_kind_label(str(item.get('kind') or ''))}\n\n"
            f"{raw}"
        )
        dialog = make_message_dialog(self, i18n.t("conn_detail"), body)
        dialog.add_response("close", i18n.t("cancel"))
        dialog.add_response("copy", i18n.t("conn_copy"))

        def on_response(_d: object, response: str) -> None:
            if response == "copy":
                self._copy_connection_dest(remote)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _copy_connection_dest(self, remote: str) -> None:
        display = Gdk.Display.get_default() if hasattr(Gdk, "Display") else None
        getter = getattr(display, "get_clipboard", None) if display is not None else None
        clipboard = getter() if callable(getter) else None
        setter = getattr(clipboard, "set", None)
        if not callable(setter):
            show_toast(self._toast_overlay, i18n.t("conn_no_clipboard"))
            return
        setter(remote)
        show_toast(self._toast_overlay, i18n.t("conn_copied"))

    def _export_connections(self) -> None:
        items = list(self._connection_items)
        if not items:
            show_toast(self._toast_overlay, i18n.t("conn_no_export"))
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = Path.home() / "Documents" / f"hub-systeme-connexions-{stamp}.csv"

        def work() -> Path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(connections.to_csv(items), encoding="utf-8")
            return path

        def done(result: Any, error: BaseException | None) -> None:
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, i18n.t("conn_exported", path=str(result)))

        run_in_thread(work, done)

    def _mark_connection_known(self, item: dict[str, Any]) -> None:
        ip_text = connections.endpoint_ip(str(item.get("remote") or ""))
        try:
            updated = connections.add_allowlist_entry(
                ip_text,
                list(self._settings.get("connection_allowlist") or []),
            )
        except connections.ConnectionError as exc:
            show_toast(self._toast_overlay, i18n.t("conn_allow_failed", detail=str(exc)))
            return
        self._settings["connection_allowlist"] = updated
        app_settings.save_settings(self._settings)
        show_toast(self._toast_overlay, i18n.t("conn_marked", ip=ip_text))
        self._refresh_connections(show_spinner=True)

    def _open_allowlist_dialog(self) -> None:
        entry = Gtk.Entry()
        set_placeholder_text(entry, i18n.t("conn_allowlist_hint"))
        current = ", ".join(list(self._settings.get("connection_allowlist") or []))
        body = current or "—"
        dialog = make_message_dialog(
            self,
            i18n.t("conn_allowlist_title"),
            body,
            extra_child=entry,
        )
        dialog.add_response("cancel", i18n.t("cancel"))
        dialog.add_response("add", i18n.t("save"))
        dialog.set_default_response("add")

        def on_response(_d: object, response: str) -> None:
            if response != "add":
                return
            try:
                updated = connections.add_allowlist_entry(
                    entry.get_text(),
                    list(self._settings.get("connection_allowlist") or []),
                )
            except connections.ConnectionError as exc:
                show_toast(self._toast_overlay, i18n.t("conn_allow_failed", detail=str(exc)))
                return
            self._settings["connection_allowlist"] = updated
            app_settings.save_settings(self._settings)
            show_toast(self._toast_overlay, i18n.t("conn_marked", ip=entry.get_text().strip()))
            self._refresh_connections(show_spinner=True)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _wifi_connect(self, ssid: str) -> None:
        entry = Gtk.PasswordEntry()
        call_if = getattr(entry, "set_show_peek_icon", None)
        if callable(call_if):
            call_if(True)
        set_placeholder_text(entry, i18n.t("wifi_password"))
        dialog = make_message_dialog(self, i18n.t("connect"), ssid, extra_child=entry)
        dialog.add_response("cancel", i18n.t("cancel"))
        dialog.add_response("ok", i18n.t("connect"))
        dialog.set_response_appearance("ok", response_appearance("SUGGESTED"))

        def on_response(_d: object, response: str) -> None:
            if response != "ok":
                return
            password = entry.get_text() or None
            self._set_busy(True)

            def work() -> None:
                network_ctl.wifi_connect(ssid, password)

            def done(_r: Any, error: BaseException | None) -> None:
                self._set_busy(False)
                if error is not None:
                    show_toast(self._toast_overlay, str(error), timeout=8)
                    return
                show_toast(self._toast_overlay, f"{i18n.t('connect')}: {ssid}")
                self._refresh_network(show_spinner=True)

            run_in_thread(work, done)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _wifi_forget(self, ssid: str) -> None:
        confirm_dialog(
            self,
            i18n.t("forget"),
            ssid,
            confirm_label=i18n.t("forget"),
            destructive=True,
            on_confirm=lambda: self._do_wifi_forget(ssid),
        )

    def _do_wifi_forget(self, ssid: str) -> None:
        self._set_busy(True)

        def work() -> None:
            network_ctl.wifi_forget(ssid)

        def done(_r: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, f"{i18n.t('forget')}: {ssid}")
            self._refresh_network(show_spinner=True)

        run_in_thread(work, done)

    # --- security ---

    def _build_security_page(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("page-toolbar")
        title = Gtk.Label(label=i18n.t("security_title"), xalign=0)
        title.add_css_class("heading")
        title.set_hexpand(True)
        self._security_spinner = make_spinner(size=18)
        self._security_spinner.set_visible(False)
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.connect("clicked", lambda *_: self._refresh_security(show_spinner=True))
        bar.append(title)
        bar.append(self._security_spinner)
        bar.append(refresh_btn)
        root.append(bar)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        clamp = Adw.Clamp(maximum_size=900)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        clamp.set_margin_bottom(12)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        fw_group = Adw.PreferencesGroup()
        fw_group.set_title(i18n.t("firewall"))
        self._fw_status_row = Adw.ActionRow(title=i18n.t("status"), subtitle="—")
        fw_group.add(self._fw_status_row)
        fw_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fw_btns.set_margin_start(12)
        fw_btns.set_margin_end(12)
        fw_btns.set_margin_bottom(8)
        enable_fw = Gtk.Button(label=i18n.t("enable"))
        enable_fw.add_css_class("suggested-action")
        enable_fw.connect("clicked", lambda *_: self._set_firewall(True))
        disable_fw = Gtk.Button(label=i18n.t("disable"))
        disable_fw.add_css_class("destructive-action")
        disable_fw.connect("clicked", lambda *_: self._set_firewall(False))
        load_rules = Gtk.Button(label=i18n.t("load_rules_admin"))
        load_rules.connect(
            "clicked",
            lambda *_: self._refresh_security(show_spinner=True, privileged=True),
        )
        self._track_privileged(enable_fw)
        self._track_privileged(disable_fw)
        self._track_privileged(load_rules)
        fw_btns.append(enable_fw)
        fw_btns.append(disable_fw)
        fw_btns.append(load_rules)
        box.append(fw_group)
        box.append(fw_btns)

        self._fw_rules_list = Gtk.ListBox()
        self._fw_rules_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._fw_rules_list.add_css_class("boxed-list")
        box.append(self._section(i18n.t("rules"), self._fw_rules_list))

        self._users_list = Gtk.ListBox()
        self._users_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._users_list.add_css_class("boxed-list")
        box.append(self._section(i18n.t("users"), self._users_list))

        power_group = Adw.PreferencesGroup()
        power_group.set_title(i18n.t("power_cpu"))
        self._governor_row = Adw.ActionRow(title=i18n.t("governor"), subtitle="—")
        self._profile_row = Adw.ActionRow(title=i18n.t("power_profile"), subtitle="—")
        power_group.add(self._governor_row)
        power_group.add(self._profile_row)
        box.append(power_group)

        self._power_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._power_buttons.set_margin_start(4)
        box.append(self._section(i18n.t("actions"), self._power_buttons))

        clamp.set_child(box)
        scrolled.set_child(clamp)
        root.append(scrolled)
        return root

    def _set_firewall(self, enabled: bool) -> None:
        confirm_dialog(
            self,
            f"{'Activer' if enabled else 'Désactiver'} UFW ?",
            "Cette action utilise pkexec et demande des droits administrateur.",
            confirm_label="Confirmer",
            destructive=not enabled,
            on_confirm=lambda: self._do_set_firewall(enabled),
        )

    def _do_set_firewall(self, enabled: bool) -> None:
        self._set_busy(True)
        show_toast(self._toast_overlay, "Modification du pare-feu…", timeout=3)

        def work() -> None:
            firewall.set_enabled(enabled)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, f"UFW {'activé' if enabled else 'désactivé'}")
            self._refresh_security()

        run_in_thread(work, done)

    def _lock_user(self, username: str, lock: bool) -> None:
        confirm_dialog(
            self,
            f"{'Verrouiller' if lock else 'Déverrouiller'} {username} ?",
            "Action privilégiée via pkexec usermod.",
            confirm_label="Confirmer",
            destructive=lock,
            on_confirm=lambda: self._do_lock_user(username, lock),
        )

    def _do_lock_user(self, username: str, lock: bool) -> None:
        self._set_busy(True)

        def work() -> None:
            users.lock_user(username, lock)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(
                self._toast_overlay,
                f"Utilisateur {username} {'verrouillé' if lock else 'déverrouillé'}",
            )
            self._refresh_security()

        run_in_thread(work, done)

    def _apply_governor(self, name: str) -> None:
        self._set_busy(True)

        def work() -> None:
            power.set_governor(name)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, f"Governor: {name}")
            self._refresh_security()

        run_in_thread(work, done)

    def _apply_power_profile(self, name: str) -> None:
        self._set_busy(True)

        def work() -> None:
            power.set_power_profile(name)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, f"Profil: {name}")
            self._refresh_security()

        run_in_thread(work, done)

    def _refresh_security(self, *, show_spinner: bool = False, privileged: bool = False) -> None:
        if show_spinner:
            self._security_spinner.set_visible(True)
        if privileged:
            show_toast(
                self._toast_overlay,
                "Lecture UFW (demande de mot de passe admin)…",
                timeout=4,
            )

        def work() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
            return firewall.status(privileged=privileged), users.list_users(), power.list_governors()

        def done(result: Any, error: BaseException | None) -> None:
            self._security_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, f"Sécurité: {error}")
                return
            fw, user_list, gov = result
            active = i18n.t("fw_active") if fw.get("active") else i18n.t("fw_inactive")
            avail = i18n.t("available") if fw.get("available") else i18n.t("unavailable")
            backend = str(fw.get("backend") or "?")
            msg = str(fw.get("message") or "").strip()
            subtitle = f"{backend} · {avail} · {active}"
            if msg:
                subtitle = f"{subtitle} — {msg}"
            self._fw_status_row.set_title(f"{i18n.t('status')} ({backend})")
            self._fw_status_row.set_subtitle(subtitle)
            self._clear_listbox(self._fw_rules_list)
            for rule in fw.get("rules") or []:
                self._fw_rules_list.append(Adw.ActionRow(title=str(rule)[:120]))
            if not (fw.get("rules") or []):
                hint = (
                    "Cliquez « Charger les règles (admin) » pour afficher le détail UFW"
                    if fw.get("needs_elevation")
                    else (msg or "Aucune règle affichée")
                )
                self._fw_rules_list.append(Adw.ActionRow(title=hint[:120]))

            self._clear_listbox(self._users_list)
            for user in user_list:
                row = Adw.ActionRow()
                row.set_title(str(user.get("name")))
                row.set_subtitle(
                    f"uid {user.get('uid')} · {user.get('home')} · {user.get('shell')}"
                )
                name = str(user.get("name"))
                lock_btn = Gtk.Button(label="Verrouiller")
                lock_btn.add_css_class("destructive-action")
                lock_btn.set_valign(Gtk.Align.CENTER)
                lock_btn.set_sensitive(self._busy_ops == 0)
                lock_btn.connect("clicked", lambda *_a, n=name: self._lock_user(n, True))
                unlock_btn = Gtk.Button(label="Déverrouiller")
                unlock_btn.set_valign(Gtk.Align.CENTER)
                unlock_btn.set_sensitive(self._busy_ops == 0)
                unlock_btn.connect("clicked", lambda *_a, n=name: self._lock_user(n, False))
                row.add_suffix(lock_btn)
                row.add_suffix(unlock_btn)
                self._users_list.append(row)

            self._governor_row.set_subtitle(str(gov.get("governor") or "—"))
            self._profile_row.set_subtitle(str(gov.get("power_profile") or "—"))

            while True:
                child = self._power_buttons.get_first_child()
                if child is None:
                    break
                self._power_buttons.remove(child)

            for name in gov.get("available_governors") or []:
                btn = Gtk.Button(label=str(name))
                btn.set_sensitive(self._busy_ops == 0)
                btn.connect("clicked", lambda *_a, n=str(name): self._apply_governor(n))
                self._power_buttons.append(btn)
            for name in gov.get("power_profiles") or []:
                btn = Gtk.Button(label=f"Profil: {name}")
                btn.add_css_class("suggested-action")
                btn.set_sensitive(self._busy_ops == 0)
                btn.connect("clicked", lambda *_a, n=str(name): self._apply_power_profile(n))
                self._power_buttons.append(btn)

        run_in_thread(work, done)

    # --- tools ---

    def _build_tools_page(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("page-toolbar")
        title = Gtk.Label(label=i18n.t("tools_title"), xalign=0)
        title.add_css_class("heading")
        title.set_hexpand(True)
        self._tools_spinner = make_spinner(size=18)
        self._tools_spinner.set_visible(False)
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.connect("clicked", lambda *_: self._refresh_tools(show_spinner=True))
        bar.append(title)
        bar.append(self._tools_spinner)
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
        export_btn.connect("clicked", lambda *_: self._export_html_report())
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
        ensure_btn.connect("clicked", lambda *_: self._ensure_example_plugin())
        ensure_row.add_suffix(ensure_btn)
        plugins_group.add(ensure_row)
        box.append(plugins_group)

        self._plugins_list = Gtk.ListBox()
        self._plugins_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._plugins_list.add_css_class("boxed-list")
        box.append(self._section(i18n.t("plugins_scripts"), self._plugins_list))

        clamp.set_child(box)
        scrolled.set_child(clamp)
        root.append(scrolled)
        return root

    def _export_html_report(self) -> None:
        self._set_busy(True)
        show_toast(self._toast_overlay, "Génération du rapport…", timeout=2)

        def work() -> Path:
            return report.export_report(report.default_report_path())

        def done(result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, f"Rapport: {result}")

        run_in_thread(work, done)

    def _ensure_example_plugin(self) -> None:
        def work() -> Path:
            return plugins.ensure_example_plugin()

        def done(result: Any, error: BaseException | None) -> None:
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, f"Exemple: {result}")
            self._refresh_tools()

        run_in_thread(work, done)

    def _run_plugin(self, name: str) -> None:
        self._set_busy(True)
        show_toast(self._toast_overlay, f"Exécution de {name}…", timeout=2)

        def work() -> dict[str, Any]:
            return plugins.run_plugin(name)

        def done(result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            ok = bool((result or {}).get("ok"))
            out = ((result or {}).get("stdout") or "").strip()
            err = ((result or {}).get("stderr") or "").strip()
            msg = out or err or ("OK" if ok else "Échec")
            show_toast(self._toast_overlay, msg[:180], timeout=5)

        run_in_thread(work, done)

    def _refresh_tools(self, *, show_spinner: bool = False) -> None:
        if show_spinner:
            self._tools_spinner.set_visible(True)

        def work() -> list[dict[str, Any]]:
            plugins.ensure_example_plugin()
            return plugins.list_plugins()

        def done(result: Any, error: BaseException | None) -> None:
            self._tools_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, f"Outils: {error}")
                return
            self._clear_listbox(self._plugins_list)
            for item in result or []:
                row = ActionListRow(
                    str(item.get("name")),
                    str(item.get("path")),
                    button_label="Exécuter",
                    button_css="suggested-action",
                    on_clicked=lambda n=str(item.get("name")): self._run_plugin(n),
                )
                row.set_busy(self._busy_ops > 0)
                self._plugins_list.append(row)
            if not (result or []):
                self._plugins_list.append(
                    Adw.ActionRow(title="Aucun plugin", subtitle=str(plugins.plugins_dir()))
                )

        run_in_thread(work, done)

    # --- backup / timeshift ---

    def _build_sessions_page(self) -> Gtk.Widget:
        from ui.pages import sessions as sessions_page

        return sessions_page.build(self)

    def _refresh_sessions(self, *, show_spinner: bool = False) -> None:
        from ui.pages import sessions as sessions_page

        sessions_page.refresh(self, show_spinner=show_spinner)

    def _build_backup_page(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._backup_stack = Gtk.Stack()
        self._backup_stack.set_vexpand(True)

        self._backup_status_page = Adw.StatusPage()
        self._backup_status_page.set_icon_name("drive-harddisk-symbolic")
        self._backup_status_page.set_title(i18n.t("snapshots"))
        self._backup_status_page.set_description("Vérification…")
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        status_box.set_halign(Gtk.Align.CENTER)
        refresh_missing = Gtk.Button(label="Actualiser")
        refresh_missing.connect("clicked", lambda *_: self._refresh_backup(show_spinner=True))
        status_box.append(refresh_missing)
        self._backup_status_page.set_child(status_box)
        self._backup_stack.add_named(self._backup_status_page, "status")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(18)
        content.set_margin_bottom(18)
        content.set_margin_start(18)
        content.set_margin_end(18)

        self._backup_status = Gtk.Label(label=f"{i18n.t('snapshots')}: —", xalign=0)
        self._backup_status.add_css_class("title-4")
        content.append(self._backup_status)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        refresh_btn = Gtk.Button(label=i18n.t("refresh"))
        refresh_btn.connect("clicked", lambda *_: self._refresh_backup(show_spinner=True))
        load_btn = Gtk.Button(label=i18n.t("load_snapshots_admin"))
        load_btn.connect(
            "clicked",
            lambda *_: self._refresh_backup(show_spinner=True, privileged=True),
        )
        create_btn = Gtk.Button(label=i18n.t("create_snapshot"))
        create_btn.add_css_class("suggested-action")
        create_btn.connect("clicked", lambda *_: self._confirm_snapshot())
        self._track_privileged(load_btn)
        self._track_privileged(create_btn)
        self._backup_spinner = make_spinner(size=18)
        self._backup_spinner.set_visible(False)
        self._btrfs_assistant_btn = Gtk.Button(label=i18n.t("open_btrfs_assistant"))
        self._btrfs_assistant_btn.set_visible(False)
        self._btrfs_assistant_btn.connect(
            "clicked",
            lambda *_: self._open_btrfs_assistant(),
        )
        controls.append(refresh_btn)
        controls.append(load_btn)
        controls.append(create_btn)
        controls.append(self._btrfs_assistant_btn)
        controls.append(self._backup_spinner)
        content.append(controls)

        self._snapshot_list = Gtk.ListBox()
        self._snapshot_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._snapshot_list.add_css_class("boxed-list")
        clamp = Adw.Clamp(maximum_size=900)
        clamp.set_child(self._snapshot_list)
        content.append(clamp)
        self._backup_stack.add_named(content, "content")

        root.append(self._backup_stack)
        return root

    def _refresh_backup(self, *, show_spinner: bool = False, privileged: bool = False) -> None:
        if show_spinner:
            self._backup_spinner.set_visible(True)
        if privileged:
            show_toast(
                self._toast_overlay,
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
            self._backup_spinner.set_visible(False)
            if error is not None:
                show_toast(self._toast_overlay, f"{i18n.t('snapshots')}: {error}")
                self._backup_status_page.set_title(i18n.t("snapshots"))
                self._backup_status_page.set_description(str(error))
                self._backup_stack.set_visible_child_name("status")
                return
            st, snaps, list_error = result
            if not st.get("available"):
                self._backup_status_page.set_icon_name("dialog-warning-symbolic")
                self._backup_status_page.set_title(i18n.t("snapshots"))
                self._backup_status_page.set_description(
                    st.get("message") or i18n.t("snapshots_desc")
                )
                self._backup_stack.set_visible_child_name("status")
                return

            self._backup_stack.set_visible_child_name("content")
            status_msg = str(st.get("message") or "").strip()
            if list_error:
                status_msg = list_error
            elif snaps:
                status_msg = i18n.t("snapshots_n", count=len(snaps))
            backend = str(st.get("backend") or "?")
            assist = st.get("btrfs_assistant")
            if hasattr(self, "_btrfs_assistant_btn"):
                self._btrfs_assistant_btn.set_visible(bool(assist))
            self._backup_status.set_text(f"{i18n.t('backend')}: {backend} — {status_msg}")
            self._clear_listbox(self._snapshot_list)
            if not snaps:
                row = Adw.ActionRow()
                row.set_title(i18n.t("no_snapshot"))
                row.set_subtitle(
                    list_error
                    or "Cliquez « Charger les clichés (admin) » ou créez un snapshot."
                )
                self._snapshot_list.append(row)
                return
            for snap in snaps:
                name = str(snap.get("name") or "")
                row = Adw.ActionRow()
                row.set_title(name or "?")
                row.set_subtitle(
                    f"{snap.get('date', '')} · {snap.get('type', snap.get('tags', ''))} · {snap.get('description', '')}"
                )
                restore_btn = Gtk.Button(label="Restaurer")
                restore_btn.add_css_class("destructive-action")
                restore_btn.set_valign(Gtk.Align.CENTER)
                restore_btn.set_sensitive(self._busy_ops == 0)
                restore_btn.connect("clicked", lambda *_a, n=name: self._confirm_restore(n))
                row.add_suffix(restore_btn)
                if snap.get("backend") == "snapper" and name not in {"0", ""}:
                    del_btn = Gtk.Button(label="Supprimer")
                    del_btn.set_valign(Gtk.Align.CENTER)
                    del_btn.connect("clicked", lambda *_a, n=name: self._confirm_delete_snap(n))
                    row.add_suffix(del_btn)
                self._snapshot_list.append(row)

        run_in_thread(work, done)

    def _confirm_snapshot(self) -> None:
        confirm_dialog(
            self,
            i18n.t("create_snapshot"),
            i18n.t("snapshots_desc"),
            confirm_label=i18n.t("create"),
            destructive=False,
            on_confirm=self._do_create_snapshot,
        )

    def _do_create_snapshot(self) -> None:
        self._set_busy(True)
        show_toast(self._toast_overlay, i18n.t("snapshot_creating"), timeout=5)

        def work() -> dict[str, Any]:
            return backup.create_snapshot(i18n.t("snapshot_comment"))

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, i18n.t("snapshot_created"))
            self._refresh_backup(privileged=True)

        run_in_thread(work, done)

    def _confirm_restore(self, name: str) -> None:
        if not name:
            show_toast(self._toast_overlay, "Cliché invalide")
            return
        confirm_dialog(
            self,
            f"Restaurer le cliché {name} ?",
            "Cette opération réécrit les fichiers système via pkexec timeshift "
            "et peut nécessiter un redémarrage. Confirmez uniquement si vous "
            "êtes prêt à restaurer l'hôte.",
            confirm_label="Restaurer",
            destructive=True,
            on_confirm=lambda: self._do_restore_snapshot(name),
        )

    def _do_restore_snapshot(self, name: str) -> None:
        self._set_busy(True)
        show_toast(self._toast_overlay, f"Restauration de {name}…", timeout=8)

        def work() -> dict[str, Any]:
            return backup.restore_snapshot(name)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(
                self._toast_overlay,
                "Restauration terminée. Redémarrez le système si Timeshift le demande.",
                timeout=8,
            )
            self._refresh_backup(privileged=True)

        run_in_thread(work, done)


    def _open_btrfs_assistant(self) -> None:
        try:
            backup.open_btrfs_assistant()
        except backup.BackupError as exc:
            show_toast(self._toast_overlay, str(exc))

    def _confirm_delete_snap(self, name: str) -> None:
        confirm_dialog(
            self,
            f"Supprimer le cliché {name} ?",
            "Suppression Snapper via pkexec.",
            confirm_label="Supprimer",
            destructive=True,
            on_confirm=lambda: self._do_delete_snap(name),
        )

    def _do_delete_snap(self, name: str) -> None:
        self._set_busy(True)

        def work() -> dict[str, Any]:
            return backup.delete_snapshot(name)

        def done(_result: Any, error: BaseException | None) -> None:
            self._set_busy(False)
            if error is not None:
                show_toast(self._toast_overlay, str(error))
                return
            show_toast(self._toast_overlay, f"Cliché {name} supprimé")
            self._refresh_backup(privileged=True)

        run_in_thread(work, done)

    # --- monitoring thread ---

    def _queue_metrics(self, metrics: dict[str, Any]) -> None:
        self._pending_metrics = metrics
        if not self._metrics_flush_scheduled:
            self._metrics_flush_scheduled = True
            GLib.idle_add(self._flush_metrics)

    def _flush_metrics(self) -> bool:
        self._metrics_flush_scheduled = False
        metrics = self._pending_metrics
        self._pending_metrics = None
        if metrics is not None:
            self._update_dashboard(metrics)
        return False

    def _start_monitoring(self) -> bool:
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return False

        def loop() -> None:
            try:
                monitoring.collect_metrics()
            except Exception:  # noqa: BLE001
                pass
            while not self._monitor_stop.wait(2.0):
                try:
                    metrics = monitoring.collect_metrics()
                except Exception as exc:  # noqa: BLE001
                    GLib.idle_add(
                        lambda e=exc: show_toast(self._toast_overlay, f"Monitoring: {e}") or False
                    )
                    continue
                GLib.idle_add(lambda m=metrics: self._queue_metrics(m) or False)

        self._monitor_thread = threading.Thread(target=loop, name="monitoring", daemon=True)
        self._monitor_thread.start()
        return False

    def _set_auto_update_enabled(self, enabled: bool) -> None:
        self._settings["auto_update_on_startup"] = bool(enabled)
        app_settings.save_settings(self._settings)
        self._settings = app_settings.load_settings()

    def _manual_check_updates(self, row: ActionListRow | None = None) -> None:
        if row is not None:
            row.set_busy(True)
        show_toast(self._toast_overlay, i18n.t("update_checking"), timeout=4)

        def work() -> dict[str, Any] | None:
            return updater.check_for_update(raise_on_error=True)

        def done(result: Any, error: BaseException | None) -> None:
            if row is not None:
                row.set_busy(False)
            if error is not None:
                show_toast(
                    self._toast_overlay,
                    i18n.t("update_check_failed", detail=str(error)),
                    timeout=8,
                )
                return
            if not isinstance(result, dict):
                show_toast(
                    self._toast_overlay,
                    i18n.t("update_up_to_date", version=updater.local_version()),
                    timeout=5,
                )
                return
            self._show_update_dialog(result)

        run_in_thread(work, done)

    def _poll_update_proceed_flag(self) -> bool:
        flag = updater.updates_dir() / "proceed-install"
        if flag.is_file():
            try:
                flag.unlink(missing_ok=True)
            except OSError:
                pass
            return self._quit_for_update()
        deadline = float(getattr(self, "_update_poll_deadline", 0.0) or 0.0)
        if deadline and time.monotonic() > deadline:
            self._update_in_progress = False
            return False
        if not self._update_in_progress:
            return False
        return True

    def _maybe_check_updates(self) -> bool:
        if not bool(self._settings.get("auto_update_on_startup", True)):
            return False

        def work() -> dict[str, Any] | None:
            return updater.check_for_update()

        def done(result: Any, error: BaseException | None) -> None:
            if error is not None or not isinstance(result, dict):
                return
            self._show_update_dialog(result)

        run_in_thread(work, done)
        return False

    def _check_startup_compatibility(self) -> bool:
        def work() -> dict[str, Any]:
            return compat.collect_startup_compatibility()

        def done(result: Any, error: BaseException | None) -> None:
            if error is not None or not isinstance(result, dict):
                return
            warnings = result.get("warnings") or []
            if not warnings:
                return
            first = str(warnings[0])
            show_toast(
                self._toast_overlay,
                i18n.t("compat_degraded", detail=first),
                timeout=8,
            )

        run_in_thread(work, done)
        return False

    def _show_update_dialog(self, info: dict[str, Any]) -> None:
        from ui_kit.dialogs.update import present as present_update_dialog

        latest = str(info.get("version") or "?")
        present_update_dialog(
            self,
            i18n.t("update_available"),
            updater.format_update_dialog_body(info),
            updater.format_update_dialog_commands(info),
            new_version=latest,
            lang=i18n.get_language(),
        )

    def _quit_for_update(self) -> bool:
        app = self.get_application()
        if app is not None:
            app.quit()
        return False

    def _show_update_restart_dialog(self) -> None:
        dialog = make_message_dialog(
            self,
            i18n.t("update_installed"),
            i18n.t("update_restart_body", command=updater.restart_hint()),
        )
        dialog.add_response("close", i18n.t("update_close"))
        dialog.add_response("quit", i18n.t("update_quit"))
        dialog.set_response_appearance("quit", response_appearance("SUGGESTED"))
        dialog.set_default_response("quit")
        dialog.set_close_response("close")

        def on_response(_dialog: object, response: str) -> None:
            if response == "quit":
                app = self.get_application()
                if app is not None:
                    app.quit()

        dialog.connect("response", on_response)
        dialog.present(self)

    def _on_close(self, *_args: Any) -> bool:
        self._monitor_stop.set()
        return False
