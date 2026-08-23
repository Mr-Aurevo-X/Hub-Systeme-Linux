# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from core.display_env import cairo_display_env, needs_cairo_gsk, needs_map_hold

_ROOT = Path(__file__).resolve().parents[1]
_MINT_21 = {
    "ID": "linuxmint",
    "VERSION_ID": "21.3",
    "UBUNTU_CODENAME": "jammy",
}
_JAMMY = {"ID": "ubuntu", "VERSION_ID": "22.04", "VERSION_CODENAME": "jammy"}
_CACHY = {"ID": "cachyos", "ID_LIKE": "arch"}


def test_mint_21_needs_cairo() -> None:
    assert needs_cairo_gsk(_MINT_21)
    assert needs_map_hold(_MINT_21)
    env = cairo_display_env(_MINT_21)
    assert env["GSK_RENDERER"] == "cairo"
    assert env["GDK_BACKEND"] == "x11"
    assert env["LIBGL_ALWAYS_SOFTWARE"] == "1"


def test_jammy_needs_cairo() -> None:
    assert needs_cairo_gsk(_JAMMY)
    env = cairo_display_env(_JAMMY)
    assert env["GSK_RENDERER"] == "cairo"
    assert env["GDK_BACKEND"] == "x11"


def test_cachyos_keeps_default_gsk() -> None:
    assert not needs_cairo_gsk(_CACHY)
    assert cairo_display_env(_CACHY) == {}
    assert cairo_display_env(_CACHY, product_name="CachyOS") == {}


def test_cachyos_no_map_hold() -> None:
    assert not needs_map_hold(_CACHY)
    assert not needs_map_hold(_CACHY, product_name="CachyOS")
    text = (_ROOT / "main.py").read_text(encoding="utf-8")
    assert "host_needs_map_hold" in text
    assert "_HOLD_UNTIL_MAP" in text
    assert "if _HOLD_UNTIL_MAP:" in text


def test_virtualbox_needs_cairo() -> None:
    assert needs_cairo_gsk(_CACHY, product_name="VirtualBox")
    env = cairo_display_env(_CACHY, product_name="VirtualBox")
    assert env["GSK_RENDERER"] == "cairo"
    assert env["GDK_BACKEND"] == "x11"
    assert env["LIBGL_ALWAYS_SOFTWARE"] == "1"


def test_lancer_applies_gsk_before_gtk_probe() -> None:
    text = (_ROOT / "LANCER.sh").read_text(encoding="utf-8")
    assert "apply_safe_display_env" in text
    assert "export" in text
    assert 'GSK_RENDERER:-' in text or "${GSK_RENDERER:-}" in text
    assert "python3-gi-cairo" in text
    assert "python3-cairo" in text
    assert '[[ "${GSK_RENDERER:-}" == "cairo" ]]' in text
    assert text.find("apply_safe_display_env") < text.find("from gi.repository import cairo")
    assert text.find("from gi.repository import cairo") < text.find("gi.require_version")


def test_main_holds_until_map() -> None:
    text = (_ROOT / "main.py").read_text(encoding="utf-8")
    assert ".hold()" in text
    assert "set_visible(True)" in text
    assert "timeout_add" in text
    assert "la fenêtre GTK ne s’est pas affichée" in text
    assert "if _HOLD_UNTIL_MAP:" in text
    assert needs_map_hold(_MINT_21)
    assert needs_map_hold(_JAMMY)


def test_readme_promises_flatpak_only() -> None:
    text = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Hub-Systeme-Linux" in text
    assert "org.mraurevox.HubSysteme" in text
    assert "LANCER.sh" in text
    assert "local-first" in text.lower() or "100 % local" in text


def test_main_window_logs_when_mapped() -> None:
    text = (_ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert 'connect("map"' in text
    assert "fenêtre ouverte" in text
