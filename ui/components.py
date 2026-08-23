# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable GTK4 / Libadwaita widgets for Gest_Linux_Pro."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402


def make_spinner(*, size: int = 24) -> Gtk.Widget:
    """Prefer Adw.Spinner (libadwaita ≥ 1.6), fall back to Gtk.Spinner."""
    spinner_cls = getattr(Adw, "Spinner", None)
    if spinner_cls is not None:
        widget = spinner_cls()
        widget.set_halign(Gtk.Align.CENTER)
        widget.set_valign(Gtk.Align.CENTER)
        widget.set_size_request(size, size)
        return widget
    spinner = Gtk.Spinner()
    spinner.set_spinning(True)
    spinner.set_halign(Gtk.Align.CENTER)
    spinner.set_valign(Gtk.Align.CENTER)
    spinner.set_size_request(size, size)
    return spinner


class CircularGauge(Gtk.Box):
    """Circular percentage gauge with smooth animation toward targets."""

    def __init__(self, title: str = "CPU", *, size: int = 140) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_halign(Gtk.Align.CENTER)
        self._value = 0.0
        self._target = 0.0
        self._title = title
        self._size = size
        self._accent = (0.35, 0.78, 0.98)
        self._anim_id: int | None = None
        self._label_override: str | None = None

        self._area = Gtk.DrawingArea()
        self._area.set_content_width(size)
        self._area.set_content_height(size)
        self._area.set_draw_func(self._on_draw)
        self.append(self._area)

        self._label = Gtk.Label(label=title)
        self._label.add_css_class("caption")
        self._label.set_halign(Gtk.Align.CENTER)
        self.append(self._label)

        self._value_label = Gtk.Label(label="0%")
        self._value_label.add_css_class("title-2")
        self._value_label.set_halign(Gtk.Align.CENTER)
        self.append(self._value_label)

    def set_accent(self, r: float, g: float, b: float) -> None:
        self._accent = (r, g, b)
        self._area.queue_draw()

    def set_value(self, percent: float, *, display: str | None = None) -> None:
        self._label_override = display
        self._target = max(0.0, min(100.0, float(percent)))
        if self._anim_id is None:
            self._anim_id = GLib.timeout_add(16, self._tick_anim)

    def set_value_immediate(self, percent: float) -> None:
        self._label_override = None
        self._target = max(0.0, min(100.0, float(percent)))
        self._value = self._target
        self._value_label.set_text(f"{self._value:.0f}%")
        self._area.queue_draw()
        if self._anim_id is not None:
            GLib.source_remove(self._anim_id)
            self._anim_id = None

    def set_title(self, title: str) -> None:
        self._title = title
        self._label.set_text(title)

    def set_value_label(self, text: str) -> None:
        self._label_override = text
        self._value_label.set_text(text)

    def set_unavailable(self, label: str = "N/A") -> None:
        self._label_override = label
        self._target = 0.0
        self._value = 0.0
        self._value_label.set_text(label)
        self._area.queue_draw()
        if self._anim_id is not None:
            GLib.source_remove(self._anim_id)
            self._anim_id = None

    def _format_value(self) -> str:
        if self._label_override is not None:
            return self._label_override
        return f"{self._value:.0f}%"

    def _tick_anim(self) -> bool:
        diff = self._target - self._value
        if abs(diff) < 0.25:
            self._value = self._target
            self._value_label.set_text(self._format_value())
            self._area.queue_draw()
            self._anim_id = None
            return False
        self._value += diff * 0.2
        self._value_label.set_text(self._format_value())
        self._area.queue_draw()
        return True

    def _on_draw(self, _area: Gtk.DrawingArea, cr: Any, width: int, height: int) -> None:
        cx, cy = width / 2.0, height / 2.0
        radius = min(width, height) / 2.0 - 10.0
        start = -math.pi / 2.0
        span = (self._value / 100.0) * 2.0 * math.pi

        cr.set_line_width(12.0)
        cr.set_source_rgba(1, 1, 1, 0.12)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        r, g, b = self._accent
        if self._value >= 90:
            r, g, b = 0.95, 0.35, 0.35
        elif self._value >= 70:
            r, g, b = 0.98, 0.72, 0.25
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        cr.set_source_rgb(r, g, b)
        cr.arc(cx, cy, radius, start, start + span)
        cr.stroke()


class CoreBars(Gtk.Box):
    """Compact per-core CPU usage bars."""

    def __init__(self, *, max_cores: int = 64) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._bars: list[Gtk.ProgressBar] = []
        self._labels: list[Gtk.Label] = []
        self._rows: list[Gtk.Box] = []
        self._max_cores = max_cores

    def set_values(self, values: list[float]) -> None:
        count = min(len(values), self._max_cores)
        while len(self._bars) < count:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            label = Gtk.Label(label=f"C{len(self._bars)}", xalign=0)
            label.add_css_class("caption")
            label.set_width_chars(3)
            bar = Gtk.ProgressBar()
            bar.set_hexpand(True)
            bar.set_valign(Gtk.Align.CENTER)
            bar.add_css_class("core-bar")
            row.append(label)
            row.append(bar)
            self.append(row)
            self._rows.append(row)
            self._bars.append(bar)
            self._labels.append(label)

        for idx, bar in enumerate(self._bars):
            visible = idx < count
            self._rows[idx].set_visible(visible)
            if not visible:
                continue
            fraction = max(0.0, min(1.0, float(values[idx]) / 100.0))
            bar.set_fraction(fraction)
            self._labels[idx].set_text(f"C{idx}")
            bar.set_text(f"{values[idx]:.0f}%")
            bar.set_show_text(True)


class Sparkline(Gtk.DrawingArea):
    """Simple sparkline chart for recent metric history."""

    def __init__(self, *, width: int = 220, height: int = 48) -> None:
        super().__init__()
        self._values: list[float] = []
        self._accent = (0.35, 0.78, 0.98)
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_draw_func(self._on_draw)

    def set_accent(self, r: float, g: float, b: float) -> None:
        self._accent = (r, g, b)
        self.queue_draw()

    def set_values(self, values: list[float]) -> None:
        self._values = [float(v) for v in values[-120:]]
        self.queue_draw()

    def _on_draw(self, _area: Gtk.DrawingArea, cr: Any, width: int, height: int) -> None:
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        if len(self._values) < 2:
            return
        vmax = max(self._values) or 1.0
        vmin = min(self._values)
        span = max(vmax - vmin, 1e-6)
        r, g, b = self._accent
        cr.set_source_rgb(r, g, b)
        cr.set_line_width(2.0)
        for idx, value in enumerate(self._values):
            x = idx / (len(self._values) - 1) * (width - 4) + 2
            y = height - 4 - ((value - vmin) / span) * (height - 8)
            if idx == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()


class MetricRow(Gtk.Box):
    """Simple key/value metric row."""

    def __init__(self, key: str, value: str = "—") -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.set_hexpand(True)
        self._key = Gtk.Label(label=key, xalign=0)
        self._key.add_css_class("dim-label")
        self._key.set_hexpand(True)
        self._value = Gtk.Label(label=value, xalign=1)
        self._value.add_css_class("heading")
        self._value.set_wrap(True)
        self._value.set_justify(Gtk.Justification.RIGHT)
        self.append(self._key)
        self.append(self._value)

    def set_key(self, key: str) -> None:
        self._key.set_text(key)

    def set_value(self, value: str) -> None:
        self._value.set_text(value)


class ActionListRow(Adw.ActionRow):
    """Adw.ActionRow with a trailing action button."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        button_label: str = "Action",
        button_css: str = "destructive-action",
        on_clicked: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.set_title(title)
        if subtitle:
            self.set_subtitle(subtitle)
        self._button = Gtk.Button(label=button_label)
        if button_css:
            self._button.add_css_class(button_css)
        self._button.set_valign(Gtk.Align.CENTER)
        if on_clicked is not None:
            self._button.connect("clicked", lambda *_: on_clicked())
        self.add_suffix(self._button)
        self.set_activatable(False)

    @property
    def button(self) -> Gtk.Button:
        return self._button

    def set_busy(self, busy: bool) -> None:
        self._button.set_sensitive(not busy)


def confirm_dialog(
    parent: Gtk.Window,
    heading: str,
    body: str,
    *,
    confirm_label: str | None = None,
    cancel_label: str | None = None,
    destructive: bool = True,
    on_confirm: Callable[[], None] | None = None,
) -> Any:
    from core import i18n
    from ui.adw_compat import make_message_dialog, response_appearance

    dialog = make_message_dialog(parent, heading, body)
    dialog.add_response("cancel", cancel_label or i18n.t("cancel"))
    dialog.add_response("confirm", confirm_label or i18n.t("confirm"))
    appearance = response_appearance("DESTRUCTIVE" if destructive else "SUGGESTED")
    dialog.set_response_appearance("confirm", appearance)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")

    def _on_response(_dialog: object, response: str) -> None:
        if response == "confirm" and on_confirm is not None:
            on_confirm()

    dialog.connect("response", _on_response)
    dialog.present(parent)
    return dialog


def show_toast(overlay: Adw.ToastOverlay, message: str, *, timeout: int = 3) -> None:
    toast = Adw.Toast.new(message)
    toast.set_timeout(timeout)
    overlay.add_toast(toast)


def debounce(delay_ms: int, callback: Callable[[], None]) -> Callable[[], None]:
    """Return a debounced callable that schedules ``callback`` after ``delay_ms``."""
    state: dict[str, int | None] = {"source": None}

    def _fire() -> bool:
        state["source"] = None
        callback()
        return False

    def schedule() -> None:
        existing = state["source"]
        if existing is not None:
            GLib.source_remove(existing)
        state["source"] = GLib.timeout_add(delay_ms, _fire)

    return schedule


def run_in_thread(fn: Callable[[], Any], on_done: Callable[[Any, BaseException | None], None]) -> None:
    """Run ``fn`` in a worker thread and deliver result on the GTK main loop."""
    import threading

    def worker() -> None:
        result: Any = None
        error: BaseException | None = None
        try:
            result = fn()
        except BaseException as exc:  # noqa: BLE001 - delivered to UI
            error = exc
        GLib.idle_add(lambda: on_done(result, error) or False)

    threading.Thread(target=worker, daemon=True).start()


def apply_app_css() -> None:
    css = b"""
    .gauge-card {
      padding: 18px;
      border-radius: 16px;
    }
    .sidebar-nav row {
      padding-top: 8px;
      padding-bottom: 8px;
    }
    .metric-card {
      padding: 12px 16px;
      border-radius: 12px;
    }
    .core-bar trough {
      min-height: 10px;
      border-radius: 6px;
    }
    .core-bar progress {
      border-radius: 6px;
    }
    .page-toolbar {
      padding: 10px 12px;
    }
    .logs-view {
      font-family: monospace;
      padding: 12px;
    }
    .job-console {
      font-family: monospace;
      padding: 8px;
    }
    .filter-chip {
      padding-left: 10px;
      padding-right: 10px;
    }
    .dashboard-hero {
      margin-bottom: 4px;
    }
    .dashboard-gauge-btn {
      padding: 4px;
    }
    .dashboard-gauge:hover {
      opacity: 0.92;
    }
    .dashboard-root {
      margin-top: 4px;
    }
    """
    provider = Gtk.CssProvider()
    try:
        provider.load_from_data(css)
    except TypeError:
        provider.load_from_data(css, -1)  # GTK 4.6 / PyGObject 3.42
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
