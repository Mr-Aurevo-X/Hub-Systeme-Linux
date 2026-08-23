# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from core import packages


def test_parse_pacman_orphans() -> None:
    text = "foo\nbar\n../evil\nbaz\n"
    assert packages.parse_pacman_orphans(text) == ["foo", "bar", "baz"]


def test_parse_apt_autoremove_block_and_remv() -> None:
    text = (
        "The following packages will be REMOVED:\n"
        "  oldpkg leftover\n"
        "0 upgraded, 0 newly installed, 2 to remove and 0 not upgraded.\n"
        "Remv leftover2 [1.0]\n"
    )
    names = packages.parse_apt_autoremove(text)
    assert "oldpkg" in names
    assert "leftover" in names
    assert "leftover2" in names


def test_parse_dnf_unneeded() -> None:
    text = "orphan.x86_64\nkeep-me.noarch\n"
    assert packages.parse_dnf_unneeded(text) == ["orphan.x86_64", "keep-me.noarch"]
