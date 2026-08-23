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
