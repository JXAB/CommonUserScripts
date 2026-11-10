"""SYSTEM OVERVIEW rendering and the read-only text renderers shared by
the CLI and the console (doctor output, plan output).

This module renders; it never collects (menu.py / cli.py own sampling)
and never executes anything.
"""
from __future__ import annotations

import datetime
import getpass
import os
import shlex
import shutil
from pathlib import Path

from .. import __version__
from ..runtime import state_path
from . import renderer as R
from .layout import display_width, pad, truncate


def short_version() -> str:
    return ".".join(__version__.split(".")[:2])


def current_user() -> str:
    try:
        return (os.environ.get("USER") or os.environ.get("USERNAME")
                or getpass.getuser())
    except Exception:
        return "N/A"


# ------------------------------------------------------------ JSON data ----
def dashboard_data(host: dict, snap: dict) -> dict:
    """Pure JSON shape for `cus dashboard --json`."""
    return {
        "host": {k: host.get(k) for k in
                 ("system", "os_id", "os_pretty", "arch", "manager",
                  "is_root", "has_sudo", "python")},
        "cpu": {"percent": snap.get("cpu_percent"),
                "cores": snap.get("cpu_cores"),
                "load1": snap.get("load1")},
        "memory": snap.get("memory"),
        "disk": snap.get("disk"),
        "network": snap.get("network"),
        "collected_at_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
    }


# ------------------------------------------------------- shared text -------
def format_plan(plan: dict) -> str:
    """The exact text form of one module plan (also used by the CLI)."""
    lines = [f"[{plan['id']}] {plan['name']} | {plan['status']}: "
             f"{plan['detail']}"]
    for cmd in plan["commands"]:
        lines.append("  planned command: " + shlex.join(cmd))
    if not plan["install_ready"]:
        lines.append("  not executable in this starter; see docs/ROADMAP.md")
    return "\n".join(lines)


def render_doctor(host: dict) -> list[str]:
    """Host diagnostics (read-only), one line per fact."""
    lines = ["CommonUserScripts host diagnostics (read-only)"]
    for key, value in host.items():
        lines.append(f"  {key:12} : {value}")
    try:
        free_gb = shutil.disk_usage(Path.home()).free / 1024 ** 3
        lines.append(f"  disk_free_gb : {free_gb:.1f}")
    except OSError:
        lines.append("  disk_free_gb : N/A")
    lines.append(f"  history      : {state_path()}")
    if not host.get("manager"):
        lines.append("  NOTE: no supported package adapter detected; "
                     "read-only mode.")
    return lines


# --------------------------------------------------------- SYSTEM rows -----
def _kv(label: str, value: str, width: int) -> str:
    return pad(truncate(f"  {label:<6}{value}", width), width)


def _system_two_column(host: dict, snap: dict, inner: int,
                       unicode_mode: bool) -> list[str]:
    left_w = inner // 2
    right_w = inner - left_w
    mem = snap.get("memory") or {}
    disk = snap.get("disk") or {}
    net = snap.get("network") or {}
    mem_used = ((mem.get("used_kb") or 0) * 1024
                if mem.get("used_kb") is not None else None)
    mem_total = ((mem.get("total_kb") or 0) * 1024
                 if mem.get("total_kb") is not None else None)
    disk_used = disk.get("used")
    disk_total = disk.get("total")

    def row(l_label, l_value, r_label, r_value):
        left = pad(truncate(f"  {l_label:<6}{l_value}", left_w), left_w)
        right = truncate(f"{r_label:<6}{r_value}" if r_label else r_value,
                         right_w)
        return pad(left + right, inner)

    cores = snap.get("cpu_cores")
    cores_text = str(cores) if cores is not None else "N/A"
    if snap.get("load1") is not None:
        cores_text += f"  LOAD {snap['load1']:.2f}"
    lines = [
        row("OS", host.get("os_pretty") or "N/A", "ARCH",
            host.get("arch") or "N/A"),
        row("USER", current_user(), "PKG", host.get("manager") or "N/A"),
        "",
        row("CPU", f"{R.progress_bar(snap.get('cpu_percent'), 10, unicode_mode)} "
                   f"{R.percent_text(snap.get('cpu_percent'))}",
            "CORES", cores_text),
        row("RAM", f"{R.progress_bar(mem.get('percent'), 10, unicode_mode)} "
                   f"{R.percent_text(mem.get('percent'))}",
            "", R.format_pair(mem_used, mem_total)),
        row("DISK", f"{R.progress_bar(disk.get('percent'), 10, unicode_mode)} "
                    f"{R.percent_text(disk.get('percent'))}",
            "", R.format_pair(disk_used, disk_total)),
        row("NET", net.get("iface") or "N/A", "RX",
            R.format_rate(net.get("rx_bps"))),
        row("", "", "TX", R.format_rate(net.get("tx_bps"))),
    ]
    return [pad(truncate(line, inner), inner) for line in lines]


def _system_compact(host: dict, snap: dict, inner: int,
                    unicode_mode: bool) -> list[str]:
    g = R.glyphs(unicode_mode)
    mem = snap.get("memory") or {}
    disk = snap.get("disk") or {}
    net = snap.get("network") or {}
    mem_used = ((mem.get("used_kb") or 0) * 1024
                if mem.get("used_kb") is not None else None)
    mem_total = ((mem.get("total_kb") or 0) * 1024
                if mem.get("total_kb") is not None else None)
    cores = snap.get("cpu_cores")
    cores_text = f" {g['mid']} {cores} cores" if cores is not None else ""
    lines = [
        _kv("OS", host.get("os_pretty") or "N/A", inner),
        _kv("USER", f"{current_user()} {g['mid']} PKG "
                    f"{host.get('manager') or 'N/A'}", inner),
        _kv("CPU", f"{R.progress_bar(snap.get('cpu_percent'), 8, unicode_mode)} "
                   f"{R.percent_text(snap.get('cpu_percent'))}{cores_text}",
            inner),
        _kv("RAM", f"{R.progress_bar(mem.get('percent'), 8, unicode_mode)} "
                   f"{R.percent_text(mem.get('percent'))} "
                   f"{R.format_pair(mem_used, mem_total)}", inner),
        _kv("DISK", f"{R.progress_bar(disk.get('percent'), 8, unicode_mode)} "
                    f"{R.percent_text(disk.get('percent'))} "
                    f"{R.format_pair(disk.get('used'), disk.get('total'))}",
            inner),
        _kv("NET", f"{net.get('iface') or 'N/A'} {g['mid']} RX "
                   f"{R.format_rate(net.get('rx_bps'))} {g['mid']} TX "
                   f"{R.format_rate(net.get('tx_bps'))}", inner),
    ]
    return lines


def _system_minimal(host: dict, snap: dict, inner: int,
                    unicode_mode: bool) -> list[str]:
    g = R.glyphs(unicode_mode)
    mem = snap.get("memory") or {}
    disk = snap.get("disk") or {}
    net = snap.get("network") or {}
    lines = [
        f"OS {host.get('os_pretty') or 'N/A'}",
        f"CPU {R.percent_text(snap.get('cpu_percent'))} {g['mid']} "
        f"RAM {R.percent_text(mem.get('percent'))} {g['mid']} "
        f"DISK {R.percent_text(disk.get('percent'))}",
        f"NET {net.get('iface') or 'N/A'}",
    ]
    return [pad(truncate(line, inner), inner) for line in lines]


def render_system(host: dict, snap: dict, inner: int,
                  unicode_mode: bool, theme=None) -> list[str]:
    """SYSTEM section rows, each already padded to `inner` columns."""
    if inner < 38:
        return _system_minimal(host, snap, inner, unicode_mode)
    if inner < 66:
        return _system_compact(host, snap, inner, unicode_mode)
    return _system_two_column(host, snap, inner, unicode_mode)


# --------------------------------------------------------- page header -----
def render_header(inner: int, unicode_mode: bool, theme=None) -> list[str]:
    """[title line, subtitle line] for the console header."""
    g = R.glyphs(unicode_mode)
    title = "CUS CONSOLE"
    version = "v" + short_version()
    if theme is not None:
        title = theme.title(title)
        version = theme.dim(version)
    title_line = R.two_columns("  " + title, version, inner)
    subtitle = (f"  CommonUserScripts {g['mid']} "
                "Universal System Toolkit")
    if theme is not None:
        subtitle = theme.dim(subtitle)
    return [pad(truncate(title_line, inner), inner),
            pad(truncate(subtitle, inner), inner)]


def render_dashboard_page(host: dict, snap: dict, width: int,
                          unicode_mode: bool, theme=None) -> list[str]:
    """Full `cus dashboard` page: header + SYSTEM section + hint."""
    if width < 40:
        lines = ["CUS CONSOLE v" + short_version(),
                 "CommonUserScripts - Universal System Toolkit", ""]
        lines += render_system(host, snap, width, unicode_mode, theme)
        lines.append("")
        lines.append("Run `cus` for the interactive console.")
        return lines
    box_w = max(38, min(width, 98))
    inner = box_w - 2
    lines = [R.box_top(box_w, unicode_mode)]
    for line in render_header(inner, unicode_mode, theme):
        lines.append(R.box_line(line, box_w, unicode_mode))
    lines.append(R.section_rule(box_w, "SYSTEM", unicode_mode, theme))
    for row in render_system(host, snap, inner, unicode_mode, theme):
        lines.append(R.box_line(row, box_w, unicode_mode))
    lines.append(R.box_bottom(box_w, unicode_mode))
    lines.append("")
    lines.append("Run `cus` for the interactive console.")
    return lines
