# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from core import sessions


def test_validate_session_id_accepts_loginctl_ids() -> None:
    assert sessions.validate_session_id("3") == "3"
    assert sessions.validate_session_id("c2") == "c2"


def test_validate_session_id_rejects_injection() -> None:
    with pytest.raises(sessions.SessionError):
        sessions.validate_session_id("../1")
    with pytest.raises(sessions.SessionError):
        sessions.validate_session_id("1; reboot")
    with pytest.raises(sessions.SessionError):
        sessions.validate_session_id("")


def test_is_current_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_SESSION_ID", "c2")
    assert sessions.is_current_session("c2") is True
    assert sessions.is_current_session("9") is False
    monkeypatch.delenv("XDG_SESSION_ID", raising=False)
    assert sessions.is_current_session("c2") is False