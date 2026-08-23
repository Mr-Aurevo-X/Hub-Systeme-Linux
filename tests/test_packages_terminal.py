# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from core import packages, updater


def _assert_pkg_lock(text: str) -> None:
    assert "flock -n" in text
    assert "pkg-terminal.lock" in text
    assert "pkg-terminal.done" in text
    assert """trap 'touch "$DONE"' EXIT""" in text


def test_package_check_script_is_live(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(updater, "updates_dir", lambda: tmp_path)
    path = packages.write_check_updates_script()
    text = path.read_text(encoding="utf-8")
    assert "set -u" in text
    assert "set -e" not in text
    assert "pkexec" in text
    assert "pacman -Sy" in text
    assert "pacman -Qu" in text
    assert "flatpak remote-ls --updates" in text
    assert "apt-get update" in text
    assert "*curl" not in text
    _assert_pkg_lock(text)
    assert path.stat().st_mode & 0o111


def test_package_apply_script_is_live(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(updater, "updates_dir", lambda: tmp_path)
    path = packages.write_apply_updates_script()
    text = path.read_text(encoding="utf-8")
    assert "set -u" in text
    assert "set -e" not in text
    assert "pkexec pacman -Syu --noconfirm" in text
    assert "flatpak update -y" in text
    assert "pkexec apt-get upgrade -y" in text
    assert "*curl" not in text
    _assert_pkg_lock(text)
    hold = "\n".join(" ".join(cmd) for cmd in updater._terminal_commands(path))
    assert "Appuyez sur Entrée pour fermer" in hold


def test_host_manager_labels_without_pkexec_skips_pacman(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        if name in {"pacman", "apt-get", "dnf", "snap", "flatpak"}:
            return f"/usr/bin/{name}"
        return None

    monkeypatch.setattr(packages.host, "which", fake_which)
    labels = packages.host_manager_labels()
    assert "pacman" not in labels
    assert "APT" not in labels
    assert "DNF" not in labels
    assert "Snap" not in labels
    assert labels == ["Flatpak"]


def test_host_manager_labels_with_pkexec_includes_pacman(monkeypatch) -> None:
    def fake_which(name: str) -> str | None:
        if name in {"pkexec", "pacman", "flatpak"}:
            return f"/usr/bin/{name}"
        return None

    monkeypatch.setattr(packages.host, "which", fake_which)
    assert packages.host_manager_labels() == ["pacman", "Flatpak"]
