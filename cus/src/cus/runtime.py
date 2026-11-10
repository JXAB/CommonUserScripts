"""Cross-platform detection; no third-party dependencies."""
from __future__ import annotations
import os
import platform
import shutil
import sys
from pathlib import Path


def state_path() -> Path:
    """Where install events are recorded (read by doctor/history/console)."""
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "CommonUserScripts" / "events.jsonl"
    base = os.getenv("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "commonuserscripts" / "events.jsonl"


def detect() -> dict:
    system = platform.system().lower()
    os_id = system
    os_like = ""
    pretty = platform.platform()
    termux = bool(os.getenv("TERMUX_VERSION")) or "com.termux" in os.getenv("PREFIX", "")
    if system == "linux" and not termux:
        p = Path("/etc/os-release")
        if p.exists():
            d = {}
            for line in p.read_text(errors="replace").splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    d[k] = v.strip('"')
            os_id = d.get("ID", "linux")
            os_like = d.get("ID_LIKE", "")
            pretty = d.get("PRETTY_NAME", pretty)
    elif termux:
        os_id = "termux"
    manager = None
    if system == "windows":
        manager = "winget" if shutil.which("winget") else None
    elif system == "darwin":
        manager = "brew" if shutil.which("brew") else None
    elif termux:
        manager = None  # Termux is observation-only in the starter
    else:
        candidates = (("apt", {"debian", "ubuntu", "linuxmint", "pop"}),
                      ("dnf", {"fedora", "rhel", "rocky", "almalinux"}),
                      ("pacman", {"arch", "manjaro", "endeavouros"}))
        words = {os_id, *os_like.split()}
        for exe, families in candidates:
            if words.intersection(families) and shutil.which(exe):
                manager = exe
                break
    root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
    return {"system": system, "os_id": os_id, "os_pretty": pretty,
            "arch": platform.machine().lower(), "manager": manager,
            "is_root": root, "has_sudo": bool(shutil.which("sudo")),
            "python": platform.python_version(), "termux": termux}
