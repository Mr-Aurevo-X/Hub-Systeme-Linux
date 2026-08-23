# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from core import jobs, updater


def test_script_argv_uses_util_linux_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "updates_dir", lambda: tmp_path)
    script = tmp_path / "run-pkg-check.sh"
    script.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    argv = jobs.script_argv(script, have_script_cmd=True)
    assert argv[0] == "script"
    assert "-qefc" in argv
    assert "bash" in argv[2]
    assert str(script.resolve()) in argv[2]
    assert argv[-1] == "/dev/null"


def test_script_argv_falls_back_to_bash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "updates_dir", lambda: tmp_path)
    script = tmp_path / "run-pkg-apply.sh"
    script.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    argv = jobs.script_argv(script, have_script_cmd=False)
    assert argv == ["bash", str(script.resolve())]


def test_validate_script_rejects_outside_updates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "updates_dir", lambda: tmp_path)
    outsider = tmp_path.parent / "evil.sh"
    outsider.write_text("echo no\n", encoding="utf-8")
    with pytest.raises(jobs.JobError, match="hors"):
        jobs.validate_script(outsider)
