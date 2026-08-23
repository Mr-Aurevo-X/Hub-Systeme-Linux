# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from core import fleet


def test_load_missing_fleet_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    store = fleet.load_fleet()
    assert store["version"] == 2
    assert store["machines"] == []


def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    machine = fleet.new_machine(
        name="Hub-Cachy",
        os_name="CachyOS",
        address="127.0.0.1",
        probe="tcp:22",
        note="local",
    )
    store = fleet.empty_store()
    store = fleet.upsert_machine(store, machine)
    fleet.save_fleet(store)
    again = fleet.load_fleet()
    assert len(again["machines"]) == 1
    row = again["machines"][0]
    assert row["name"] == "Hub-Cachy"
    assert row["address"] == "127.0.0.1"
    assert row["probe"] == "tcp:22"
    assert row["id"]


def test_rejects_shell_metacharacters_in_address() -> None:
    with pytest.raises(fleet.FleetError):
        fleet.validate_address("127.0.0.1; rm -rf /")
    with pytest.raises(fleet.FleetError):
        fleet.validate_address("host$(reboot)")
    with pytest.raises(fleet.FleetError):
        fleet.validate_address("")


def test_accepts_ip_and_lan_hostname() -> None:
    assert fleet.validate_address("192.168.1.10") == "192.168.1.10"
    assert fleet.validate_address("hub-mint.lan") == "hub-mint.lan"
    assert fleet.validate_address("::1") == "::1"
    machine = fleet.new_machine(name="Hub Mint", os_name="Linux Mint", address="192.0.2.10")
    assert machine["os"] == "Linux Mint"
    assert machine["name"] == "Hub Mint"


def test_rejects_unknown_probe_and_caps_fleet() -> None:
    with pytest.raises(fleet.FleetError):
        fleet.validate_probe("udp:53")
    store = fleet.empty_store()
    for idx in range(fleet.MAX_MACHINES):
        store = fleet.upsert_machine(
            store,
            fleet.new_machine(name=f"m{idx}", os_name="Linux", address=f"10.0.0.{idx + 1}"),
        )
    with pytest.raises(fleet.FleetError):
        fleet.upsert_machine(
            store,
            fleet.new_machine(name="extra", os_name="Linux", address="10.0.0.99"),
        )


def test_delete_machine_requires_id() -> None:
    store = fleet.empty_store()
    machine = fleet.new_machine(name="A", os_name="Mint", address="10.0.0.2")
    store = fleet.upsert_machine(store, machine)
    store = fleet.delete_machine(store, machine["id"])
    assert store["machines"] == []
    with pytest.raises(fleet.FleetError):
        fleet.delete_machine(store, "missing")


def test_probe_tcp_online_and_offline_mocked() -> None:
    def ok(addr: tuple[str, int], timeout: float = 1.0):  # noqa: ARG001
        class Sock:
            def close(self) -> None:
                return None

        return Sock()

    result = fleet.probe_tcp("127.0.0.1", 22, timeout=0.2, connector=ok)
    assert result["online"] is True
    assert result["method"] == "tcp:22"
    assert result["error"] == ""

    def fail(addr: tuple[str, int], timeout: float = 1.0):  # noqa: ARG001
        raise TimeoutError("timed out")

    down = fleet.probe_tcp("10.0.0.9", 22, timeout=0.2, connector=fail)
    assert down["online"] is False
    assert down["error"]


def test_tcp_connection_refused_counts_as_online() -> None:
    """RST / ECONNREFUSED means the host answered; only timeout is offline."""

    def refuse(addr: tuple[str, int], timeout: float = 1.0):  # noqa: ARG001
        raise ConnectionRefusedError(111, "Connection refused")

    result = fleet.probe_tcp("127.0.0.1", 22, timeout=0.2, connector=refuse)
    assert result["online"] is True
    assert result["method"] == "tcp:22"


def test_icmp_denied_falls_back_to_tcp() -> None:
    def ping_denied(_cmd: list[str], **_kwargs: object) -> object:
        class Done:
            returncode = 2
            stdout = ""
            stderr = "ping: socket: Operation not permitted"

        return Done()

    def tcp_ok(address: str, port: int, *, timeout: float = 1.0, connector=None):  # noqa: ARG001
        return {
            "online": True,
            "method": f"tcp:{port}",
            "error": "",
            "at": "now",
        }

    machine = fleet.new_machine(name="Hub", os_name="CachyOS", address="127.0.0.1", probe="icmp")
    result = fleet.probe_machine(machine, ping_runner=ping_denied, tcp_fn=tcp_ok)
    assert result["online"] is True
    assert result["method"].startswith("tcp:")
    assert "icmp" in result["error"] or "permis" in result["error"].lower() or result["fallback"]


def test_to_csv_has_header() -> None:
    machine = fleet.new_machine(name="Hub-Win", os_name="Windows", address="10.0.0.5", probe="tcp:3389")
    machine["last_online"] = False
    machine["last_probe_at"] = "2026-08-18 11:00:00"
    text = fleet.to_csv([machine])
    header = text.splitlines()[0]
    assert header.startswith("name,os,address,online,last_probe,note")
    assert "Hub-Win" in text
    assert "10.0.0.5" in text
