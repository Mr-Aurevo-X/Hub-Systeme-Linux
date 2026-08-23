# SPDX-License-Identifier: GPL-3.0-or-later
"""Local socket table (ss on the host). No DNS, no outbound HTTP."""

from __future__ import annotations

import csv
import ipaddress
import io
import re
from typing import Any

from core import executil, host, settings as app_settings

_SS_ARGV = ["ss", "-H", "-tuanp"]
_KEEP_STATES = frozenset({"ESTAB", "ESTABLISHED", "LISTEN", "UNCONN"})
_LISTEN_STATES = frozenset({"LISTEN", "UNCONN"})
_USERS_RE = re.compile(r'users:\(\("([^"]+)",pid=(\d+)')
_UNSAFE_ALLOW = re.compile(r"[;|&`$()<>\\]")
_CSV_FIELDS = ("kind", "proto", "state", "comm", "pid", "local", "remote")


class ConnectionError(Exception):
    """Raised when connection listing or allowlist updates fail."""


def _norm_proto(raw: str) -> str:
    text = (raw or "").lower()
    if text.startswith("udp"):
        return "udp"
    return "tcp"


def endpoint_ip(endpoint: str) -> str:
    """IP from ``ip:port``, ``[ipv6]:port``, or a bare address."""
    text = (endpoint or "").strip()
    if not text or text == "*":
        return ""
    if text.startswith("["):
        end = text.find("]")
        if end > 1:
            return text[1:end]
        return text.strip("[]")
    if text.count(":") == 1:
        return text.rsplit(":", 1)[0]
    if text.count(":") > 1 and not text.startswith("["):
        # IPv6 without brackets (rare in ss)
        if text.rsplit(":", 1)[-1].isdigit() or text.endswith(":*"):
            return text.rsplit(":", 1)[0]
        return text
    return text.rsplit(":", 1)[0] if ":" in text else text


def classify(
    remote_ip: str,
    *,
    state: str,
    allowlist: list[str] | None = None,
) -> str:
    """Return ``listen``, ``known``, or ``unknown``. Never a vendor/malware label."""
    st = (state or "").upper()
    if st in _LISTEN_STATES:
        return "listen"
    ip_text = endpoint_ip(remote_ip) if ":" in (remote_ip or "") and not _looks_bare_ip(remote_ip) else (remote_ip or "").strip()
    if not ip_text:
        ip_text = (remote_ip or "").strip()
    if _is_known_ip(ip_text, allowlist or []):
        return "known"
    return "unknown"


def _looks_bare_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


def _is_known_ip(ip_text: str, allowlist: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip_text.split("%", 1)[0])
    except ValueError:
        return False
    if addr.is_loopback or addr.is_link_local or addr.is_private:
        return True
    if addr.version == 6 and getattr(addr, "is_private", False):
        return True
    for raw in allowlist:
        if _ip_in_allow_entry(addr, raw):
            return True
    return False


def _ip_in_allow_entry(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, raw: str) -> bool:
    text = (raw or "").strip()
    if not text:
        return False
    try:
        net = ipaddress.ip_network(text, strict=False)
        return addr in net
    except ValueError:
        try:
            return addr == ipaddress.ip_address(text)
        except ValueError:
            return False


def add_allowlist_entry(raw: str, current: list[str] | None = None) -> list[str]:
    text = (raw or "").strip()
    if not text or _UNSAFE_ALLOW.search(text) or any(ch.isspace() for ch in text):
        raise ConnectionError("Entrée allowlist invalide")
    try:
        ipaddress.ip_network(text, strict=False)
    except ValueError as exc:
        raise ConnectionError("Entrée allowlist invalide") from exc
    out: list[str] = []
    seen: set[str] = set()
    for item in list(current or []) + [text]:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def parse_ss(text: str) -> list[dict[str, Any]]:
    """Parse ``ss -H -tuanp`` stdout. No subprocess."""
    rows: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        raw = line.rstrip()
        if not raw.strip():
            continue
        parts = raw.split()
        if len(parts) < 6:
            continue
        proto = _norm_proto(parts[0])
        state = parts[1].upper()
        if state not in _KEEP_STATES:
            continue
        local = parts[4]
        remote = parts[5]
        comm: str | None = None
        pid: int | None = None
        rest = " ".join(parts[6:])
        match = _USERS_RE.search(rest) or _USERS_RE.search(raw)
        if match:
            comm = match.group(1)
            pid = int(match.group(2))
        rows.append(
            {
                "pid": pid,
                "comm": comm or "?",
                "proto": proto,
                "local": local,
                "remote": remote,
                "state": state,
                "raw": raw,
                "kind": classify(endpoint_ip(remote), state=state, allowlist=[]),
            }
        )
    return rows


def to_csv(items: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(_CSV_FIELDS), extrasaction="ignore")
    writer.writeheader()
    for item in items:
        kind = item.get("kind") or classify(
            endpoint_ip(str(item.get("remote") or "")),
            state=str(item.get("state") or ""),
        )
        writer.writerow(
            {
                "kind": kind,
                "proto": item.get("proto") or "",
                "state": item.get("state") or "",
                "comm": item.get("comm") or "",
                "pid": item.get("pid") if item.get("pid") is not None else "",
                "local": item.get("local") or "",
                "remote": item.get("remote") or "",
            }
        )
    return buf.getvalue()


def _needs_elevation(items: list[dict[str, Any]]) -> bool:
    for item in items:
        state = str(item.get("state") or "").upper()
        if state in _LISTEN_STATES:
            continue
        if item.get("pid") is None:
            return True
    return False


def list_connections(
    *,
    privileged: bool = False,
    allowlist: list[str] | None = None,
) -> dict[str, Any]:
    """Read the host socket table. Never opens a network connection."""
    if allowlist is None:
        allowlist = list(app_settings.load_settings().get("connection_allowlist") or [])
    empty = {
        "available": False,
        "needs_elevation": False,
        "message": "ss introuvable sur l’hôte (paquet iproute2).",
        "items": [],
    }
    if host.which("ss") is None:
        return empty
    try:
        if privileged:
            completed = executil.run_pkexec(_SS_ARGV, timeout=20.0)
        else:
            completed = host.run(
                _SS_ARGV,
                check=False,
                capture_output=True,
                text=True,
                timeout=20.0,
            )
    except (OSError, executil.ExecError) as exc:
        return {
            "available": False,
            "needs_elevation": False,
            "message": str(exc),
            "items": [],
        }
    if int(getattr(completed, "returncode", 1) or 0) != 0:
        err = (getattr(completed, "stderr", None) or getattr(completed, "stdout", None) or "").strip()
        return {
            "available": False,
            "needs_elevation": False,
            "message": err or "ss a échoué",
            "items": [],
        }
    items = parse_ss(getattr(completed, "stdout", None) or "")
    for item in items:
        item["kind"] = classify(
            endpoint_ip(str(item.get("remote") or "")),
            state=str(item.get("state") or ""),
            allowlist=allowlist,
        )
    return {
        "available": True,
        "needs_elevation": (not privileged) and _needs_elevation(items),
        "message": "",
        "items": items,
    }
