# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from core import link_status


_ROUTE = """\
default via 192.168.1.1 dev wlan0 proto dhcp src 192.168.1.42 metric 600
192.168.1.0/24 dev wlan0 proto kernel scope link src 192.168.1.42 metric 600
"""


def test_parse_default_ipv4_from_ip_route() -> None:
    assert link_status.parse_default_ipv4(_ROUTE) == "192.168.1.42"


def test_parse_default_ipv4_missing() -> None:
    assert link_status.parse_default_ipv4("192.168.1.0/24 dev lo\n") is None


def test_summary_line_hostname_and_ipv4() -> None:
    assert link_status.format_summary("box", "10.0.0.5") == "box 10.0.0.5"


def test_summary_line_unavailable() -> None:
    assert link_status.format_summary(None, None) == "réseau: n/a"
    assert link_status.format_summary("box", None) == "réseau: n/a"


def test_summary_line_composes_hostname_and_ipv4(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(link_status, "_hostname", lambda: "box")
    monkeypatch.setattr(link_status, "_ipv4_via_socket", lambda: "10.0.0.5")
    monkeypatch.setattr(link_status, "_ipv4_via_ip_route", lambda: None)
    assert link_status.summary_line() == "box 10.0.0.5"


def test_summary_line_returns_text() -> None:
    line = link_status.summary_line()
    assert isinstance(line, str)
    assert line
