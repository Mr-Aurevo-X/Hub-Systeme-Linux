# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from core.snapper import parse_list_output


SAMPLE = """\
Type   | # | Pre # | Date                     | User | Cleanup | Description           | Userdata
-------+---+-------+--------------------------+------+---------+-----------------------+---------
single | 0 |       |                          | root |         | current               |
single | 1 |       | Mon Aug 11 12:00:00 2025 | root | number  | timeline              |
pre    | 2 |       | Mon Aug 11 13:00:00 2025 | root | number  | pacman                |
post   | 3 | 2     | Mon Aug 11 13:00:05 2025 | root | number  | pacman                |
"""


def test_parse_snapper_list() -> None:
    items = parse_list_output(SAMPLE)
    ids = [i["id"] for i in items]
    assert "0" in ids
    assert "1" in ids
    assert "3" in ids
    one = next(i for i in items if i["id"] == "1")
    assert one["backend"] == "snapper"
    assert "timeline" in one["description"] or "Aug" in one["date"]


def test_parse_ignores_junk() -> None:
    assert parse_list_output("not a table\n") == []
