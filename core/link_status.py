# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only default-route pointer (hostname + IPv4). No Hub-Réseau, no pkexec."""

from __future__ import annotations

import socket
import subprocess
from shutil import which

_UNAVAILABLE = "réseau: n/a"


def parse_default_ipv4(route_text: str) -> str | None:
    """Return ``src`` IPv4 from an ``ip -4 route`` default line, if present."""
    for line in (route_text or "").splitlines():
        parts = line.split()
        if not parts or parts[0] != "default" or "src" not in parts:
            continue
        idx = parts.index("src")
        if idx + 1 >= len(parts):
            continue
        addr = parts[idx + 1].strip()
        if addr:
            return addr
    return None


def format_summary(hostname: str | None, ipv4: str | None) -> str:
    host = (hostname or "").strip()
    addr = (ipv4 or "").strip()
    if host and addr:
        return f"{host} {addr}"
    return _UNAVAILABLE


def _hostname() -> str | None:
    try:
        name = socket.gethostname().strip()
    except OSError:
        return None
    return name or None


def _ipv4_via_socket() -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("1.1.1.1", 80))
            addr = str(sock.getsockname()[0] or "").strip()
        finally:
            sock.close()
    except OSError:
        return None
    if not addr or addr.startswith("127."):
        return None
    return addr


def _ipv4_via_ip_route() -> str | None:
    ip_bin = which("ip")
    if not ip_bin:
        return None
    try:
        completed = subprocess.run(
            [ip_bin, "-4", "route"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return parse_default_ipv4(completed.stdout or "")


def summary_line() -> str:
    """Hostname plus default IPv4, or ``réseau: n/a`` when that is not easy."""
    return format_summary(_hostname(), _ipv4_via_socket() or _ipv4_via_ip_route())
