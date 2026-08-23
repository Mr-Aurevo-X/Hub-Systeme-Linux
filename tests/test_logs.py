# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from core import logs


def test_follow_argv_user_and_priority() -> None:
    argv = logs.follow_argv(priority="err", grep="", privileged=False)
    assert argv[:4] == ["journalctl", "-n", "0", "-f"]
    assert "-p" in argv
    assert logs.PRIORITY_MAP["err"] in argv
    assert "pkexec" not in argv
    assert "--grep" not in argv


def test_follow_argv_privileged_and_grep() -> None:
    argv = logs.follow_argv(priority="warning", grep="kernel", privileged=True)
    assert argv[0] == "pkexec"
    assert "--system" in argv
    assert "--grep" in argv
    assert "kernel" in argv


def test_follow_argv_rejects_bad_grep() -> None:
    with pytest.raises(logs.LogsError):
        logs.follow_argv(priority="all", grep="bad\nline", privileged=False)
    with pytest.raises(logs.LogsError):
        logs.follow_argv(priority="all", grep="-evil", privileged=False)