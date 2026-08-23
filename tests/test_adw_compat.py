# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from ui.compat_attr import call_if_present, first_attr


def test_first_attr_prefers_modern_name() -> None:
    class FakeAdw:
        NavigationSplitView = object()
        Leaflet = object()

    found = first_attr(FakeAdw, "NavigationSplitView", "Leaflet")
    assert found is FakeAdw.NavigationSplitView


def test_first_attr_falls_back_when_modern_missing() -> None:
    class FakeAdw:
        Leaflet = "legacy"

    assert first_attr(FakeAdw, "NavigationSplitView", "Leaflet") == "legacy"
    assert first_attr(FakeAdw, "AlertDialog", "MessageDialog") is None


def test_call_if_present_true_and_false_branches() -> None:
    class HasSetter:
        def __init__(self) -> None:
            self.value = ""

        def set_placeholder_text(self, text: str) -> None:
            self.value = text

    class NoSetter:
        pass

    has = HasSetter()
    assert call_if_present(has, "set_placeholder_text", "hello") is True
    assert has.value == "hello"
    assert call_if_present(NoSetter(), "set_placeholder_text", "hello") is False
