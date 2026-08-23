# SPDX-License-Identifier: GPL-3.0-or-later
"""Stdlib-only host probe (stdin → ``python3 - <mode>`` via flatpak-spawn)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_BYTES_PER_GIB = 1024**3
_BYTES_PER_MIB = 1024**2


def _host_cwd() -> str:
    """Host-valid working directory; never inherit a Flatpak ``/app`` path."""
    home = os.environ.get("HOME") or ""
    if home and os.path.isdir(home) and not (home == "/app" or home.startswith("/app/")):
        return home
    return "/"


def _ensure_host_cwd() -> None:
    try:
        cwd = os.getcwd()
    except OSError:
        cwd = ""
    if cwd and os.path.isdir(cwd) and not (cwd == "/app" or cwd.startswith("/app/")):
        return
    for target in (_host_cwd(), "/"):
        try:
            os.chdir(target)
            return
        except OSError:
            continue


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _cpu_times() -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    for line in _read("/proc/stat").splitlines():
        if not line.startswith("cpu"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        vals = [int(x) for x in parts[1:]]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        rows.append((parts[0], idle, sum(vals)))
    return rows


def _cpu_percent(dt: float) -> tuple[float, list[float]]:
    a = _cpu_times()
    time.sleep(max(dt, 0.12))
    b = {name: (idle, total) for name, idle, total in _cpu_times()}
    per_core: list[float] = []
    total_pct = 0.0
    for name, idle1, total1 in a:
        idle2, total2 = b.get(name, (idle1, total1))
        d_total = max(total2 - total1, 1)
        d_idle = max(idle2 - idle1, 0)
        pct = round(max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0)), 1)
        if name == "cpu":
            total_pct = pct
        elif name.startswith("cpu"):
            per_core.append(pct)
    if not per_core:
        per_core = [total_pct]
        total_pct = total_pct
    elif total_pct == 0.0:
        total_pct = round(sum(per_core) / len(per_core), 1)
    return total_pct, per_core


def _meminfo() -> dict[str, int]:
    info: dict[str, int] = {}
    for line in _read("/proc/meminfo").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].rstrip(":")
        try:
            info[key] = int(parts[1]) * 1024
        except ValueError:
            continue
    return info


def _ram() -> dict[str, Any]:
    mem = _meminfo()
    total = mem.get("MemTotal", 0)
    avail = mem.get("MemAvailable", mem.get("MemFree", 0))
    used = max(total - avail, 0)
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    swap_used = max(swap_total - swap_free, 0)
    return {
        "used_gib": round(used / _BYTES_PER_GIB, 2),
        "free_gib": round(avail / _BYTES_PER_GIB, 2),
        "total_gib": round(total / _BYTES_PER_GIB, 2),
        "percent": round((used / total) * 100, 1) if total else 0.0,
        "swap_used_gib": round(swap_used / _BYTES_PER_GIB, 2),
        "swap_total_gib": round(swap_total / _BYTES_PER_GIB, 2),
        "swap_percent": round((swap_used / swap_total) * 100, 1) if swap_total else 0.0,
    }


def _temps() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    thermal = Path("/sys/class/thermal")
    if thermal.is_dir():
        for zone in sorted(thermal.glob("thermal_zone*")):
            try:
                raw = int((zone / "temp").read_text(encoding="utf-8").strip())
                celsius = raw / 1000.0 if raw > 200 else float(raw)
                label_path = zone / "type"
                label = label_path.read_text(encoding="utf-8").strip() if label_path.exists() else zone.name
                results.append({"label": label, "current": round(celsius, 1)})
            except (OSError, ValueError):
                continue
    hwmon = Path("/sys/class/hwmon")
    if hwmon.is_dir():
        for mon in sorted(hwmon.glob("hwmon*")):
            try:
                name = (mon / "name").read_text(encoding="utf-8").strip() if (mon / "name").exists() else "hwmon"
            except OSError:
                name = "hwmon"
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


def _cpu_freq() -> list[dict[str, float]]:
    freqs: list[dict[str, float]] = []
    base = Path("/sys/devices/system/cpu")
    for cpu in sorted(base.glob("cpu[0-9]*")):
        cur = cpu / "cpufreq/scaling_cur_freq"
        if not cur.exists():
            continue
        try:
            current = int(cur.read_text(encoding="utf-8").strip()) / 1000.0
            mn = cpu / "cpufreq/cpuinfo_min_freq"
            mx = cpu / "cpufreq/cpuinfo_max_freq"
            freqs.append(
                {
                    "current": round(current, 1),
                    "min": round(int(mn.read_text(encoding="utf-8").strip()) / 1000.0, 1) if mn.exists() else 0.0,
                    "max": round(int(mx.read_text(encoding="utf-8").strip()) / 1000.0, 1) if mx.exists() else 0.0,
                }
            )
        except (OSError, ValueError):
            continue
    return freqs


def _cpu_counts() -> tuple[int, int]:
    logical = os.cpu_count() or 0
    ids: set[tuple[str, str]] = set()
    phys = ""
    try:
        for line in _read("/proc/cpuinfo").splitlines():
            if line.startswith("physical id"):
                phys = line.split(":", 1)[1].strip()
            elif line.startswith("core id"):
                core = line.split(":", 1)[1].strip()
                ids.add((phys, core))
    except OSError:
        pass
    physical = len(ids) if ids else logical
    return logical, physical


def _disks() -> dict[str, Any]:
    partitions: list[dict[str, Any]] = []
    try:
        for line in _read("/proc/mounts").splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            device, mountpoint, fstype = parts[0], parts[1], parts[2]
            if fstype in _SKIP_FS or not device.startswith("/"):
                continue
            try:
                st = os.statvfs(mountpoint)
            except OSError:
                continue
            total = st.f_frsize * st.f_blocks
            free = st.f_frsize * st.f_bavail
            used = max(total - (st.f_frsize * st.f_bfree), 0)
            percent = round((used / total) * 100, 1) if total else 0.0
            partitions.append(
                {
                    "device": device,
                    "mountpoint": mountpoint,
                    "fstype": fstype,
                    "total_gib": round(total / _BYTES_PER_GIB, 2),
                    "used_gib": round(used / _BYTES_PER_GIB, 2),
                    "free_gib": round(free / _BYTES_PER_GIB, 2),
                    "percent": percent,
                }
            )
    except OSError:
        pass
    return {"partitions": partitions, "io_read_mibs": 0.0, "io_write_mibs": 0.0}


def _net_sample() -> tuple[int, int]:
    recv = 0
    sent = 0
    try:
        for line in _read("/proc/net/dev").splitlines()[2:]:
            if ":" not in line:
                continue
            iface, rest = line.split(":", 1)
            name = iface.strip()
            if name == "lo":
                continue
            cols = rest.split()
            if len(cols) < 9:
                continue
            recv += int(cols[0])
            sent += int(cols[8])
    except (OSError, ValueError):
        pass
    return recv, sent


def _ifaces() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    try:
        completed = subprocess.run(
            ["ip", "-j", "addr"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            cwd=_host_cwd(),
        )
        if completed.returncode == 0 and completed.stdout.strip():
            for item in json.loads(completed.stdout):
                ipv4: list[str] = []
                ipv6: list[str] = []
                for addr in item.get("addr_info") or []:
                    local = addr.get("local")
                    if not local:
                        continue
                    if addr.get("family") == "inet6":
                        ipv6.append(local)
                    else:
                        ipv4.append(local)
                results.append(
                    {
                        "name": item.get("ifname") or "",
                        "ipv4": ipv4,
                        "ipv6": ipv6,
                        "is_up": item.get("operstate") == "UP",
                        "speed_mbps": 0,
                    }
                )
            return results
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired, TypeError):
        pass
    return results


def _network(dt: float, recv1: int, sent1: int) -> dict[str, Any]:
    recv2, sent2 = _net_sample()
    down = max((recv2 - recv1) / dt / _BYTES_PER_MIB, 0.0)
    up = max((sent2 - sent1) / dt / _BYTES_PER_MIB, 0.0)
    return {
        "download_mibs": round(down, 2),
        "upload_mibs": round(up, 2),
        "interfaces": _ifaces(),
    }


def _battery() -> dict[str, Any] | None:
    base = Path("/sys/class/power_supply")
    if not base.is_dir():
        return None
    for bat in sorted(base.glob("BAT*")):
        try:
            cap = (bat / "capacity").read_text(encoding="utf-8").strip()
            status = (bat / "status").read_text(encoding="utf-8").strip() if (bat / "status").exists() else ""
            return {
                "percent": round(_safe_float(cap), 1),
                "plugged": status.lower() == "charging" or status.lower() == "full",
                "time_left": "—",
            }
        except (OSError, ValueError):
            continue
    return None


def _system() -> dict[str, Any]:
    uname = os.uname()
    try:
        load1, load5, load15 = os.getloadavg()
        loadavg = [round(load1, 2), round(load5, 2), round(load15, 2)]
    except (OSError, AttributeError):
        loadavg = []
    return {
        "hostname": uname.nodename,
        "kernel": f"{uname.sysname} {uname.release}",
        "machine": uname.machine,
        "loadavg": loadavg,
        "battery": _battery(),
    }


def _nvidia() -> list[dict[str, Any]] | None:
    query = "name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu"
    try:
        completed = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            cwd=_host_cwd(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not (completed.stdout or "").strip():
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
    return gpus or None


def _amd() -> list[dict[str, Any]]:
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
        try:
            if (device / "mem_info_vram_used").exists():
                mem_used = round(int((device / "mem_info_vram_used").read_text().strip()) / _BYTES_PER_MIB, 1)
            if (device / "mem_info_vram_total").exists():
                mem_total = round(int((device / "mem_info_vram_total").read_text().strip()) / _BYTES_PER_MIB, 1)
        except (OSError, ValueError):
            pass
        name = card.name
        try:
            if (device / "product_name").exists():
                name = (device / "product_name").read_text(encoding="utf-8").strip() or name
            else:
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


def _gpu() -> dict[str, Any]:
    nvidia = _nvidia()
    if nvidia:
        return {"available": True, "devices": nvidia}
    amd = _amd()
    return {"available": bool(amd), "devices": amd}


def _boot_time() -> float:
    for line in _read("/proc/stat").splitlines():
        if line.startswith("btime "):
            try:
                return float(line.split()[1])
            except (IndexError, ValueError):
                break
    return time.time()


def _sensors(temps: list[dict[str, Any]], battery: dict[str, Any] | None) -> list[dict[str, Any]]:
    sensors: list[dict[str, Any]] = []
    for item in temps:
        sensors.append({"kind": "temp", "label": item["label"], "value": item["current"], "unit": "°C"})
    if battery:
        sensors.append({"kind": "battery", "label": "Battery", "value": battery["percent"], "unit": "%"})
    return sensors


def _read_optional(path: str) -> str:
    try:
        return _read(path)
    except OSError:
        return ""


def _run_text(cmd: list[str], timeout: float = 8.0) -> str:
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_host_cwd(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout or ""


def _timezone() -> str:
    tz = _read_optional("/etc/timezone").strip()
    if tz:
        return tz.splitlines()[0].strip()
    try:
        link = os.readlink("/etc/localtime")
    except OSError:
        return ""
    marker = "/zoneinfo/"
    if marker in link:
        return link.split(marker, 1)[1]
    return ""


def collect_inventory_raw() -> dict[str, Any]:
    """Static host texts for the machine sheet. No CPU-sample sleep, no pkexec."""
    uname = os.uname()
    boot = _boot_time()
    now = time.time()
    os_release = ""
    for candidate in ("/etc/os-release", "/usr/lib/os-release"):
        os_release = _read_optional(candidate)
        if os_release:
            break
    return {
        "os_release": os_release,
        "meminfo": _read_optional("/proc/meminfo"),
        "df": _run_text(["df", "-P"]),
        "cpuinfo": _read_optional("/proc/cpuinfo"),
        "resolv": _read_optional("/etc/resolv.conf"),
        "route": _read_optional("/proc/net/route"),
        "ip_route": _run_text(["ip", "-j", "route"]),
        "hostname": uname.nodename,
        "kernel": f"{uname.sysname} {uname.release}",
        "machine": uname.machine,
        "timezone": _timezone(),
        "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
        "uptime_s": max(now - boot, 0.0),
        "gpu": _gpu(),
        "interfaces": _ifaces(),
        "pacman_qu": _run_text(["pacman", "-Qu"], timeout=12.0),
        "apt_upgradable": _run_text(["apt", "list", "--upgradable"], timeout=12.0),
    }


def collect_metrics() -> dict[str, Any]:
    recv1, sent1 = _net_sample()
    t0 = time.monotonic()
    total, per_core = _cpu_percent(0.15)
    dt = max(time.monotonic() - t0, 0.12)
    temps = _temps()
    logical, physical = _cpu_counts()
    system = _system()
    cpu = {
        "percent_total": total,
        "percent_per_core": per_core,
        "frequencies_mhz": _cpu_freq(),
        "temperatures_c": temps,
        "logical_cores": logical,
        "physical_cores": physical,
    }
    return {
        "timestamp": time.time(),
        "cpu": cpu,
        "ram": _ram(),
        "disks": _disks(),
        "network": _network(dt, recv1, sent1),
        "gpu": _gpu(),
        "boot_time": _boot_time(),
        "hostname": system.get("hostname", ""),
        "system": system,
        "sensors": _sensors(temps, system.get("battery")),
    }


_STATUS = {
    "R": "running",
    "S": "sleeping",
    "D": "disk-sleep",
    "Z": "zombie",
    "T": "stopped",
    "t": "tracing-stop",
    "I": "idle",
}


def _proc_user(uid: str) -> str:
    try:
        import pwd

        return pwd.getpwuid(int(uid)).pw_name
    except (OSError, ValueError, KeyError, ImportError):
        return uid


def list_processes(limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            status = (entry / "status").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rpar = stat.rfind(")")
        if rpar < 0:
            continue
        name = stat[stat.find("(") + 1 : rpar]
        rest = stat[rpar + 2 :].split()
        state = rest[0] if rest else "?"
        rss_pages = int(rest[21]) if len(rest) > 21 else 0
        rss = rss_pages * os.sysconf("SC_PAGE_SIZE") if rss_pages else 0
        uid = "0"
        for line in status.splitlines():
            if line.startswith("Uid:"):
                uid = line.split()[1]
                break
        utime = int(rest[11]) if len(rest) > 12 else 0
        stime = int(rest[12]) if len(rest) > 13 else 0
        rows.append(
            {
                "pid": pid,
                "name": name,
                "cpu": 0.0,
                "ram_mib": round(rss / _BYTES_PER_MIB, 1),
                "user": _proc_user(uid),
                "status": _STATUS.get(state, state),
                "_ticks": utime + stime,
            }
        )
    rows.sort(key=lambda item: item["ram_mib"], reverse=True)
    if limit is not None and limit > 0:
        rows = rows[:limit]
    for item in rows:
        item.pop("_ticks", None)
    return rows


def _cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
        return raw
    except OSError:
        return ""


def process_details(pid: int) -> dict[str, Any]:
    base = Path(f"/proc/{pid}")
    if not base.exists():
        return {"error": f"Processus {pid} introuvable"}
    try:
        stat = (base / "stat").read_text(encoding="utf-8", errors="replace")
        status = (base / "status").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"Processus {pid} introuvable"}
    rpar = stat.rfind(")")
    name = stat[stat.find("(") + 1 : rpar] if rpar > 0 else "?"
    rest = stat[rpar + 2 :].split() if rpar > 0 else []
    state = rest[0] if rest else "?"
    ppid = int(rest[1]) if len(rest) > 1 else 0
    rss_pages = int(rest[21]) if len(rest) > 21 else 0
    rss = rss_pages * os.sysconf("SC_PAGE_SIZE") if rss_pages else 0
    threads = None
    uid = "0"
    nice = None
    if len(rest) > 17:
        try:
            nice = int(rest[17])
        except ValueError:
            nice = None
    for line in status.splitlines():
        if line.startswith("Uid:"):
            uid = line.split()[1]
        elif line.startswith("Threads:"):
            try:
                threads = int(line.split()[1])
            except (IndexError, ValueError):
                pass
    cwd = "—"
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        pass
    cmdline = _cmdline(pid) or name
    return {
        "pid": pid,
        "name": name,
        "cmdline": cmdline,
        "cwd": cwd,
        "nice": nice,
        "num_threads": threads,
        "open_files": None,
        "create_time": None,
        "status": _STATUS.get(state, state),
        "user": _proc_user(uid),
        "cpu": 0.0,
        "ram_mib": round(rss / _BYTES_PER_MIB, 1),
        "_ppid": ppid,
    }


def process_tree(pid: int) -> dict[str, Any]:
    details = process_details(pid)
    if details.get("error"):
        return details
    ppid = int(details.pop("_ppid", 0) or 0)
    parent = None
    if ppid > 0:
        parent_info = process_details(ppid)
        if not parent_info.get("error"):
            parent = {"pid": ppid, "name": parent_info.get("name") or "?"}
    children: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rpar = stat.rfind(")")
        if rpar < 0:
            continue
        rest = stat[rpar + 2 :].split()
        if len(rest) < 2:
            continue
        try:
            child_ppid = int(rest[1])
        except ValueError:
            continue
        if child_ppid != pid:
            continue
        children.append({"pid": int(entry.name), "name": stat[stat.find("(") + 1 : rpar]})
    details["parent"] = parent
    details["children"] = children
    return details


def main(argv: list[str]) -> int:
    _ensure_host_cwd()
    mode = argv[1] if len(argv) > 1 else "metrics"
    if mode == "metrics":
        json.dump(collect_metrics(), sys.stdout, ensure_ascii=False)
    elif mode == "inventory":
        json.dump(collect_inventory_raw(), sys.stdout, ensure_ascii=False)
    elif mode == "processes":
        limit = int(argv[2]) if len(argv) > 2 else 0
        json.dump({"processes": list_processes(limit or None)}, sys.stdout, ensure_ascii=False)
    elif mode == "details":
        json.dump(process_details(int(argv[2])), sys.stdout, ensure_ascii=False)
    elif mode == "tree":
        json.dump(process_tree(int(argv[2])), sys.stdout, ensure_ascii=False)
    else:
        json.dump({"error": f"mode inconnu: {mode}"}, sys.stdout)
        return 1
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
