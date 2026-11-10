"""Read-only system resource sampling. Stdlib only.

Linux-first (/proc); honest N/A on any platform or file that cannot be
read. CPU and network share ONE short sampling window (t0 -> sleep 0.2s
-> t1) so the console never waits twice. No background threads, no
daemons, no network access, no secrets, no writes of any kind.
"""
from __future__ import annotations

import ctypes
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
    user/nice, so they are never added again. Any negative field means
    a corrupt counter: return None instead of a bogus number.
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
            if len(vals) < 5 or any(v < 0 for v in vals):
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
    """Usage between two samples. None on missing data, zero delta, or
    an impossible idle increment (idle delta > total delta)."""
    if t0 is None or t1 is None:
        return None
    dt, di = t1[0] - t0[0], t1[1] - t0[1]
    if dt <= 0 or di < 0 or di > dt:
        return None
    return max(0.0, min(100.0, (1.0 - di / dt) * 100.0))


# ------------------------------------------------- Windows (ctypes) ------
class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                ("dwHighDateTime", ctypes.c_uint32)]


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_uint32),
        ("dwMemoryLoad", ctypes.c_uint32),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _win_cpu_times() -> tuple[int, int] | None:
    """(total, idle) 100ns ticks from GetSystemTimes. The kernel time
    already includes idle, so total = kernel + user (never + idle)."""
    try:
        idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
        if not ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel),
                ctypes.byref(user)):
            return None

        def value(ft: _FileTime) -> int:
            return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)

        return value(kernel) + value(user), value(idle)
    except (AttributeError, OSError):
        return None


def _windows_cpu_sample(sample_seconds: float, sleep) -> float | None:
    first = _win_cpu_times()
    try:
        sleep(max(0.0, sample_seconds))
    except Exception:
        pass
    return cpu_percent(first, _win_cpu_times())


def _windows_memory() -> dict | None:
    """{total_kb, used_kb, percent} via GlobalMemoryStatusEx. Stdlib
    WinAPI only; no WMI/PowerShell."""
    try:
        obj = _MemoryStatusEx()
        obj.dwLength = ctypes.sizeof(obj)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(obj)):
            total = int(obj.ullTotalPhys)
            used = total - int(obj.ullAvailPhys)
            if total <= 0:
                return None
            return {"total_kb": total // 1024,
                    "used_kb": max(0, used // 1024),
                    "percent": max(0.0, min(100.0, used / total * 100.0))}
    except (AttributeError, OSError, ValueError):
        pass
    return None


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
    """Total only (sysctl hw.memsize). vm_stat's free/inactive pages
    are NOT a MemAvailable equivalent, so used/percent stay None
    (honest N/A) instead of a fabricated number."""
    try:
        run = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
            timeout=5)
        if run.returncode != 0:
            return None
        total = int(run.stdout.strip())
        return {"total_kb": total // 1024, "used_kb": None, "percent": None}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def memory(proc_root: str | Path = "/proc") -> dict | None:
    """Used = MemTotal - MemAvailable (never Total - MemFree).

    Platform dispatch is explicit: Linux reads /proc/meminfo, macOS
    reports total only (sysctl hw.memsize), Windows uses
    GlobalMemoryStatusEx, anything else is N/A. Unit tests exercise
    _memory_linux directly against a fake /proc tree.
    """
    if sys.platform == "darwin":
        return _memory_darwin()
    if sys.platform == "win32":
        return _windows_memory()
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


def _net_dev_ifaces(proc_root: str | Path = "/proc") -> list[str]:
    """Interface names present in /proc/net/dev (loopback included)."""
    text = _read_text(Path(proc_root) / "net" / "dev")
    if not text:
        return []
    names = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        name = line.split(":", 1)[0].strip()
        if name:
            names.append(name)
    return names


def _iface_operstate(name: str, sys_root: str | Path = "/sys") -> str | None:
    text = _read_text(Path(sys_root) / "class" / "net" / name / "operstate")
    return text.strip() if text else None


def pick_iface(proc_root: str | Path = "/proc",
               sys_root: str | Path = "/sys") -> str | None:
    """Default-route interface; without one, pick a single non-loopback
    interface deterministically: operstate 'up' first, then name order.
    Traffic volume is NOT a selection criterion. None when nothing is
    usable (show N/A). Interfaces are never summed: VPN encapsulation
    would double-count."""
    iface = default_iface(proc_root)
    if iface:
        return iface
    candidates = [n for n in _net_dev_ifaces(proc_root) if n != "lo"]
    if not candidates:
        return None

    def priority(name: str):
        return (0 if _iface_operstate(name, sys_root) == "up" else 1, name)

    return min(candidates, key=priority)


# -------------------------------------------------------------- Collect ----
def _rate(before: int, after: int, elapsed: float) -> float | None:
    """Bytes/second. A counter that went backwards (reset/wrap) is N/A,
    never clamped to 0."""
    if elapsed <= 0 or after < before:
        return None
    return (after - before) / elapsed


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
    if sys.platform == "win32":
        # Windows: GetSystemTimes pair over the same interval. There are
        # no /proc network counters, so network stays N/A; disk uses the
        # system drive (see disk()).
        out["cpu_percent"] = _windows_cpu_sample(interval, sleep)
        return out
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
                              "rx_bps": _rate(net0[1], net1[1], dt),
                              "tx_bps": _rate(net0[2], net1[2], dt)}
        else:
            out["network"] = {"iface": net0[0], "rx_bps": None,
                              "tx_bps": None}
    return out
