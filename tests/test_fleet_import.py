# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from core import fleet


def test_import_export_roundtrip() -> None:
    store = fleet.empty_store()
    row = fleet.new_machine(name="Hub", os_name="Linux", address="192.168.1.10", location="Atelier")
    store = fleet.upsert_machine(store, row)
    text = fleet.export_store_json(store)
    imported = fleet.import_store_from_json(text)
    assert len(imported["machines"]) == 1
    assert imported["machines"][0]["location"] == "Atelier"


def test_merge_import_keeps_existing() -> None:
    a = fleet.new_machine(name="A", os_name="L", address="10.0.0.1", machine_id="id-a")
    b = fleet.new_machine(name="B", os_name="L", address="10.0.0.2", machine_id="id-b")
    store = fleet.upsert_machine(fleet.empty_store(), a)
    incoming = fleet.import_store_from_json(fleet.export_store_json(fleet.upsert_machine(fleet.empty_store(), b)))
    merged = fleet.merge_import(store, incoming)
    names = {m["name"] for m in merged["machines"]}
    assert names == {"A", "B"}


def test_validate_tags_limit() -> None:
    with pytest.raises(fleet.FleetError):
        fleet.validate_tags([f"t{i}" for i in range(9)])
