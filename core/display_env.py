# SPDX-License-Identifier: GPL-3.0-or-later
"""Pick a safe GTK4 display env before Gtk is imported.

Native reference is CachyOS (bare metal): never set GSK/GDK/LIBGL.
Mint 21 / Ubuntu jammy native is unsupported for now; cairo+x11+software
fallbacks stay gated for a later return, and for VirtualBox VMs only.
"""

from __future__ import annotations

import os
from pathlib import Path

_OS_RELEASE_CANDIDATES = (
    Path("/etc/os-release"),
    Path("/run/host/etc/os-release"),
    Path("/var/run/host/etc/os-release"),
)
_DMI_PRODUCT = Path("/sys/class/dmi/id/product_name")
_VM_MARKERS = ("virtualbox", "vmware", "qemu", "kvm", "bochs", "virtual machine")

# GTK 4.6 has no GDK_DEBUG=gl-disable. These three exist and are enough.
_CAIRO_HOST_ENV = {
    "GSK_RENDERER": "cairo",
    "GDK_BACKEND": "x11",
    "LIBGL_ALWAYS_SOFTWARE": "1",
}


def read_os_release(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return data
    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def needs_cairo_gsk(
    os_release: dict[str, str],
    *,
    product_name: str = "",
) -> bool:
    os_id = (os_release.get("ID") or "").lower()
    like = (os_release.get("ID_LIKE") or "").lower()
    version = os_release.get("VERSION_ID") or ""
    ubuntu = (os_release.get("UBUNTU_CODENAME") or os_release.get("VERSION_CODENAME") or "").lower()
    product = product_name.lower()
    is_vm = any(marker in product for marker in _VM_MARKERS)
    # Bare CachyOS / Arch: never GSK/GDK/LIBGL. VirtualBox on those hosts may still use cairo.
    if os_id in {"cachyos", "arch"} or "arch" in like.split():
        return is_vm
    if os_id == "linuxmint" and version.startswith("21"):
        return True
    if ubuntu == "jammy":
        return True
    if os_id == "ubuntu" and version.startswith("22.04"):
        return True
    if "ubuntu" in like and version.startswith("22.04"):
        return True
    return is_vm


def cairo_display_env(
    os_release: dict[str, str],
    *,
    product_name: str = "",
) -> dict[str, str]:
    """Env to apply on Mint 21 / jammy / VMs. Empty on CachyOS (bare metal)."""
    if not needs_cairo_gsk(os_release, product_name=product_name):
        return {}
    return dict(_CAIRO_HOST_ENV)


def needs_map_hold(
    os_release: dict[str, str],
    *,
    product_name: str = "",
) -> bool:
    """Gio hold + 3s map timeout: Mint/jammy/VM only. Never on bare CachyOS."""
    return needs_cairo_gsk(os_release, product_name=product_name)


def host_needs_map_hold() -> bool:
    return needs_map_hold(_host_os_release(), product_name=_host_product_name())


def _host_os_release() -> dict[str, str]:
    for path in _OS_RELEASE_CANDIDATES:
        data = read_os_release(path)
        if data:
            return data
    return {}


def _host_product_name() -> str:
    try:
        return _DMI_PRODUCT.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def apply_safe_display_env() -> dict[str, str]:
    """Set cairo/X11/software-GL on Mint 21 / jammy / VMs. Return applied vars.

    Existing GSK_RENDERER / GDK_BACKEND / LIBGL_* are left untouched (setdefault).
    CachyOS bare metal: no changes (empty dict).
    """
    extras = cairo_display_env(_host_os_release(), product_name=_host_product_name())
    applied: dict[str, str] = {}
    for key, value in extras.items():
        os.environ.setdefault(key, value)
        applied[key] = os.environ[key]
    return applied
