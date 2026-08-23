# SPDX-License-Identifier: GPL-3.0-or-later
"""Manual workshop fleet (Parc). Local JSON + TCP/ICMP probe. No WOL."""

from __future__ import annotations

import csv
import errno
import io
import ipaddress
import json
import re
import socket
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core import host, settings as app_settings

MAX_MACHINES = 12
PROBES = ("tcp:22", "tcp:3389", "tcp:445", "icmp")
_UNSAFE = re.compile(r"[;&|`$<>(){}\\!#\s]")
_HOSTNAME = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)$"
)
TcpFn = Callable[..., dict[str, Any]]
PingRunner = Callable[..., Any]


class FleetError(Exception):
    """Invalid fleet data or operation."""


def empty_store() -> dict[str, Any]:
    return {"version": 2, "machines": []}


def fleet_path() -> Path:
    return app_settings.config_dir() / "fleet.json"


def validate_name(name: str) -> str:
    text = " ".join((name or "").split())
    if not text or len(text) > 80:
        raise FleetError("Nom invalide")
    if any(ch in text for ch in ";`$|<>(){}\\"):
        raise FleetError("Nom : caractères interdits")
    return text


def validate_os_name(os_name: str) -> str:
    text = " ".join((os_name or "").split())
    if not text:
        return "—"
    if len(text) > 40 or any(ch in text for ch in ";`$|<>(){}\\"):
        raise FleetError("OS déclaré invalide")
    return text


def validate_note(note: str) -> str:
    text = (note or "").strip()
    if len(text) > 200:
        raise FleetError("Note trop longue")
    if any(ch in text for ch in ";`$|<>"):
        raise FleetError("Note : caractères interdits")
    return text


def validate_address(address: str) -> str:
    text = (address or "").strip()
    if not text:
        raise FleetError("Adresse vide")
    if _UNSAFE.search(text):
        raise FleetError("Adresse : caractères interdits")
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        pass
    if _HOSTNAME.fullmatch(text):
        return text
    raise FleetError("Adresse : IP ou nom d’hôte LAN uniquement")


def validate_probe(probe: str) -> str:
    text = (probe or "").strip().lower()
    if text not in PROBES:
        raise FleetError("Sonde inconnue")
    return text


def validate_location(location: str) -> str:
    text = " ".join((location or "").split())
    if len(text) > 80:
        raise FleetError("Emplacement trop long")
    if any(ch in text for ch in ";`$|<>{}"):
        raise FleetError("Emplacement : caractères interdits")
    return text


def validate_tags(raw: str | list[str]) -> list[str]:
    if isinstance(raw, list):
        parts = [str(p).strip() for p in raw]
    else:
        parts = [p.strip() for p in str(raw or "").split(",")]
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        if len(part) > 32 or any(ch in part for ch in ";`$|<>{}\\"):
            raise FleetError("Tag invalide")
        if part in out:
            continue
        if len(out) >= 8:
            raise FleetError("Trop de tags (max 8)")
        out.append(part)
    return out


def new_machine(
    *,
    name: str,
    os_name: str,
    address: str,
    probe: str = "tcp:22",
    note: str = "",
    location: str = "",
    tags: list[str] | str | None = None,
    machine_id: str = "",
) -> dict[str, Any]:
    return {
        "id": machine_id or str(uuid.uuid4()),
        "name": validate_name(name),
        "os": validate_os_name(os_name),
        "address": validate_address(address),
        "probe": validate_probe(probe),
        "note": validate_note(note),
        "location": validate_location(location),
        "tags": validate_tags(tags or []),
        "last_online": None,
        "last_probe_at": "",
        "last_method": "",
        "last_error": "",
    }


def _normalize_machine(raw: dict[str, Any]) -> dict[str, Any]:
    return new_machine(
        name=str(raw.get("name") or ""),
        os_name=str(raw.get("os") or raw.get("os_name") or ""),
        address=str(raw.get("address") or ""),
        probe=str(raw.get("probe") or "tcp:22"),
        note=str(raw.get("note") or ""),
        location=str(raw.get("location") or ""),
        tags=list(raw.get("tags") or []),
        machine_id=str(raw.get("id") or ""),
    ) | {
        "last_online": raw.get("last_online"),
        "last_probe_at": str(raw.get("last_probe_at") or ""),
        "last_method": str(raw.get("last_method") or ""),
        "last_error": str(raw.get("last_error") or ""),
    }


def load_fleet(path: Path | None = None) -> dict[str, Any]:
    target = path or fleet_path()
    if not target.exists():
        return empty_store()
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return empty_store()
    if not isinstance(parsed, dict):
        return empty_store()
    machines: list[dict[str, Any]] = []
    for item in parsed.get("machines") or []:
        if not isinstance(item, dict):
            continue
        try:
            machines.append(_normalize_machine(item))
        except FleetError:
            continue
        if len(machines) >= MAX_MACHINES:
            break
    return {"version": 2, "machines": machines}


def save_fleet(store: dict[str, Any], path: Path | None = None) -> Path:
    target = path or fleet_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "machines": list(store.get("machines") or []),
    }
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def upsert_machine(store: dict[str, Any], machine: dict[str, Any]) -> dict[str, Any]:
    row = _normalize_machine(machine)
    machines = list(store.get("machines") or [])
    for idx, existing in enumerate(machines):
        if existing.get("id") == row["id"]:
            machines[idx] = {**existing, **row}
            return {"version": 2, "machines": machines}
    if len(machines) >= MAX_MACHINES:
        raise FleetError(f"Parc limité à {MAX_MACHINES} machines")
    machines.append(row)
    return {"version": 2, "machines": machines}


def delete_machine(store: dict[str, Any], machine_id: str) -> dict[str, Any]:
    machines = list(store.get("machines") or [])
    kept = [item for item in machines if item.get("id") != machine_id]
    if len(kept) == len(machines):
        raise FleetError("Machine introuvable")
    return {"version": 2, "machines": kept}


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def probe_tcp(
    address: str,
    port: int,
    *,
    timeout: float = 1.2,
    connector: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    connect = connector or socket.create_connection
    try:
        sock = connect((address, int(port)), timeout=float(timeout))
    except OSError as exc:
        reachable = getattr(exc, "errno", None) == errno.ECONNREFUSED
        return {
            "online": reachable,
            "method": f"tcp:{int(port)}",
            "error": "" if reachable else str(exc),
            "at": _stamp(),
            "fallback": False,
        }
    closer = getattr(sock, "close", None)
    if callable(closer):
        try:
            closer()
        except OSError:
            pass
    return {
        "online": True,
        "method": f"tcp:{int(port)}",
        "error": "",
        "at": _stamp(),
        "fallback": False,
    }


def _icmp_denied(text: str) -> bool:
    lower = (text or "").lower()
    return any(
        needle in lower
        for needle in (
            "not permitted",
            "permission denied",
            "operation not permitted",
            "opération non permise",
            "cap_net_raw",
            "not allowed",
        )
    )


def probe_icmp(
    address: str,
    *,
    timeout: float = 1.2,
    runner: PingRunner | None = None,
) -> dict[str, Any]:
    run = runner or host.run
    cmd = ["ping", "-c", "1", "-W", str(max(int(timeout), 1)), address]
    try:
        completed = run(cmd, check=False, capture_output=True, text=True, timeout=timeout + 1.5)
    except (OSError, TimeoutError) as exc:
        return {
            "online": False,
            "method": "icmp",
            "error": str(exc),
            "at": _stamp(),
            "fallback": False,
        }
    out = f"{getattr(completed, 'stdout', '')}\n{getattr(completed, 'stderr', '')}"
    code = int(getattr(completed, "returncode", 1) or 1)
    if code == 0:
        return {"online": True, "method": "icmp", "error": "", "at": _stamp(), "fallback": False}
    return {
        "online": False,
        "method": "icmp",
        "error": out.strip() or f"ping exit {code}",
        "at": _stamp(),
        "fallback": False,
    }


def probe_machine(
    machine: dict[str, Any],
    *,
    timeout: float = 1.2,
    ping_runner: PingRunner | None = None,
    tcp_fn: TcpFn | None = None,
) -> dict[str, Any]:
    address = validate_address(str(machine.get("address") or ""))
    probe = validate_probe(str(machine.get("probe") or "tcp:22"))
    tcp = tcp_fn or probe_tcp
    if probe.startswith("tcp:"):
        port = int(probe.split(":", 1)[1])
        return tcp(address, port, timeout=timeout)
    icmp = probe_icmp(address, timeout=timeout, runner=ping_runner)
    if icmp.get("online"):
        return icmp
    if _icmp_denied(str(icmp.get("error") or "")):
        fallback = tcp(address, 22, timeout=timeout)
        fallback["fallback"] = True
        denied = str(icmp.get("error") or "ping interdit")
        extra = str(fallback.get("error") or "")
        fallback["error"] = f"ICMP indisponible ({denied}); repli TCP 22" + (f" ({extra})" if extra else "")
        return fallback
    return icmp


def apply_probe(machine: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    updated = dict(machine)
    updated["last_online"] = bool(result.get("online"))
    updated["last_probe_at"] = str(result.get("at") or _stamp())
    updated["last_method"] = str(result.get("method") or "")
    updated["last_error"] = str(result.get("error") or "")
    history = list(updated.get("probe_history") or [])
    history.append(
        {
            "at": updated["last_probe_at"],
            "online": updated["last_online"],
            "method": updated["last_method"],
        }
    )
    updated["probe_history"] = history[-20:]
    return updated


def to_csv(machines: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "os", "address", "online", "last_probe", "note"])
    for item in machines:
        online = item.get("last_online")
        if online is True:
            status = "online"
        elif online is False:
            status = "offline"
        else:
            status = ""
        writer.writerow(
            [
                item.get("name") or "",
                item.get("os") or "",
                item.get("address") or "",
                status,
                item.get("last_probe_at") or "",
                item.get("note") or "",
            ]
        )
    return buf.getvalue()


def default_export_path() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Documents" / f"hub-systeme-parc-{stamp}.csv"


def export_store_json(store: dict[str, Any]) -> str:
    payload = {
        "version": 2,
        "machines": list(store.get("machines") or []),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def import_store_from_json(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FleetError("JSON invalide") from exc
    if not isinstance(parsed, dict):
        raise FleetError("Format parc invalide")
    machines: list[dict[str, Any]] = []
    for item in parsed.get("machines") or []:
        if not isinstance(item, dict):
            continue
        try:
            machines.append(_normalize_machine(item))
        except FleetError:
            continue
        if len(machines) >= MAX_MACHINES:
            break
    if not machines:
        raise FleetError("Aucune machine valide dans le fichier")
    return {"version": 2, "machines": machines}


def merge_import(store: dict[str, Any], imported: dict[str, Any]) -> dict[str, Any]:
    current = list(store.get("machines") or [])
    by_id = {str(m.get("id")): m for m in current if m.get("id")}
    for item in imported.get("machines") or []:
        mid = str(item.get("id") or "")
        if mid and mid in by_id:
            by_id[mid] = {**by_id[mid], **item}
        elif len(by_id) < MAX_MACHINES:
            by_id[str(item.get("id") or uuid.uuid4())] = item
    return {"version": 2, "machines": list(by_id.values())[:MAX_MACHINES]}
