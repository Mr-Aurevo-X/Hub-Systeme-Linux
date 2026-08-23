# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from core import process


def test_sort_processes_cpu_ram_name() -> None:
    rows = [
        {"pid": 1, "name": "zeta", "cpu": 1.0, "ram_mib": 80.0},
        {"pid": 2, "name": "alpha", "cpu": 9.0, "ram_mib": 10.0},
        {"pid": 3, "name": "mu", "cpu": 9.0, "ram_mib": 40.0},
    ]
    by_cpu = process.sort_processes(rows, "cpu")
    assert [item["pid"] for item in by_cpu] == [3, 2, 1]
    by_ram = process.sort_processes(rows, "ram")
    assert [item["pid"] for item in by_ram] == [1, 3, 2]
    by_name = process.sort_processes(rows, "name")
    assert [item["name"] for item in by_name] == ["alpha", "mu", "zeta"]
    assert process.sort_processes(rows, "nope") == process.sort_processes(rows, "cpu")
