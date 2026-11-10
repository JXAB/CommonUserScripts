"""SYSTEM OVERVIEW rendering and the read-only text renderers shared by
the CLI and the console (doctor output, plan output).

This module renders; it never collects (menu.py / cli.py own sampling)
and never executes anything.
"""
from __future__ import annotations

import datetime
import getpass
import os
import re
import shlex
import shutil
from pathlib import Path

from .. import __version__
from ..runtime import state_path
from . import renderer as R
from .layout import display_width, pad, truncate
from .theme import threshold_style

# A resource bar is the only run of 8-10 block/hash/dash cells in a row.
_BAR_RE = re.compile(r"[█░]{8,10}|[#-]{8,10}")


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
                       unicode_mode: bool, counts=None) -> list[str]:
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
    ]
    if counts is not None:
        # 7-char "MODULES" would glue to its value with row()'s
        # 6-wide label field, so this row is spaced by hand.
        scenes = pad(truncate(f"  SCENES {counts[0]}", left_w), left_w)
        modules_n = truncate(f"MODULES {counts[1]}", right_w)
        lines.append(pad(scenes + modules_n, inner))
    lines += [
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
                    unicode_mode: bool, counts=None) -> list[str]:
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
    ]
    if counts is not None:
        lines.append(_kv("SCENES", f"{counts[0]} {g['mid']} MODULES "
                                   f"{counts[1]}", inner))
    lines += [
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
                    unicode_mode: bool, counts=None) -> list[str]:
    g = R.glyphs(unicode_mode)
    mem = snap.get("memory") or {}
    disk = snap.get("disk") or {}
    net = snap.get("network") or {}
    lines = [
        f"OS {host.get('os_pretty') or 'N/A'}",
    ]
    if counts is not None:
        lines.append(f"SCENES {counts[0]} {g['mid']} MODULES {counts[1]}")
    lines += [
        f"CPU {R.percent_text(snap.get('cpu_percent'))} {g['mid']} "
        f"RAM {R.percent_text(mem.get('percent'))} {g['mid']} "
        f"DISK {R.percent_text(disk.get('percent'))}",
        f"NET {net.get('iface') or 'N/A'}",
    ]
    return [pad(truncate(line, inner), inner) for line in lines]


def render_system(host: dict, snap: dict, inner: int,
                  unicode_mode: bool, theme=None, counts=None) -> list[str]:
    """SYSTEM section rows, each already padded to `inner` columns.
    counts is (scenes, modules); without it the SCENES/MODULES row is
    omitted. The rows are plain text: callers paint them after boxing
    (see paint_system_lines), so strip_controls cannot eat our colors."""
    if inner < 38:
        return _system_minimal(host, snap, inner, unicode_mode, counts)
    if inner < 66:
        return _system_compact(host, snap, inner, unicode_mode, counts)
    return _system_two_column(host, snap, inner, unicode_mode, counts)


# --------------------------------------------------------- page header -----
def render_header(inner: int, unicode_mode: bool) -> list[str]:
    """[title line, subtitle line] for the console header. Plain text:
    callers paint the spans after boxing (see paint_header_lines), so
    strip_controls in the layout path cannot eat our own ANSI codes."""
    g = R.glyphs(unicode_mode)
    title = "CUS Console"
    version = "v" + short_version()
    title_line = R.two_columns("  " + title, version, inner)
    subtitle = (f"  CommonUserScripts {g['mid']} "
                "Universal System Toolkit")
    return [pad(truncate(title_line, inner), inner),
            pad(truncate(subtitle, inner), inner)]


def paint_header_lines(lines: list[str], theme, unicode_mode: bool) -> list[str]:
    """Paint the header spans in already-boxed lines. Runs after layout
    (see render_header). A span that was truncated away is simply left
    unpainted; a disabled theme is a no-op."""
    if theme is None:
        return lines
    g = R.glyphs(unicode_mode)
    subtitle = f"CommonUserScripts {g['mid']} Universal System Toolkit"
    version = "v" + short_version()
    out = []
    for line in lines:
        line = line.replace("CUS", theme.heading("CUS"), 1)
        line = line.replace(" Console", theme.ok(" Console"), 1)
        line = line.replace(version, theme.dim(version), 1)
        line = line.replace(subtitle, theme.dim(subtitle), 1)
        out.append(line)
    return out


def paint_system_lines(lines: list[str], host: dict, snap: dict,
                       theme, unicode_mode: bool,
                       counts=None) -> list[str]:
    """Paint already-laid-out SYSTEM rows: labels gray, values bright
    white, resource bars and percents threshold-colored. Runs after
    boxing, like paint_header_lines. A disabled theme is a no-op.

    Painting is row-aware (leading label token decides which spans to
    paint), so a value is never colored by matching a substring of
    another row. The SCENES row paints label+value jointly: bare
    counts ("8", "50") are substrings of each other, so a plain
    sequential replace could nest one paint inside another."""
    if theme is None or not theme.enabled:
        return lines
    mem = snap.get("memory") or {}
    disk = snap.get("disk") or {}
    net = snap.get("network") or {}
    mem_used = ((mem.get("used_kb") or 0) * 1024
                if mem.get("used_kb") is not None else None)
    mem_total = ((mem.get("total_kb") or 0) * 1024
                 if mem.get("total_kb") is not None else None)
    cores = snap.get("cpu_cores")
    cores_text = str(cores) if cores is not None else "N/A"
    if snap.get("load1") is not None:
        cores_text += f"  LOAD {snap['load1']:.2f}"

    def paint(line: str, needle: str, style: str) -> str:
        if not needle:
            return line
        return line.replace(needle, theme.paint(needle, style), 1)

    def paint_bar_pct(line: str, percent) -> str:
        """Paint one resource row's bar run and percent text. The bar
        is painted only when this percent's text is actually in the
        line: the CPU row is also visited for the RAM/DISK percents
        (minimal layout packs all three on one line), and the bar
        regex would otherwise re-paint the CPU bar with the wrong
        row's color on every visit."""
        style = threshold_style(percent)
        if style is None or percent is None:
            return line
        pct = R.percent_text(percent)
        if pct not in line:
            return line
        m = _BAR_RE.search(line)
        if m:
            bar = m.group(0)
            line = line.replace(bar, theme.paint(bar, style), 1)
        return line.replace(pct, theme.paint(pct, style), 1)

    out = []
    for line in lines:
        stripped = line.lstrip("│|").lstrip()
        token = stripped.split(None, 1)[0] if stripped else ""
        if token == "OS":
            line = paint(line, "OS", "gray")
            line = paint(line, "ARCH", "gray")
            line = paint(line, host.get("os_pretty") or "N/A", "bold_white")
            line = paint(line, host.get("arch") or "N/A", "bold_white")
        elif token == "USER":
            line = paint(line, "USER", "gray")
            line = paint(line, "PKG", "gray")
            line = paint(line, current_user(), "bold_white")
            line = paint(line, host.get("manager") or "N/A", "bold_white")
        elif token == "SCENES":
            if counts is not None:
                line = line.replace(
                    f"SCENES {counts[0]}",
                    theme.paint("SCENES", "gray") + " "
                    + theme.paint(str(counts[0]), "bold_white"), 1)
                line = line.replace(
                    f"MODULES {counts[1]}",
                    theme.paint("MODULES", "gray") + " "
                    + theme.paint(str(counts[1]), "bold_white"), 1)
        elif token == "CPU":
            # Two-column CPU row, compact CPU row, and the minimal
            # combined "CPU .. · RAM .. · DISK .." row all start here.
            line = paint(line, "CPU", "gray")
            line = paint(line, "RAM", "gray")
            line = paint(line, "DISK", "gray")
            line = paint_bar_pct(line, snap.get("cpu_percent"))
            line = paint_bar_pct(line, mem.get("percent"))
            line = paint_bar_pct(line, disk.get("percent"))
            line = paint(line, "CORES", "gray")
            line = paint(line, cores_text, "bold_white")
            if cores is not None:
                line = paint(line, f"{cores} cores", "bold_white")
        elif token == "RAM":
            line = paint(line, "RAM", "gray")
            line = paint_bar_pct(line, mem.get("percent"))
            line = paint(line, R.format_pair(mem_used, mem_total),
                         "bold_white")
        elif token == "DISK":
            line = paint(line, "DISK", "gray")
            line = paint_bar_pct(line, disk.get("percent"))
            line = paint(line, R.format_pair(disk.get("used"),
                                             disk.get("total")),
                         "bold_white")
        elif token == "NET":
            line = paint(line, "NET", "gray")
            line = paint(line, "RX", "gray")
            line = paint(line, "TX", "gray")
            line = paint(line, net.get("iface") or "N/A", "bold_white")
            line = paint(line, R.format_rate(net.get("rx_bps")),
                         "bold_white")
            line = paint(line, R.format_rate(net.get("tx_bps")),
                         "bold_white")
        elif token == "TX":
            line = paint(line, "TX", "gray")
            line = paint(line, R.format_rate(net.get("tx_bps")),
                         "bold_white")
        out.append(line)
    return out


def render_dashboard_page(host: dict, snap: dict, width: int,
                          unicode_mode: bool, theme=None,
                          counts=None) -> list[str]:
    """Full `cus dashboard` page: header + SYSTEM section + hint.
    counts is (scenes, modules); without it the SCENES/MODULES row is
    omitted."""
    if width < 40:
        lines = ["CUS Console v" + short_version(),
                 "CommonUserScripts - Universal System Toolkit", ""]
        lines += paint_system_lines(
            render_system(host, snap, width, unicode_mode, theme, counts),
            host, snap, theme, unicode_mode, counts)
        lines.append("")
        lines.append("Run `cus` for the interactive console.")
        return lines
    box_w = max(38, min(width, 98))
    inner = box_w - 2
    lines = [R.box_top(box_w, unicode_mode)]
    header = [R.box_line(line, box_w, unicode_mode)
              for line in render_header(inner, unicode_mode)]
    lines += paint_header_lines(header, theme, unicode_mode)
    lines.append(R.section_rule(box_w, "SYSTEM", unicode_mode, theme))
    sys_lines = [R.box_line(row, box_w, unicode_mode)
                 for row in render_system(host, snap, inner, unicode_mode,
                                          theme, counts)]
    lines += paint_system_lines(sys_lines, host, snap, theme,
                                unicode_mode, counts)
    lines.append(R.box_bottom(box_w, unicode_mode))
    lines.append("")
    lines.append("Run `cus` for the interactive console.")
    return lines
