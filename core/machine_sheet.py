# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only local machine inventory (Fiche). No pkexec."""

from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path
from typing import Any

from core import backup, host

_SKIP_FS = {
    "squashfs",
    "overlay",
    "tmpfs",
    "devtmpfs",
    "proc",
    "sysfs",
    "cgroup",
    "cgroup2",
    "devpts",
    "securityfs",
    "pstore",
    "bpf",
    "tracefs",
    "debugfs",
    "hugetlbfs",
    "mqueue",
    "fusectl",
    "configfs",
    "autofs",
    "ramfs",
}

_SKIP_MOUNT_PREFIXES = ("/snap/", "/var/lib/docker/", "/run/", "/sys/", "/proc/")
_SKIP_DEVICES = {"none", "tmpfs", "devtmpfs", "overlay", "squashfs", "efivarfs"}
_SKIP_MOUNTS = {
    "/dev/shm",
    "/root",
    "/srv",
    "/var/tmp",
    "/var/log",
    "/var/cache",
    "/tmp",
    "/dev",
}
_KEEP_MOUNTS = {"/", "/home"}
_KIB = 1024
_BYTES_PER_GIB = 1024**3


def parse_os_release(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in (text or "").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def parse_meminfo(text: str) -> dict[str, int]:
    info: dict[str, int] = {}
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].rstrip(":")
        try:
            kib = int(parts[1])
        except ValueError:
            continue
        info[key] = kib * _KIB
    return info


def ram_from_meminfo(mem: dict[str, int]) -> dict[str, Any]:
    total = int(mem.get("MemTotal") or 0)
    avail = int(mem.get("MemAvailable") or mem.get("MemFree") or 0)
    used = max(total - avail, 0)
    return {
        "total_bytes": total,
        "used_bytes": used,
        "avail_bytes": avail,
        "total_gib": round(total / _BYTES_PER_GIB, 2) if total else 0.0,
        "used_gib": round(used / _BYTES_PER_GIB, 2) if total else 0.0,
        "avail_gib": round(avail / _BYTES_PER_GIB, 2) if total else 0.0,
        "percent": round((used / total) * 100, 1) if total else 0.0,
    }


def _skip_mount(device: str, mountpoint: str, fstype: str) -> bool:
    if mountpoint in _KEEP_MOUNTS:
        return False
    if fstype in _SKIP_FS:
        return True
    if mountpoint in _SKIP_MOUNTS:
        return True
    if any(mountpoint.startswith(prefix) for prefix in _SKIP_MOUNT_PREFIXES):
        return True
    if device in _SKIP_DEVICES:
        return True
    return False


def parse_df_p(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        if not line.strip() or line.startswith("Filesystem"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        device = parts[0]
        try:
            total_kib = int(parts[1])
            used_kib = int(parts[2])
            avail_kib = int(parts[3])
        except ValueError:
            continue
        cap = parts[4].rstrip("%")
        try:
            percent = float(cap)
        except ValueError:
            percent = 0.0
        mountpoint = parts[5]
        fstype = ""
        if _skip_mount(device, mountpoint, fstype):
            continue
        if device in _SKIP_FS or device in _SKIP_DEVICES:
            continue
        rows.append(
            {
                "device": device,
                "mountpoint": mountpoint,
                "fstype": fstype,
                "total_kib": total_kib,
                "used_kib": used_kib,
                "avail_kib": avail_kib,
                "percent": percent,
                "total_gib": round(total_kib / _KIB / _KIB, 2),
                "used_gib": round(used_kib / _KIB / _KIB, 2),
                "free_gib": round(avail_kib / _KIB / _KIB, 2),
            }
        )
    return rows


def parse_cpuinfo(text: str) -> dict[str, Any]:
    model = ""
    cores = 0
    for line in (text or "").splitlines():
        if line.startswith("processor"):
            cores += 1
        elif line.startswith("model name") and not model:
            model = line.split(":", 1)[1].strip()
    return {"model": model, "logical_cores": cores}


def parse_resolv_conf(text: str) -> list[str]:
    seen: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            addr = parts[1]
            if addr not in seen:
                seen.append(addr)
    return seen


def _hex_ipv4_le(value: str) -> str:
    raw = value.strip()
    if len(raw) != 8:
        return ""
    try:
        num = int(raw, 16)
    except ValueError:
        return ""
    return ".".join(str((num >> shift) & 0xFF) for shift in (0, 8, 16, 24))


def parse_ip_route_json(text: str) -> str:
    if not (text or "").strip():
        return ""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, list):
        return ""
    for item in data:
        if not isinstance(item, dict):
            continue
        dst = str(item.get("dst") or "")
        if dst not in {"default", "0.0.0.0/0", "::/0"}:
            continue
        gw = item.get("gateway")
        if gw:
            return str(gw)
    return ""


def parse_proc_route(text: str) -> str:
    for line in (text or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        if parts[1] == "00000000":
            gw = _hex_ipv4_le(parts[2])
            if gw and gw != "0.0.0.0":
                return gw
    return ""


def parse_pacman_qu(text: str) -> list[str]:
    names: list[str] = []
    for line in (text or "").splitlines():
        name = line.split(None, 1)[0].strip() if line.strip() else ""
        if name and not name.startswith("("):
            names.append(name)
    return names


def parse_apt_upgradable(text: str) -> list[str]:
    names: list[str] = []
    for line in (text or "").splitlines():
        if not line or line.startswith("Listing"):
            continue
        name = line.split("/", 1)[0].strip()
        if name:
            names.append(name)
    return names


def _format_uptime(seconds: float) -> str:
    total = max(int(seconds), 0)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


_VIRTUAL_IFACE_PREFIXES = (
    "veth",
    "docker",
    "br-",
    "virbr",
    "tun",
    "tap",
    "cni",
    "flannel",
)


def _useful_iface(name: str) -> bool:
    if not name or name in {"lo", "lo0"}:
        return False
    return not name.startswith(_VIRTUAL_IFACE_PREFIXES)


def assemble_sheet(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    osrel = parse_os_release(str(data.get("os_release") or ""))
    mem = parse_meminfo(str(data.get("meminfo") or ""))
    cpu = parse_cpuinfo(str(data.get("cpuinfo") or ""))
    storage = parse_df_p(str(data.get("df") or ""))
    dns = parse_resolv_conf(str(data.get("resolv") or ""))
    gateway = (
        str(data.get("gateway") or "")
        or parse_ip_route_json(str(data.get("ip_route") or ""))
        or parse_proc_route(str(data.get("route") or ""))
    )
    interfaces = [
        item
        for item in (data.get("interfaces") if isinstance(data.get("interfaces"), list) else [])
        if isinstance(item, dict) and _useful_iface(str(item.get("name") or ""))
    ]
    gpu = data.get("gpu") if isinstance(data.get("gpu"), dict) else {"available": False, "devices": []}
    snaps = data.get("snapshots") if isinstance(data.get("snapshots"), dict) else {}
    pacman = parse_pacman_qu(str(data.get("pacman_qu") or ""))
    apt = parse_apt_upgradable(str(data.get("apt_upgradable") or ""))
    pending = pacman + apt
    uptime_s = float(data.get("uptime_s") or 0)
    return {
        "collected_at": str(data.get("datetime") or time.strftime("%Y-%m-%d %H:%M:%S")),
        "identity": {
            "hostname": str(data.get("hostname") or ""),
            "pretty_name": osrel.get("PRETTY_NAME") or osrel.get("NAME") or "",
            "os_id": osrel.get("ID") or "",
            "version": osrel.get("VERSION") or osrel.get("VERSION_ID") or "",
            "kernel": str(data.get("kernel") or ""),
            "arch": str(data.get("machine") or ""),
        },
        "cpu": cpu,
        "ram": ram_from_meminfo(mem),
        "gpu": gpu,
        "storage": storage,
        "network": {
            "interfaces": interfaces,
            "gateway": gateway,
            "dns": dns,
        },
        "time": {
            "uptime_s": uptime_s,
            "uptime": _format_uptime(uptime_s),
            "timezone": str(data.get("timezone") or ""),
            "datetime": str(data.get("datetime") or ""),
        },
        "updates": {
            "pending": len(pending),
            "names": pending,
            "source": "local-cache",
        },
        "snapshots": {
            "detected": bool(snaps.get("detected")),
            "backend": str(snaps.get("backend") or "none"),
        },
    }


def to_json(sheet: dict[str, Any]) -> str:
    return json.dumps(sheet, indent=2, ensure_ascii=False) + "\n"


def to_text(sheet: dict[str, Any]) -> str:
    ident = sheet.get("identity") or {}
    cpu = sheet.get("cpu") or {}
    ram = sheet.get("ram") or {}
    gpu = sheet.get("gpu") or {}
    net = sheet.get("network") or {}
    tinfo = sheet.get("time") or {}
    updates = sheet.get("updates") or {}
    snaps = sheet.get("snapshots") or {}
    lines = [
        f"Hôte : {ident.get('hostname') or '—'}",
        f"OS : {ident.get('pretty_name') or '—'} ({ident.get('os_id') or '—'}) {ident.get('version') or ''}".rstrip(),
        f"Noyau : {ident.get('kernel') or '—'} · {ident.get('arch') or '—'}",
        f"CPU : {cpu.get('model') or '—'} · {cpu.get('logical_cores') or 0} cœurs",
        f"RAM : {ram.get('used_gib', 0)} / {ram.get('total_gib', 0)} Gio ({ram.get('percent', 0)}%)",
    ]
    devices = gpu.get("devices") or []
    if devices:
        for item in devices:
            lines.append(f"GPU : {item.get('vendor') or ''} {item.get('name') or '—'}".strip())
    else:
        lines.append("GPU : —")
    for part in sheet.get("storage") or []:
        lines.append(
            f"Stockage {part.get('mountpoint')} : {part.get('used_gib', 0)} / "
            f"{part.get('total_gib', 0)} Gio ({part.get('percent', 0)}% · libre {part.get('free_gib', 0)})"
        )
    lines.append(f"Passerelle : {net.get('gateway') or '—'}")
    dns = ", ".join(net.get("dns") or []) or "—"
    lines.append(f"DNS : {dns}")
    for iface in net.get("interfaces") or []:
        addrs = list(iface.get("ipv4") or []) + list(iface.get("ipv6") or [])
        lines.append(f"Iface {iface.get('name') or '?'} : {', '.join(addrs) or '—'}")
    lines.append(f"Uptime : {tinfo.get('uptime') or '—'} · {tinfo.get('timezone') or ''} {tinfo.get('datetime') or ''}".rstrip())
    lines.append(f"MAJ en attente (cache local) : {updates.get('pending', 0)}")
    detected = "oui" if snaps.get("detected") else "non"
    lines.append(f"Clichés Timeshift/Snapper : {detected} ({snaps.get('backend') or 'none'})")
    return "\n".join(lines) + "\n"


def to_csv(sheet: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["section", "key", "value"])
    ident = sheet.get("identity") or {}
    for key in ("hostname", "pretty_name", "os_id", "version", "kernel", "arch"):
        writer.writerow(["identity", key, ident.get(key) or ""])
    cpu = sheet.get("cpu") or {}
    writer.writerow(["cpu", "model", cpu.get("model") or ""])
    writer.writerow(["cpu", "logical_cores", cpu.get("logical_cores") or 0])
    ram = sheet.get("ram") or {}
    for key in ("used_gib", "total_gib", "percent"):
        writer.writerow(["ram", key, ram.get(key, "")])
    gpu = sheet.get("gpu") or {}
    devices = gpu.get("devices") or []
    if devices:
        for idx, item in enumerate(devices):
            writer.writerow(["gpu", f"device_{idx}", f"{item.get('vendor') or ''} {item.get('name') or ''}".strip()])
    else:
        writer.writerow(["gpu", "device", ""])
    for part in sheet.get("storage") or []:
        writer.writerow(
            [
                "storage",
                part.get("mountpoint") or "",
                f"{part.get('used_gib', 0)}/{part.get('total_gib', 0)} Gio {part.get('percent', 0)}%",
            ]
        )
    net = sheet.get("network") or {}
    writer.writerow(["network", "gateway", net.get("gateway") or ""])
    writer.writerow(["network", "dns", ";".join(net.get("dns") or [])])
    for iface in net.get("interfaces") or []:
        addrs = list(iface.get("ipv4") or []) + list(iface.get("ipv6") or [])
        writer.writerow(["network", iface.get("name") or "", ";".join(addrs)])
    tinfo = sheet.get("time") or {}
    for key in ("uptime", "timezone", "datetime"):
        writer.writerow(["time", key, tinfo.get(key) or ""])
    updates = sheet.get("updates") or {}
    writer.writerow(["updates", "pending", updates.get("pending", 0)])
    snaps = sheet.get("snapshots") or {}
    writer.writerow(["snapshots", "detected", "yes" if snaps.get("detected") else "no"])
    writer.writerow(["snapshots", "backend", snaps.get("backend") or "none"])
    return buf.getvalue()


def default_export_path(suffix: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Documents" / f"hub-systeme-fiche-{stamp}.{suffix}"


def collect_sheet() -> dict[str, Any]:
    raw = host.collect_inventory()
    backend = backup.detect_backend()
    raw["snapshots"] = {
        "detected": backend != "none",
        "backend": backend,
    }
    return assemble_sheet(raw)
