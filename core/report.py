# SPDX-License-Identifier: GPL-3.0-or-later
"""HTML system health report export."""

from __future__ import annotations

import html
import time
from pathlib import Path
from typing import Any

from core import monitoring


def build_report_html(metrics: dict[str, Any] | None = None) -> str:
    data = metrics or monitoring.collect_metrics()
    cpu = data.get("cpu") or {}
    ram = data.get("ram") or {}
    system = data.get("system") or {}
    disks = data.get("disks") or {}
    net = data.get("network") or {}
    gpu = data.get("gpu") or {}

    disk_rows = "".join(
        f"<tr><td>{html.escape(str(p.get('mountpoint')))}</td>"
        f"<td>{p.get('used_gib', 0):.1f} / {p.get('total_gib', 0):.1f} Go</td>"
        f"<td>{p.get('percent', 0):.0f}%</td></tr>"
        for p in disks.get("partitions") or []
    )
    gpu_rows = "".join(
        f"<tr><td>{html.escape(str(g.get('vendor')))} {html.escape(str(g.get('name')))}</td>"
        f"<td>{g.get('busy_percent', 0):.0f}%</td></tr>"
        for g in gpu.get("devices") or []
    ) or "<tr><td colspan='2'>Aucun GPU détecté</td></tr>"

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"/>
<title>Rapport Hub Système</title>
<style>
body{{font-family:system-ui,sans-serif;background:#1e1e1e;color:#eee;margin:2rem}}
h1,h2{{color:#7ec8ff}} table{{border-collapse:collapse;width:100%;margin:1rem 0}}
td,th{{border:1px solid #444;padding:.5rem;text-align:left}} th{{background:#2a2a2a}}
</style></head><body>
<h1>Rapport santé système</h1>
<p>Généré le {html.escape(stamp)} — hôte <b>{html.escape(str(system.get('hostname') or data.get('hostname') or ''))}</b></p>
<h2>Système</h2>
<ul>
<li>Noyau : {html.escape(str(system.get('kernel') or '—'))}</li>
<li>Uptime : {html.escape(monitoring.format_uptime(data.get('boot_time') or 0))}</li>
<li>Loadavg : {html.escape(str(system.get('loadavg') or '—'))}</li>
</ul>
<h2>CPU / RAM</h2>
<ul>
<li>CPU : {cpu.get('percent_total', 0):.1f}%</li>
<li>RAM : {ram.get('used_gib', 0):.2f} / {ram.get('total_gib', 0):.2f} Go ({ram.get('percent', 0):.0f}%)</li>
</ul>
<h2>Disques</h2>
<table><tr><th>Point de montage</th><th>Usage</th><th>%</th></tr>{disk_rows}</table>
<h2>Réseau</h2>
<p>↓ {net.get('download_mibs', 0):.2f} Mo/s · ↑ {net.get('upload_mibs', 0):.2f} Mo/s</p>
<h2>GPU</h2>
<table><tr><th>Périphérique</th><th>Charge</th></tr>{gpu_rows}</table>
<p><small>Hub Système — © 2026 Mr-Aurevo-X — GPL-3.0-or-later</small></p>
</body></html>
"""


def export_report(path: str | Path, metrics: dict[str, Any] | None = None) -> Path:
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report_html(metrics), encoding="utf-8")
    return out


def default_report_path() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Documents" / f"hub-systeme-rapport-{stamp}.html"
