# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from unittest.mock import patch

import pytest

from core import backup


def test_reminder_status_snapper_never_lists() -> None:
    with patch.object(backup, "status", return_value={"available": True, "backend": "snapper"}):
        with patch.object(backup, "list_snapshots") as list_mock:
            result = backup.reminder_status()
    list_mock.assert_not_called()
    assert result["needs_admin"] is True
    assert result["ok"] is None


def test_list_snapshots_respects_privileged_false() -> None:
    with patch("core.backup.detect_backend", return_value="snapper"):
        with patch("core.backup.snapper_mod.list_snapshots") as snap_mock:
            snap_mock.return_value = []
            backup.list_snapshots(privileged=False)
    snap_mock.assert_called_once()
    assert snap_mock.call_args.kwargs.get("privileged") is False


def test_sanitize_snapshot_comment_defaults_to_hub() -> None:
    assert backup.sanitize_snapshot_comment(None) == "Hub Système"
    assert backup.sanitize_snapshot_comment("") == "Hub Système"
    assert backup.sanitize_snapshot_comment("  ok  ") == "ok"
    assert "Gest" not in backup.sanitize_snapshot_comment(None)


def test_delete_timeshift_error_does_not_say_gest() -> None:
    with pytest.raises(backup.BackupError) as exc:
        backup.delete_snapshot("2026-01-01_00-00-00", backend="timeshift")
    msg = str(exc.value)
    assert "Gest" not in msg
    assert "Timeshift" in msg
