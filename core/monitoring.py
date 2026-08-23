# SPDX-License-Identifier: GPL-3.0-or-later
"""System resource monitoring (CPU, RAM, disks, network, GPU)."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import psutil

from core import host

_BYTES_PER_GIB = 1024**3
_BYTES_PER_MIB = 1024**2

_lock = threading.Lock()
_prev_disk: tuple[float, Any] | None = None
_prev_net: tuple[float, Any] | None = None
_history: dict[str, list[float]] = {
    "cpu": [],
    "ram": [],
    "net_down": [],
    "net_up": [],
}
_HISTORY_MAX = 120


def push_history(metrics: dict[str, Any], *, max_points: int | None = None) -> dict[str, list[float]]:
    """Append metrics into in-memory circular history buffers."""
    limit = max(10, min(int(max_points or _HISTORY_MAX), 300))
    cpu = float((metrics.get("cpu") or {}).get("percent_total") or 0)
    ram = float((metrics.get("ram") or {}).get("percent") or 0)
    net = metrics.get("network") or {}
    down = float(net.get("download_mibs") or 0)
    up = float(net.get("upload_mibs") or 0)
    with _lock:
        for key, value in (
            ("cpu", cpu),
            ("ram", ram),
            ("net_down", down),
            ("net_up", up),
        ):
            series = _history.setdefault(key, [])
            series.append(value)
            if len(series) > limit:
                del series[0 : len(series) - limit]
        return {k: list(v) for k, v in _history.items()}


def get_history() -> dict[str, list[float]]:
    with _lock:
        return {k: list(v) for k, v in _history.items()}


def detailed_sensors() -> list[dict[str, Any]]:
    """lm-sensors style dump via psutil + /sys fallbacks already in temps."""
    sensors: list[dict[str, Any]] = []
    for item in _cpu_temperatures():
        sensors.append({"kind": "temp", "label": item["label"], "value": item["current"], "unit": "°C"})
    try:
        fans = psutil.sensors_fans() or {}
        for chip, entries in fans.items():
            for entry in entries:
                sensors.append(
                    {
                        "kind": "fan",
                        "label": f"{chip}/{entry.label or 'fan'}",
                        "value": float(entry.current),
                        "unit": "RPM",
                    }
                )
    except (AttributeError, OSError):
        pass
    # Battery already in system; add raw if present
    try:
        bats = psutil.sensors_battery()
        if bats is not None:
            sensors.append(
                {
                    "kind": "battery",
                    "label": "Battery",
                    "value": float(bats.percent),
                    "unit": "%",
                }
            )
    except (AttributeError, OSError):
        pass
    return sensors


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_sys_temp_celsius() -> list[dict[str, Any]]:
    """Fallback temperature readers from /sys when psutil has no sensors."""
    results: list[dict[str, Any]] = []

    thermal = Path("/sys/class/thermal")
    if thermal.is_dir():
        for zone in sorted(thermal.glob("thermal_zone*")):
            temp_path = zone / "temp"
            type_path = zone / "type"
            try:
                raw = int(temp_path.read_text(encoding="utf-8").strip())
                # Values are usually millidegrees Celsius.
                celsius = raw / 1000.0 if raw > 200 else float(raw)
                label = type_path.read_text(encoding="utf-8").strip() if type_path.exists() else zone.name
                results.append({"label": label, "current": round(celsius, 1)})
            except (OSError, ValueError):
                continue

    hwmon = Path("/sys/class/hwmon")
    if hwmon.is_dir():
        for mon in sorted(hwmon.glob("hwmon*")):
            name = "hwmon"
            name_path = mon / "name"
            try:
                if name_path.exists():
                    name = name_path.read_text(encoding="utf-8").strip()
            except OSError:
                pass
            for input_path in sorted(mon.glob("temp*_input")):
                try:
                    raw = int(input_path.read_text(encoding="utf-8").strip())
                    celsius = raw / 1000.0 if raw > 200 else float(raw)
                    label_path = input_path.with_name(input_path.name.replace("_input", "_label"))
                    label = name
                    if label_path.exists():
                        label = f"{name}/{label_path.read_text(encoding='utf-8').strip()}"
                    results.append({"label": label, "current": round(celsius, 1)})
                except (OSError, ValueError):
                    continue

    return results


def _cpu_temperatures() -> list[dict[str, Any]]:
    temps: list[dict[str, Any]] = []
    try:
        sensors = psutil.sensors_temperatures(fahrenheit=False) or {}
        for chip, entries in sensors.items():
            for entry in entries:
                current = getattr(entry, "current", None)
                if current is None:
                    continue
                label = entry.label or chip
                temps.append({"label": label, "current": round(float(current), 1)})
    except (AttributeError, OSError):
        pass

    if not temps:
        temps = _read_sys_temp_celsius()
    return temps


def _cpu_info() -> dict[str, Any]:
    # First call may return 0.0; callers poll regularly so subsequent values are fine.
    per_core = [round(v, 1) for v in psutil.cpu_percent(interval=None, percpu=True)]
    total = round(sum(per_core) / len(per_core), 1) if per_core else round(psutil.cpu_percent(interval=None), 1)

    frequencies: list[dict[str, float]] = []
    try:
        freq = psutil.cpu_freq(percpu=True)
        if freq:
            for item in freq:
                frequencies.append(
                    {
                        "current": round(_safe_float(item.current), 1),
                        "min": round(_safe_float(item.min), 1),
                        "max": round(_safe_float(item.max), 1),
                    }
                )
        else:
            single = psutil.cpu_freq(percpu=False)
            if single:
                frequencies.append(
                    {
                        "current": round(_safe_float(single.current), 1),
                        "min": round(_safe_float(single.min), 1),
                        "max": round(_safe_float(single.max), 1),
                    }
                )
    except (AttributeError, OSError, NotImplementedError):
        pass

    return {
        "percent_total": total,
        "percent_per_core": per_core,
        "frequencies_mhz": frequencies,
        "temperatures_c": _cpu_temperatures(),
        "logical_cores": psutil.cpu_count(logical=True) or 0,
        "physical_cores": psutil.cpu_count(logical=False) or 0,
    }


def _ram_info() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "used_gib": round(vm.used / _BYTES_PER_GIB, 2),
        "free_gib": round(vm.available / _BYTES_PER_GIB, 2),
        "total_gib": round(vm.total / _BYTES_PER_GIB, 2),
        "percent": round(vm.percent, 1),
        "swap_used_gib": round(swap.used / _BYTES_PER_GIB, 2),
        "swap_total_gib": round(swap.total / _BYTES_PER_GIB, 2),
        "swap_percent": round(swap.percent, 1),
    }


def _disk_info() -> dict[str, Any]:
    global _prev_disk
    partitions: list[dict[str, Any]] = []
    for part in psutil.disk_partitions(all=False):
        if not part.fstype or part.fstype in {"squashfs", "overlay", "tmpfs", "devtmpfs"}:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        partitions.append(
            {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_gib": round(usage.total / _BYTES_PER_GIB, 2),
                "used_gib": round(usage.used / _BYTES_PER_GIB, 2),
                "free_gib": round(usage.free / _BYTES_PER_GIB, 2),
                "percent": round(usage.percent, 1),
            }
        )

    read_mibs = 0.0
    write_mibs = 0.0
    now = time.monotonic()
    try:
        counters = psutil.disk_io_counters()
    except (OSError, AttributeError):
        counters = None

    if counters is not None:
        with _lock:
            if _prev_disk is not None:
                prev_t, prev_c = _prev_disk
                dt = max(now - prev_t, 1e-6)
                read_mibs = max((counters.read_bytes - prev_c.read_bytes) / dt / _BYTES_PER_MIB, 0.0)
                write_mibs = max((counters.write_bytes - prev_c.write_bytes) / dt / _BYTES_PER_MIB, 0.0)
            _prev_disk = (now, counters)

    return {
        "partitions": partitions,
        "io_read_mibs": round(read_mibs, 2),
        "io_write_mibs": round(write_mibs, 2),
    }


def _iface_addresses() -> list[dict[str, Any]]:
    """Per-interface IP addresses via psutil.net_if_addrs."""
    results: list[dict[str, Any]] = []
    try:
        addrs = psutil.net_if_addrs()
    except (OSError, AttributeError):
        return results

    try:
        stats = psutil.net_if_stats()
    except (OSError, AttributeError):
        stats = {}

    for name, entries in sorted(addrs.items()):
        ipv4: list[str] = []
        ipv6: list[str] = []
        for entry in entries:
            family = getattr(entry, "family", None)
            address = getattr(entry, "address", "") or ""
            if not address:
                continue
            fam_name = str(family)
            if "AF_INET6" in fam_name or getattr(family, "name", "") == "AF_INET6":
                ipv6.append(address)
            elif "AF_INET" in fam_name or getattr(family, "name", "") == "AF_INET":
                ipv4.append(address)
            else:
                # Numeric family values: 2=IPv4 on Linux, 10=IPv6
                try:
                    fam_int = int(family)
                except (TypeError, ValueError):
                    continue
                if fam_int == 2:
                    ipv4.append(address)
                elif fam_int == 10:
                    ipv6.append(address)

        st = stats.get(name)
        results.append(
            {
                "name": name,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "is_up": bool(getattr(st, "isup", False)) if st is not None else None,
                "speed_mbps": getattr(st, "speed", 0) if st is not None else 0,
            }
        )
    return results


def _network_info() -> dict[str, Any]:
    global _prev_net
    down_mibs = 0.0
    up_mibs = 0.0
    now = time.monotonic()
    try:
        counters = psutil.net_io_counters()
    except (OSError, AttributeError):
        counters = None

    if counters is not None:
        with _lock:
            if _prev_net is not None:
                prev_t, prev_c = _prev_net
                dt = max(now - prev_t, 1e-6)
                down_mibs = max((counters.bytes_recv - prev_c.bytes_recv) / dt / _BYTES_PER_MIB, 0.0)
                up_mibs = max((counters.bytes_sent - prev_c.bytes_sent) / dt / _BYTES_PER_MIB, 0.0)
            _prev_net = (now, counters)

    return {
        "download_mibs": round(down_mibs, 2),
        "upload_mibs": round(up_mibs, 2),
        "interfaces": _iface_addresses(),
    }


def _battery_info() -> dict[str, Any] | None:
    try:
        batt = psutil.sensors_battery()
    except (AttributeError, OSError):
        return None
    if batt is None:
        return None
    secs = batt.secsleft
    if secs is None or secs < 0 or secs == psutil.POWER_TIME_UNLIMITED:
        eta = "—"
    elif secs == psutil.POWER_TIME_UNKNOWN:
        eta = "?"
    else:
        hours, rem = divmod(int(secs), 3600)
        minutes, _ = divmod(rem, 60)
        eta = f"{hours}h {minutes:02d}m"
    return {
        "percent": round(float(batt.percent), 1),
        "plugged": bool(batt.power_plugged),
        "time_left": eta,
    }


def _system_info() -> dict[str, Any]:
    uname = os.uname() if hasattr(os, "uname") else None
    try:
        load1, load5, load15 = os.getloadavg()
        loadavg = [round(load1, 2), round(load5, 2), round(load15, 2)]
    except (OSError, AttributeError):
        loadavg = []

    return {
        "hostname": uname.nodename if uname else "",
        "kernel": f"{uname.sysname} {uname.release}" if uname else "",
        "machine": uname.machine if uname else "",
        "loadavg": loadavg,
        "battery": _battery_info(),
    }


def _nvidia_gpu() -> list[dict[str, Any]] | None:
    if shutil.which("nvidia-smi") is None:
        return None

    # nvidia-smi spawn every poll is expensive; reuse for a few seconds.
    cache = getattr(_nvidia_gpu, "_cache", None)
    cache_ts = float(getattr(_nvidia_gpu, "_cache_ts", 0.0) or 0.0)
    now = time.time()
    if cache is not None and (now - cache_ts) < 5.0:
        return cache

    query = (
        "name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu"
    )
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            cwd=host.host_cwd(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0 or not completed.stdout.strip():
        return None

    gpus: list[dict[str, Any]] = []
    for line in completed.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        gpus.append(
            {
                "vendor": "NVIDIA",
                "name": parts[0],
                "busy_percent": round(_safe_float(parts[1]), 1),
                "mem_busy_percent": round(_safe_float(parts[2]), 1),
                "mem_used_mib": round(_safe_float(parts[3]), 1),
                "mem_total_mib": round(_safe_float(parts[4]), 1),
                "temperature_c": round(_safe_float(parts[5]), 1),
            }
        )
    result = gpus or None
    _nvidia_gpu._cache = result  # type: ignore[attr-defined]
    _nvidia_gpu._cache_ts = now  # type: ignore[attr-defined]
    return result


def _amd_gpu() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    drm = Path("/sys/class/drm")
    if not drm.is_dir():
        return gpus

    for card in sorted(drm.glob("card[0-9]")):
        if "-" in card.name:
            continue
        device = card / "device"
        busy_path = device / "gpu_busy_percent"
        if not busy_path.exists():
            continue
        try:
            busy = round(_safe_float(busy_path.read_text(encoding="utf-8").strip()), 1)
        except OSError:
            continue

        mem_used = 0.0
        mem_total = 0.0
        used_path = device / "mem_info_vram_used"
        total_path = device / "mem_info_vram_total"
        try:
            if used_path.exists():
                mem_used = round(int(used_path.read_text(encoding="utf-8").strip()) / _BYTES_PER_MIB, 1)
            if total_path.exists():
                mem_total = round(int(total_path.read_text(encoding="utf-8").strip()) / _BYTES_PER_MIB, 1)
        except (OSError, ValueError):
            pass

        name = card.name
        vendor_path = device / "vendor"
        try:
            if (device / "product_name").exists():
                name = (device / "product_name").read_text(encoding="utf-8").strip() or name
            elif vendor_path.exists():
                name = f"AMD GPU ({card.name})"
        except OSError:
            name = f"AMD GPU ({card.name})"

        gpus.append(
            {
                "vendor": "AMD",
                "name": name,
                "busy_percent": busy,
                "mem_busy_percent": round((mem_used / mem_total) * 100, 1) if mem_total else 0.0,
                "mem_used_mib": mem_used,
                "mem_total_mib": mem_total,
                "temperature_c": None,
            }
        )
    return gpus


def _gpu_info() -> dict[str, Any]:
    nvidia = _nvidia_gpu()
    if nvidia:
        return {"available": True, "devices": nvidia}
    amd = _amd_gpu()
    return {"available": bool(amd), "devices": amd}


def collect_metrics() -> dict[str, Any]:
    """Collect a full snapshot of system metrics."""
    if host.is_flatpak():
        metrics = host.collect_metrics()
        metrics["history"] = push_history(metrics)
        return metrics

    # Prime cpu_percent on first use if needed.
    if not hasattr(collect_metrics, "_primed"):
        psutil.cpu_percent(interval=None, percpu=True)
        collect_metrics._primed = True  # type: ignore[attr-defined]
        time.sleep(0.15)

    system = _system_info()
    metrics = {
        "timestamp": time.time(),
        "cpu": _cpu_info(),
        "ram": _ram_info(),
        "disks": _disk_info(),
        "network": _network_info(),
        "gpu": _gpu_info(),
        "boot_time": psutil.boot_time(),
        "hostname": system.get("hostname", ""),
        "system": system,
        "sensors": detailed_sensors(),
    }
    metrics["history"] = push_history(metrics)
    return metrics


def format_uptime(boot_time: float) -> str:
    seconds = max(int(time.time() - boot_time), 0)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}j {hours:02d}h {minutes:02d}m"
    return f"{hours:02d}h {minutes:02d}m"
