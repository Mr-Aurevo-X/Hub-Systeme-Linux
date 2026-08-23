# SPDX-License-Identifier: GPL-3.0-or-later
"""Load presets, user overrides, and apply GTK CSS (void-glow default)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parent

_COLOR_KEYS = (
    "bg",
    "surface",
    "surface2",
    "text",
    "muted",
    "accent",
    "accent2",
    "ok",
    "warn",
    "danger",
    "border",
    "borderStrong",
    "accentDim",
    "onAccent",
)


def tokens_dir() -> Path:
    return _PKG_ROOT / "tokens"


def presets_dir() -> Path:
    return tokens_dir() / "presets"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def default_preset_id() -> str:
    manifest = _read_json(presets_dir() / "manifest.json")
    return str(manifest.get("default") or "void-glow")


def list_presets() -> list[tuple[str, str]]:
    manifest = _read_json(presets_dir() / "manifest.json")
    out: list[tuple[str, str]] = []
    for item in manifest.get("presets") or []:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()
        label = str(item.get("label") or pid)
        if pid:
            out.append((pid, label))
    return out


def load_preset(preset_id: str) -> dict[str, Any]:
    path = presets_dir() / f"{preset_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"preset introuvable : {preset_id}")
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"preset invalide : {preset_id}")
    return data


def user_theme_path(config_app_id: str) -> Path:
    return Path.home() / ".config" / config_app_id / "theme.json"


def load_user_theme(path: Path | None = None, *, config_app_id: str = "my-app") -> dict[str, Any]:
    target = path or user_theme_path(config_app_id)
    if not target.is_file():
        return {}
    try:
        raw = _read_json(target)
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def merge_colors(preset: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    colors: dict[str, str] = dict(preset.get("colors") or {})
    overrides = user.get("overrides") if isinstance(user.get("overrides"), dict) else {}
    for key, value in overrides.items():
        if key in _COLOR_KEYS and value:
            colors[key] = str(value)
    effects: dict[str, Any] = dict(preset.get("effects") or {})
    return {
        "id": preset.get("id"),
        "label": preset.get("label"),
        "colors": colors,
        "effects": effects,
    }


def load_merged_colors(
    *,
    config_app_id: str = "my-app",
    preset_id: str | None = None,
) -> dict[str, Any]:
    user = load_user_theme(config_app_id=config_app_id)
    pid = preset_id or str(user.get("preset") or "") or default_preset_id()
    preset = load_preset(pid)
    return merge_colors(preset, user)


def _css_for_merged(merged: dict[str, Any]) -> str:
    c = merged.get("colors") or {}
    eff = merged.get("effects") or {}
    radius = str(eff.get("radius") or "14px")
    glow_a = str(eff.get("glowAccent") or "none")
    shadow = str(eff.get("shadowCard") or "0 8px 24px rgba(0,0,0,0.4)")

    bg = c.get("bg", "#030304")
    surface = c.get("surface", "#0a0a0c")
    surface2 = c.get("surface2", "#101012")
    text = c.get("text", "#ffffff")
    muted = c.get("muted", "#b4bcc8")
    accent = c.get("accent", "#e03545")
    accent2 = c.get("accent2", "#6a9bb8")
    ok = c.get("ok", "#42e8a0")
    warn = c.get("warn", "#f5a623")
    danger = c.get("danger", "#ff5565")
    border = c.get("border", "rgba(255,255,255,0.08)")
    accent_dim = c.get("accentDim", "rgba(224,53,69,0.15)")

    return f"""
/* Uni-UI preset: {merged.get("id")} */
window, .uni-window {{
  background-color: {bg};
  color: {text};
}}
.uni-titlebar, headerbar {{
  background-color: {surface2};
  color: {text};
  border-bottom: 1px solid {border};
  box-shadow: {glow_a};
}}
.uni-sidebar {{
  background-color: {surface};
  border-right: 1px solid {border};
}}
.uni-card, .boxed-list {{
  background-color: {surface};
  border-radius: {radius};
  border: 1px solid {border};
  box-shadow: {shadow};
}}
.uni-status-default, .uni-status-default label {{ color: {text}; }}
.uni-status-ok, .uni-status-ok label {{ color: {ok}; }}
.uni-status-warn, .uni-status-warn label {{ color: {warn}; }}
.uni-status-error, .uni-status-error label {{ color: {danger}; }}
.uni-muted, .uni-muted label {{ color: {muted}; }}
.uni-accent {{ color: {accent}; }}
.uni-accent2 {{ color: {accent2}; }}
.uni-chrome-update {{
  border: 1px solid color-mix(in srgb, {accent} 50%, transparent);
  border-radius: 8px;
  padding: 4px;
}}
.uni-chrome-update:hover {{
  box-shadow:
    0 0 6px color-mix(in srgb, {accent} 45%, transparent),
    0 0 14px color-mix(in srgb, {accent} 25%, transparent);
}}
.uni-chrome-lang-slider {{
  padding: 2px 4px;
}}
.uni-chrome-lang-slider scale {{
  margin: 0 2px;
}}
.uni-chrome-lang-slider scale slider {{
  border-radius: 50%;
  background-color: {accent};
  box-shadow: 0 0 6px color-mix(in srgb, {accent} 55%, transparent);
}}
.uni-chrome-lang-slider scale highlight {{
  background-color: color-mix(in srgb, {accent} 35%, transparent);
  border-radius: 4px;
}}
.uni-lang-label {{
  font-size: 0.8em;
  font-weight: 600;
}}
.uni-lang-label.uni-lang-active {{
  color: {text};
}}
.uni-update-footer {{
  border-top: 1px solid {border};
  background-color: {surface2};
  padding: 8px 16px;
}}
.uni-update-footer .uni-muted {{
  color: {muted};
  font-size: 0.85em;
}}
button.suggested-action {{
  background-color: {accent};
  color: {c.get("onAccent", "#ffffff")};
  box-shadow: {glow_a};
}}
.navigation-sidebar row.active {{
  background-color: {accent_dim};
}}
scrollbar {{
  background-color: color-mix(in srgb, {bg} 75%, {surface2});
}}
scrollbar slider {{
  background-color: color-mix(in srgb, {accent2} 55%, {surface});
  border-radius: 8px;
  min-width: 8px;
  min-height: 8px;
}}
scrollbar slider:hover {{
  background-color: color-mix(in srgb, {accent2} 75%, {surface2});
}}
"""


def build_css(merged: dict[str, Any]) -> str:
    return _css_for_merged(merged)


def apply_theme(
    *,
    config_app_id: str = "my-app",
    preset_id: str | None = None,
) -> dict[str, Any]:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, Gtk

    merged = load_merged_colors(config_app_id=config_app_id, preset_id=preset_id)
    css = build_css(merged)
    provider = Gtk.CssProvider()
    raw = css.encode("utf-8")
    loaded = False
    for loader in (
        lambda: provider.load_from_data(raw),
        lambda: provider.load_from_string(css),
        lambda: provider.load_from_data(raw, len(raw)),
    ):
        try:
            loader()
            loaded = True
            break
        except (TypeError, AttributeError, ValueError):
            continue
    if not loaded:
        raise RuntimeError("Impossible de charger le CSS Uni-UI")

    display = Gdk.Display.get_default()
    if display is None:
        return merged
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    return merged


def save_user_theme(
    path: Path,
    *,
    preset_id: str,
    overrides: dict[str, str],
) -> None:
    data = {
        "preset": preset_id,
        "overrides": {k: v for k, v in overrides.items() if k in _COLOR_KEYS and v},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
