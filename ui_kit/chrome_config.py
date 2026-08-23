# SPDX-License-Identifier: GPL-3.0-or-later
"""Chrome Uni-UI — Hub Système."""

from __future__ import annotations

from pathlib import Path

from ui_kit.donation_urls import DONATE_DISCORD, DONATE_PAYPAL, DONATE_REVOLUT

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_version() -> str:
    path = _REPO_ROOT / "VERSION"
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "1.0.0"


APP_NAME = "Hub Système"
APP_VERSION = _read_version()
CONFIG_APP_ID = "hub-systeme"
UI_LANGUAGE = "fr"

DONATE_URLS = {
    "discord": DONATE_DISCORD,
    "revolut": DONATE_REVOLUT,
    "paypal": DONATE_PAYPAL,
}

DONATE_MESSAGE = {
    "fr": (
        "Les apps publiques Mr-Aurevo-X sont et resteront gratuites.\n\n"
        "Un petit coup de pouce (Discord, Revolut ou PayPal) aide le temps de dev — "
        "100 % optionnel. L'application ne suit pas les dons."
    ),
    "en": (
        "Mr-Aurevo-X public apps are and will stay free.\n\n"
        "An optional tip (Discord, Revolut, or PayPal) helps development time — "
        "never required. The app does not track donations."
    ),
}

_KIT_ROOT = Path(__file__).resolve().parent
_LEGAL_DIR = _KIT_ROOT / "legal"


def _read_legal_file(name: str, fallback: str) -> str:
    path = _LEGAL_DIR / name
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return fallback


LEGAL_RGPD = _read_legal_file(
    "rgpd.md",
    "Données 100 % locales — ~/.config/Mr-Aurevo-X/hubs/systeme/",
)
LEGAL_CGU = _read_legal_file(
    "cgu.md",
    "Usage local. Pas de mise à jour automatique.",
)
LEGAL_LICENSES = _read_legal_file(
    "licenses.md",
    "Hub Système — GNU GPL-3.0-or-later © 2026 Mr-Aurevo-X.",
)


def app_line() -> str:
    return f"{APP_NAME} {APP_VERSION}".strip()
