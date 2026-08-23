# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from core import timers


def test_parse_list_timers_output() -> None:
    sample = (
        "NEXT                        LEFT          LAST                        PASSED UNIT                         ACTIVATES\n"
        "Mon 2026-08-23 12:00:00 CEST  1h 2min left Mon 2026-08-23 10:00:00 CEST  58min ago apt-daily.timer              apt-daily.service\n"
    )
    rows = timers.parse_list_timers_output(sample)
    assert len(rows) == 1
    assert rows[0]["unit"] == "apt-daily.timer"
    assert "2026" in rows[0]["next"]


def test_validate_unit_name() -> None:
    assert timers.validate_unit_name("apt-daily") == "apt-daily.timer"
    assert timers.validate_unit_name("apt-daily.timer") == "apt-daily.timer"
