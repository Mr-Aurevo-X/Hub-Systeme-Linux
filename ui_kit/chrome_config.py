# SPDX-License-Identifier: GPL-3.0-or-later
"""
App chrome configuration — REMPLIR après copie du kit dans une app.

- APP_NAME, APP_VERSION, CONFIG_APP_ID
- legal : chemins ui_kit/legal/*.md ou texte inline ci-dessous
"""

from __future__ import annotations

from pathlib import Path

from ui_kit.donation_urls import DONATE_DISCORD, DONATE_PAYPAL, DONATE_REVOLUT

# --- À remplir ---
APP_NAME = "MyApp"
APP_VERSION = "0.0.0"
CONFIG_APP_ID = "my-app"

# Langue par défaut des strings kit (fr | en)
UI_LANGUAGE = "fr"

# Don (prérempli profil GitHub — override si besoin)
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
    "À compléter : vie privée / RGPD pour cette application.",
)
LEGAL_CGU = _read_legal_file(
    "cgu.md",
    "À compléter : conditions d'utilisation (CGU).",
)
LEGAL_LICENSES = _read_legal_file(
    "licenses.md",
    "À compléter : licences du logiciel (ex. GPL-3.0-or-later).",
)


def app_line() -> str:
    return f"{APP_NAME} {APP_VERSION}".strip()
