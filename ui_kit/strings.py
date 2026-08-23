# SPDX-License-Identifier: GPL-3.0-or-later
"""Chrome tooltips and labels (FR / EN)."""

from __future__ import annotations

_STRINGS: dict[str, dict[str, str]] = {
    "check_updates": {"fr": "Vérifier les mises à jour", "en": "Check for updates"},
    "don_title": {"fr": "Soutien (optionnel)", "en": "Support (optional)"},
    "legal": {"fr": "Mentions légales", "en": "Legal"},
    "preferences": {"fr": "Paramètres", "en": "Preferences"},
    "lang_toggle": {"fr": "Changer la langue", "en": "Switch language"},
    "tab_rgpd": {"fr": "RGPD", "en": "Privacy (GDPR)"},
    "tab_cgu": {"fr": "CGU", "en": "Terms"},
    "tab_licenses": {"fr": "Licences", "en": "Licenses"},
    "tab_donate": {"fr": "Soutien (optionnel)", "en": "Support (optional)"},
    "close": {"fr": "Fermer", "en": "Close"},
    "save": {"fr": "Enregistrer", "en": "Save"},
    "current_version": {"fr": "Version installée", "en": "Installed version"},
    "theme_preset": {"fr": "Preset thème", "en": "Theme preset"},
    "theme_reset": {"fr": "Réinitialiser couleurs", "en": "Reset colors"},
    "theme_pick": {"fr": "Couleur", "en": "Pick"},
    "appearance": {"fr": "Apparence", "en": "Appearance"},
    "appearance_sub": {
        "fr": "Preset Uni-UI et couleurs locales.",
        "en": "Uni-UI preset and local color overrides.",
    },
    "updates": {"fr": "Mises à jour", "en": "Updates"},
    "update_title": {"fr": "Nouvelle version", "en": "New version"},
    "update_copy": {"fr": "Copier", "en": "Copy"},
    "update_commands_label": {
        "fr": "Commandes (copier-coller dans un terminal)",
        "en": "Commands (copy-paste into a terminal)",
    },
    "update_manual_hint": {
        "fr": "Pas d’installation automatique — copier les commandes dans un terminal.",
        "en": "No automatic install — copy commands into a terminal.",
    },
    "don_discord": {"fr": "Discord", "en": "Discord"},
    "don_revolut": {"fr": "Revolut", "en": "Revolut"},
    "don_paypal": {"fr": "PayPal", "en": "PayPal"},
}


def normalize_language(code: str | None) -> str:
    raw = (code or "fr").split("-", 1)[0].lower()
    return raw if raw in {"fr", "en"} else "fr"


def t(key: str, lang: str | None = None) -> str:
    code = normalize_language(lang)
    bucket = _STRINGS.get(key, {})
    return bucket.get(code) or bucket.get("fr") or key

