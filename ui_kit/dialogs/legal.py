# SPDX-License-Identifier: GPL-3.0-or-later
"""Legal dialog — RGPD · CGU · Licences · Soutien."""

from __future__ import annotations

from gi.repository import Gtk

from ui_kit import chrome_config
from ui_kit.dialogs import donate as donate_dialog
from ui_kit.dialogs._tabbed import present_tabbed
from ui_kit.strings import normalize_language, t


def present(parent: Gtk.Window, lang: str | None = None) -> Gtk.Window:
    code = normalize_language(lang or chrome_config.UI_LANGUAGE)
    return present_tabbed(
        parent,
        t("legal", code),
        [
            ("rgpd", t("tab_rgpd", code), chrome_config.LEGAL_RGPD),
            ("cgu", t("tab_cgu", code), chrome_config.LEGAL_CGU),
            ("licenses", t("tab_licenses", code), chrome_config.LEGAL_LICENSES),
            ("donate", t("tab_donate", code), donate_dialog.build_panel(code)),
        ],
    )
