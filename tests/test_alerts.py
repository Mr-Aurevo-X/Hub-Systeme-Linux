# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from core import alerts


def test_format_history_entries() -> None:
    raw = [
        {"ts": 1_700_000_000.0, "messages": ["CPU élevé : 99%", "RAM élevée : 91%"]},
        {"ts": "bad", "messages": "nope"},
        {"messages": ["seul"]},
    ]
    rows = alerts.format_history_entries(raw)
    assert len(rows) == 2
    assert "CPU" in rows[0]["body"]
    assert "RAM" in rows[0]["body"]
    assert rows[0]["when"]
    assert rows[1]["body"] == "seul"
