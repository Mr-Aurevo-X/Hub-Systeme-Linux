# SPDX-License-Identifier: GPL-3.0-or-later
"""In-app live log for host package scripts (does not kill the process on close)."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import GLib, Gtk  # noqa: E402

from core import i18n, jobs


def present(
    parent: Gtk.Window,
    *,
    title: str,
    script: Path,
    on_finished: Callable[[int], None] | None = None,
) -> None:
    """Open a modal log window and stream ``script`` stdout. Raises ``JobError``."""
    proc = jobs.spawn(script)

    win = Gtk.Window(title=title)
    win.set_transient_for(parent)
    win.set_modal(True)
    win.set_default_size(760, 460)
    win.set_hide_on_close(False)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    header = Gtk.Label(label=title, xalign=0)
    header.add_css_class("title-4")
    header.set_margin_top(12)
    header.set_margin_start(12)
    header.set_margin_end(12)
    header.set_margin_bottom(8)
    box.append(header)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    view = Gtk.TextView()
    view.set_editable(False)
    view.set_cursor_visible(False)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.add_css_class("job-console")
    view.add_css_class("logs-view")
    buf = view.get_buffer()
    end_mark = buf.create_mark("job-end", buf.get_end_iter(), False)
    scrolled.set_child(view)
    box.append(scrolled)

    close_btn = Gtk.Button(label=i18n.t("pkg_job_close"))
    close_btn.set_sensitive(False)
    close_btn.set_margin_top(8)
    close_btn.set_margin_bottom(12)
    close_btn.set_margin_start(12)
    close_btn.set_margin_end(12)
    close_btn.connect("clicked", lambda *_: win.close())
    box.append(close_btn)
    win.set_child(box)

    def append_line(line: str) -> bool:
        buf.insert(buf.get_end_iter(), line)
        buf.move_mark(end_mark, buf.get_end_iter())
        view.scroll_to_mark(end_mark, 0.0, False, 0.0, 1.0)
        return False

    def finished(code: int) -> bool:
        close_btn.set_sensitive(True)
        if on_finished is not None:
            on_finished(code)
        return False

    def on_close(_window: Gtk.Window) -> bool:
        if proc.poll() is None:
            return True
        return False

    win.connect("close-request", on_close)

    def pump() -> None:
        try:
            out = proc.stdout
            if out is not None:
                for line in out:
                    GLib.idle_add(append_line, line)
        finally:
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                pass
            code = proc.returncode if proc.returncode is not None else -1
            GLib.idle_add(finished, code)

    threading.Thread(target=pump, daemon=True).start()
    win.present()
