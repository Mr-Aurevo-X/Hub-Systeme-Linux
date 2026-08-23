#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hub Système — point d'entrée GTK4 / Libadwaita."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from core.display_env import apply_safe_display_env, host_needs_map_hold

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ui_kit.bootstrap import ensure_ui_kit_on_path  # noqa: E402

ensure_ui_kit_on_path(_ROOT)

_applied = apply_safe_display_env()
for _key, _value in _applied.items():
    print(f"{_key}={_value}", flush=True)
_HOLD_UNTIL_MAP = host_needs_map_hold()

from core.host import install_flatpak_host_bridge

install_flatpak_host_bridge()

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib  # noqa: E402

from core import i18n  # noqa: E402
from core import settings as app_settings  # noqa: E402
from core.migrate import run_first_launch_migration  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

_MAP_TIMEOUT_MS = 3000
_MAP_FAIL_MSG = (
    "ERREUR : la fenêtre GTK ne s’est pas affichée (map, 3 s).\n"
    "Cause probable : GSK/GL encore actif ou X11/VirtualBox (libEGL DRI2).\n"
    "Attendu : GSK_RENDERER=cairo GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1\n"
    "Paquets : sudo apt install python3-gi-cairo python3-cairo"
)


def _launch_log_path() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / "hub-systeme" / "launch.log"


def _append_launch_log(message: str) -> None:
    path = _launch_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(message.rstrip() + "\n")
    except OSError:
        pass


class HubSystemeApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="org.mraurevox.HubSysteme",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._window: MainWindow | None = None
        self._held_until_map = False
        self._window_mapped = False
        self._map_failed = False
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._on_quit)
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def _on_quit(self, *_args: object) -> None:
        self.quit()

    def _on_main_mapped(self, *_args: object) -> None:
        self._window_mapped = True
        if self._held_until_map:
            self.release()
            self._held_until_map = False

    def _on_map_timeout(self) -> bool:
        if self._window_mapped:
            return False
        print(_MAP_FAIL_MSG, flush=True)
        _append_launch_log(_MAP_FAIL_MSG)
        self._map_failed = True
        self.quit()
        return False

    def do_activate(self) -> None:  # noqa: N802 - GObject override
        style = Adw.StyleManager.get_default()
        style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        from ui_kit.theme import apply_theme

        apply_theme(config_app_id="hub-systeme")

        run_first_launch_migration()
        cfg = app_settings.load_settings()
        i18n.set_language(app_settings.coerce_language(cfg.get("language")))

        if self._window is None:
            self._window = MainWindow(application=self)
            if _HOLD_UNTIL_MAP:
                self._window.connect("map", self._on_main_mapped)
                self.hold()
                self._held_until_map = True
                GLib.timeout_add(_MAP_TIMEOUT_MS, self._on_map_timeout)
        self._window.set_visible(True)
        self._window.present()


def main(argv: list[str] | None = None) -> int:
    app = HubSystemeApp()
    code = int(app.run(argv or sys.argv))
    if app._map_failed:
        return 1
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise
