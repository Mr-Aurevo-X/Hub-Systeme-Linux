# SPDX-License-Identifier: GPL-3.0-or-later

from ui_kit.dialogs.legal import present as present_legal
from ui_kit.dialogs.donate import present as present_donate
from ui_kit.dialogs.settings import present as present_settings
from ui_kit.dialogs.update import present as present_update

__all__ = ["present_legal", "present_donate", "present_settings", "present_update"]
