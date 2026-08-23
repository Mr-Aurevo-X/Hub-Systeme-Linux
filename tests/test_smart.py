# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from core import smart


def test_status_summary_ok_bad_empty() -> None:
    assert smart.status_summary([]) == {"kind": "empty", "text": ""}
    ok = smart.status_summary([{"device": "/dev/sda", "health": "PASSED", "ok": True}])
    assert ok == {"kind": "ok", "text": ""}
    bad = smart.status_summary(
        [
            {"device": "/dev/sda", "health": "PASSED", "ok": True},
            {"device": "/dev/sdb", "health": "FAILED", "ok": False},
            {"device": "/dev/sdc", "health": "error", "ok": False},
        ]
    )
    assert bad["kind"] == "bad"
    assert "/dev/sdb: FAILED" in bad["text"]
    assert "/dev/sdc: error" in bad["text"]


def test_format_dialog_rows_caps_and_prefers_error() -> None:
    items = [
        {"device": "/dev/sda", "health": "passed", "ok": True},
        {"device": "/dev/sdb", "health": "error", "ok": False, "error": "denied"},
    ]
    items.extend(
        {"device": f"/dev/sd{idx}", "health": "passed", "ok": True} for idx in range(10)
    )
    rows = smart.format_dialog_rows(items)
    assert len(rows) == 6
    assert rows[0] == {"device": "/dev/sda", "detail": "passed"}
    assert rows[1] == {"device": "/dev/sdb", "detail": "denied"}
