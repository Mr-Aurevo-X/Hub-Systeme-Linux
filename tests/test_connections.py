# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core import connections

_ROOT = Path(__file__).resolve().parents[1]

_SS_FIXTURE = """\
tcp   ESTAB 0      0      192.168.1.10:443      8.8.8.8:443          users:(("firefox",pid=1234,fd=32))
tcp   LISTEN 0      128    0.0.0.0:22            0.0.0.0:*            users:(("sshd",pid=812,fd=3))
tcp   ESTAB 0      0      127.0.0.1:5432        127.0.0.1:43210      users:(("postgres",pid=99,fd=8))
tcp   ESTAB 0      0      10.1.1.8:443          10.0.0.1:51234       users:(("curl",pid=50,fd=4))
udp   UNCONN 0      0      0.0.0.0:68            0.0.0.0:*            users:(("dhclient",pid=70,fd=5))
tcp   TIME-WAIT 0  0      10.0.0.5:54321        1.2.3.4:443
tcp6  ESTAB 0      0      [::1]:8080            [::1]:12345          users:(("python3",pid=7,fd=4))
tcp   ESTAB 0      0      192.168.1.10:53111    9.9.9.9:853
"""


def test_parse_ss_fixture_keeps_estab_listen_drops_time_wait() -> None:
    rows = connections.parse_ss(_SS_FIXTURE)
    remotes = {item["remote"] for item in rows}
    assert "8.8.8.8:443" in remotes
    assert "0.0.0.0:22" in {item["local"] for item in rows}
    assert not any("TIME-WAIT" in (item.get("state") or "") for item in rows)
    firefox = next(item for item in rows if item.get("comm") == "firefox")
    assert firefox["pid"] == 1234
    assert firefox["proto"] == "tcp"
    assert firefox["state"] == "ESTAB"
    sshd = next(item for item in rows if item.get("comm") == "sshd")
    assert sshd["state"] == "LISTEN"
    loop6 = next(item for item in rows if item.get("comm") == "python3")
    assert loop6["remote"].startswith("[::1]")
    no_pid = next(item for item in rows if "9.9.9.9" in item["remote"])
    assert no_pid["pid"] is None
    assert "raw" in no_pid


def test_classify_loopback_and_lan_known() -> None:
    assert connections.classify("127.0.0.1", state="ESTAB") == "known"
    assert connections.classify("::1", state="ESTAB") == "known"
    assert connections.classify("10.0.0.1", state="ESTAB") == "known"
    assert connections.classify("192.168.1.20", state="ESTAB") == "known"
    assert connections.classify("fe80::1", state="ESTAB") == "known"
    assert connections.classify("fd12:3456::1", state="ESTAB") == "known"


def test_classify_public_unknown_unless_allowlisted() -> None:
    assert connections.classify("8.8.8.8", state="ESTAB") == "unknown"
    assert connections.classify("8.8.8.8", state="ESTAB", allowlist=["8.8.8.0/24"]) == "known"
    assert connections.classify("1.1.1.1", state="ESTAB", allowlist=["8.8.8.8"]) == "unknown"


def test_classify_listen_before_unknown() -> None:
    assert connections.classify("0.0.0.0", state="LISTEN") == "listen"
    assert connections.classify("8.8.8.8", state="LISTEN") == "listen"
    assert connections.classify("0.0.0.0", state="UNCONN") == "listen"


def test_add_allowlist_entry_validates() -> None:
    assert connections.add_allowlist_entry("8.8.8.8", []) == ["8.8.8.8"]
    assert connections.add_allowlist_entry("10.0.0.0/8", ["8.8.8.8"]) == ["8.8.8.8", "10.0.0.0/8"]
    with pytest.raises(connections.ConnectionError):
        connections.add_allowlist_entry("not an ip", [])
    with pytest.raises(connections.ConnectionError):
        connections.add_allowlist_entry("8.8.8.8; rm", [])


def test_to_csv_has_header_and_row() -> None:
    rows = connections.parse_ss(_SS_FIXTURE)
    text = connections.to_csv(rows)
    assert text.splitlines()[0].startswith("kind,proto,")
    assert "firefox" in text
    assert "8.8.8.8:443" in text


def test_list_connections_uses_ss_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connections.host, "which", lambda name: "/usr/bin/ss" if name == "ss" else None)

    class Fake:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = _SS_FIXTURE
            self.stderr = ""

    monkeypatch.setattr(connections.host, "run", lambda *_a, **_k: Fake())
    result = connections.list_connections(allowlist=[])
    assert result["available"] is True
    assert any(item["comm"] == "firefox" for item in result["items"])
    assert result["needs_elevation"] is True
    kinds = {item["kind"] for item in result["items"]}
    assert "unknown" in kinds
    assert "known" in kinds
    assert "listen" in kinds


def test_list_connections_ss_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connections.host, "which", lambda _name: None)
    result = connections.list_connections(allowlist=[])
    assert result["available"] is False
    assert result["items"] == []
    assert result["message"]


def test_module_has_no_outbound_network() -> None:
    tree = ast.parse((_ROOT / "core" / "connections.py").read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    assert "urllib" not in imports
    source = (_ROOT / "core" / "connections.py").read_text(encoding="utf-8")
    assert "create_connection" not in source
    assert "getnameinfo" not in source
    assert "urlopen" not in source
    assert "shell=True" not in source


def test_settings_default_allowlist() -> None:
    from core import settings as app_settings

    assert "connection_allowlist" in app_settings.DEFAULTS
    assert app_settings.DEFAULTS["connection_allowlist"] == []
