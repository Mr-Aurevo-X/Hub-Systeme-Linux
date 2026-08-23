# SPDX-License-Identifier: GPL-3.0-or-later
"""Wi-Fi (nmcli) and Bluetooth (bluetoothctl) helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any


class NetworkCtlError(Exception):
    """Raised when network control fails."""


def _run(cmd: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)


def wifi_status() -> dict[str, Any]:
    if shutil.which("nmcli") is None:
        return {"available": False, "enabled": False, "connections": [], "message": "nmcli introuvable"}
    try:
        radio = _run(["nmcli", "radio", "wifi"])
        enabled = (radio.stdout or "").strip().lower() == "enabled"
        lst = _run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list"])
        connections: list[dict[str, Any]] = []
        for line in (lst.stdout or "").splitlines():
            parts = line.split(":")
            if len(parts) < 3:
                continue
            connections.append(
                {
                    "active": parts[0] == "yes",
                    "ssid": parts[1],
                    "signal": parts[2],
                    "security": parts[3] if len(parts) > 3 else "",
                }
            )
        return {"available": True, "enabled": enabled, "connections": connections[:30], "message": ""}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": True, "enabled": False, "connections": [], "message": str(exc)}


def set_wifi_enabled(enabled: bool) -> None:
    if shutil.which("nmcli") is None:
        raise NetworkCtlError("nmcli introuvable")
    value = "on" if enabled else "off"
    completed = _run(["nmcli", "radio", "wifi", value])
    if completed.returncode != 0:
        raise NetworkCtlError((completed.stderr or completed.stdout or "échec wifi").strip())


_SSID_RE = re.compile(r"^[\w ._\-@#']{1,64}$", re.UNICODE)


def _validate_ssid(ssid: str) -> str:
    clean = ssid.strip()
    if not clean or not _SSID_RE.match(clean):
        raise NetworkCtlError("SSID invalide")
    return clean


def wifi_connect(ssid: str, password: str | None = None) -> None:
    """Connect to ``ssid`` (optionally with WPA password)."""
    if shutil.which("nmcli") is None:
        raise NetworkCtlError("nmcli introuvable")
    name = _validate_ssid(ssid)
    if password:
        if len(password) > 128 or "\n" in password or "\x00" in password:
            raise NetworkCtlError("Mot de passe Wi-Fi invalide")
        cmd = [
            "nmcli",
            "dev",
            "wifi",
            "connect",
            name,
            "password",
            password,
        ]
    else:
        cmd = ["nmcli", "dev", "wifi", "connect", name]
    completed = _run(cmd, timeout=90.0)
    if completed.returncode != 0:
        raise NetworkCtlError((completed.stderr or completed.stdout or "échec connexion").strip())


def wifi_forget(ssid: str) -> None:
    """Delete saved connection matching SSID (best-effort via nmcli)."""
    if shutil.which("nmcli") is None:
        raise NetworkCtlError("nmcli introuvable")
    name = _validate_ssid(ssid)
    # List connections and delete matching name
    lst = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    targets: list[str] = []
    for line in (lst.stdout or "").splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] == "802-11-wireless" and parts[0] == name:
            targets.append(parts[0])
    if not targets:
        # Try delete by id == ssid anyway
        targets = [name]
    for conn in targets:
        completed = _run(["nmcli", "connection", "delete", conn], timeout=30.0)
        if completed.returncode != 0:
            raise NetworkCtlError(
                (completed.stderr or completed.stdout or f"échec oubli {conn}").strip()
            )


def bluetooth_status() -> dict[str, Any]:
    if shutil.which("bluetoothctl") is None:
        return {"available": False, "powered": False, "devices": [], "message": "bluetoothctl introuvable"}
    try:
        show = _run(["bluetoothctl", "show"])
        powered = "Powered: yes" in (show.stdout or "")
        devices_out = _run(["bluetoothctl", "devices"])
        devices: list[dict[str, str]] = []
        for line in (devices_out.stdout or "").splitlines():
            # Device AA:BB:CC:DD:EE:FF Name
            match = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.*)$", line)
            if match:
                devices.append({"mac": match.group(1), "name": match.group(2)})
        return {"available": True, "powered": powered, "devices": devices[:40], "message": ""}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": True, "powered": False, "devices": [], "message": str(exc)}


def set_bluetooth_powered(powered: bool) -> None:
    if shutil.which("bluetoothctl") is None:
        raise NetworkCtlError("bluetoothctl introuvable")
    value = "on" if powered else "off"
    completed = _run(["bluetoothctl", "power", value])
    if completed.returncode != 0:
        raise NetworkCtlError((completed.stderr or completed.stdout or "échec bluetooth").strip())
