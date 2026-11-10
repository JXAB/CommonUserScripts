"""Read-only system resource sampling. Stdlib only.

Linux-first (/proc); honest N/A on any platform or file that cannot be
read. CPU and network share ONE short sampling window (t0 -> sleep 0.2s
-> t1) so the console never waits twice. No background threads, no
daemons, no network access, no secrets, no writes of any kind.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SAMPLE_INTERVAL = 0.2  # seconds, shared by CPU and network sampling


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return None


# ---------------------------------------------------------------- CPU ----
def cpu_times(proc_root: str | Path = "/proc") -> tuple[int, int] | None:
    """Return (total, idle) jiffies from /proc/stat.

    idle includes iowait. guest/guest_nice are already counted inside
    user/nice, so they are never added again.
    """
    text = _read_text(Path(proc_root) / "stat")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("cpu "):
            parts = line.split()
            try:
                vals = [int(x) for x in parts[1:]]
            except ValueError:
                return None
            if len(vals) < 5:
                return None
            user, nice, system, idle, iowait = vals[0:5]
            irq = vals[5] if len(vals) > 5 else 0
            softirq = vals[6] if len(vals) > 6 else 0
            steal = vals[7] if len(vals) > 7 else 0
            total = user + nice + system + idle + iowait + irq + softirq + steal
            return total, idle + iowait
    return None


def cpu_percent(t0: tuple[int, int] | None,
                t1: tuple[int, int] | None) -> float | None:
    """Usage between two samples. None on missing data or zero delta."""
    if t0 is None or t1 is None:
        return None
    dt, di = t1[0] - t0[0], t1[1] - t0[1]
    if dt <= 0 or di < 0:
        return None
    return max(0.0, min(100.0, (1.0 - di / dt) * 100.0))


# -------------------------------------------------------------- Memory ----
def _memory_linux(proc_root: str | Path) -> dict | None:
    """{total_kb, used_kb, percent} from MemTotal/MemAvailable."""
    text = _read_text(Path(proc_root) / "meminfo")
    if not text:
        return None
    vals: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        fields = rest.strip().split()
        if fields:
            try:
                vals[key.strip()] = int(fields[0])
            except ValueError:
                pass
    total = vals.get("MemTotal")
    avail = vals.get("MemAvailable")
    if not total or avail is None:
        return None
    used = total - avail
    return {"total_kb": total, "used_kb": max(0, used),
            "percent": max(0.0, min(100.0, used / total * 100.0))}


def _memory_darwin() -> dict | None:
    """Best effort via sysctl + vm_stat; None on any failure."""
    try:
        total = int(subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
            timeout=5).stdout.strip())
        out = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=5).stdout
        page_size = 4096
        pages: dict[str, int] = {}
        for line in out.splitlines():
            if "page size of" in line:
                page_size = int(line.split("page size of")[1].split()[0])
            if ":" in line:
                key, rest = line.split(":", 1)
                pages[key.strip()] = int(rest.strip().split(".")[0])
        free = pages.get("Pages free", 0) + pages.get("Pages inactive", 0)
        avail = free * page_size
        used = total - avail
        return {"total_kb": total // 1024, "used_kb": max(0, used // 1024),
                "percent": max(0.0, min(100.0, used / total * 100.0))}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def memory(proc_root: str | Path = "/proc") -> dict | None:
    """Used = MemTotal - MemAvailable (never Total - MemFree).

    Platform dispatch is explicit: Linux reads /proc/meminfo, macOS uses
    sysctl/vm_stat, anything else is N/A. Unit tests exercise
    _memory_linux directly against a fake /proc tree.
    """
    if sys.platform == "darwin":
        return _memory_darwin()
    if sys.platform == "win32":
        return None
    return _memory_linux(proc_root)


# ---------------------------------------------------------------- Disk ----
def disk(path: str | None = None) -> dict | None:
    """{path, total, used, percent} for the root filesystem. No tree walk."""
    if path is None:
        path = "C:\\" if os.name == "nt" else "/"
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    if usage.total <= 0:
        return None
    used = usage.total - usage.free
    return {"path": path, "total": usage.total, "used": used,
            "percent": used / usage.total * 100.0}


# ------------------------------------------------------------- Network ----
def default_iface(proc_root: str | Path = "/proc") -> str | None:
    """Interface of the IPv4 default route (lowest metric), or None."""
    text = _read_text(Path(proc_root) / "net" / "route")
    if not text:
        return None
    best: tuple[int, str] | None = None
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 8:
            continue
        iface, dest, flags, metric = parts[0], parts[1], parts[3], parts[7]
        if dest != "00000000" or iface == "lo":
            continue
        try:
            flag_val, metric_val = int(flags, 16), int(metric)
        except ValueError:
            continue
        if not (flag_val & 0x1):  # RTF_UP
            continue
        if best is None or metric_val < best[0]:
            best = (metric_val, iface)
    return best[1] if best else None


def net_counters(proc_root: str | Path = "/proc",
                 iface: str | None = None) -> tuple[str, int, int] | None:
    """(iface, rx_bytes, tx_bytes) for the given (or default) interface."""
    if iface is None:
        iface = default_iface(proc_root)
    if not iface:
        return None
    text = _read_text(Path(proc_root) / "net" / "dev")
    if not text:
        return None
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        if name.strip() != iface:
            continue
        fields = rest.split()
        if len(fields) < 9:
            return None
        try:
            return iface, int(fields[0]), int(fields[8])
        except ValueError:
            return None
    return None


def pick_iface(proc_root: str | Path = "/proc") -> str | None:
    """Default-route interface; without one, the first non-lo interface
    that has carried traffic. None when nothing is usable (show N/A).
    Interfaces are never summed: VPN encapsulation would double-count."""
    iface = default_iface(proc_root)
    if iface:
        return iface
    text = _read_text(Path(proc_root) / "net" / "dev")
    if not text:
        return None
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        if name == "lo" or not name:
            continue
        fields = rest.split()
        if len(fields) < 9:
            continue
        try:
            rx, tx = int(fields[0]), int(fields[8])
        except ValueError:
            continue
        if rx > 0 or tx > 0:
            return name
    return None


# -------------------------------------------------------------- Collect ----
def collect(interval: float = SAMPLE_INTERVAL,
            proc_root: str | Path = "/proc",
            sleep=time.sleep,
            monotonic=time.monotonic) -> dict:
    """One shared sampling window. Never raises; every field is a value
    or None (rendered as N/A)."""
    out: dict = {"cpu_percent": None, "cpu_cores": None, "load1": None,
                 "memory": None, "disk": None,
                 "network": {"iface": None, "rx_bps": None, "tx_bps": None}}
    try:
        out["cpu_cores"] = os.cpu_count()
    except Exception:
        pass
    try:
        out["load1"] = os.getloadavg()[0]
    except (OSError, AttributeError):
        pass
    out["memory"] = memory(proc_root)
    out["disk"] = disk()
    cpu0 = cpu_times(proc_root)
    iface = pick_iface(proc_root)
    net0 = net_counters(proc_root, iface) if iface else None
    t0 = monotonic()
    if interval > 0:
        try:
            sleep(interval)
        except Exception:
            pass
    t1 = monotonic()
    out["cpu_percent"] = cpu_percent(cpu0, cpu_times(proc_root))
    if net0:
        net1 = net_counters(proc_root, net0[0])
        dt = t1 - t0
        if net1 and dt > 0:
            out["network"] = {"iface": net0[0],
                              "rx_bps": max(0.0, (net1[1] - net0[1]) / dt),
                              "tx_bps": max(0.0, (net1[2] - net0[2]) / dt)}
        else:
            out["network"] = {"iface": net0[0], "rx_bps": None,
                              "tx_bps": None}
    return out
