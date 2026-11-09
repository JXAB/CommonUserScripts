"""
Operating System & Hardware Platform Detector.
Identifies Linux distributions, macOS, Windows, architectures, package managers, and privilege levels.
"""

from dataclasses import dataclass, asdict
from enum import Enum
import os
import platform
import shutil
import subprocess
from typing import Optional, Dict, Any


class PackageManager(str, Enum):
    APT = "apt"
    DNF = "dnf"
    PACMAN = "pacman"
    BREW = "brew"
    WINGET = "winget"
    APK = "apk"
    PKG = "pkg"  # Termux
    UNKNOWN = "unknown"


@dataclass
class OSInfo:
    system: str           # linux, darwin, windows, unknown
    distribution: str     # ubuntu, debian, fedora, arch, macos, win10, etc.
    version: str          # 24.04, 12, 14.5, etc.
    arch: str             # x86_64, aarch64, arm64, etc.
    pkg_manager: PackageManager
    is_root: bool
    is_wsl: bool
    is_container: bool

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["pkg_manager"] = self.pkg_manager.value
        return data


def _is_wsl() -> bool:
    if os.path.exists("/proc/version"):
        try:
            with open("/proc/version", "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
                return "microsoft" in content or "wsl" in content
        except Exception:
            return False
    return False


def _is_container() -> bool:
    if os.path.exists("/.dockerenv"):
        return True
    if os.path.exists("/run/.containerenv"):
        return True
    return False


def _parse_os_release() -> Dict[str, str]:
    data = {}
    if os.path.exists("/etc/os-release"):
        try:
            with open("/etc/os-release", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        data[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
    return data


def detect_system() -> OSInfo:
    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    distro = "unknown"
    version = ""
    pkg_mgr = PackageManager.UNKNOWN
    is_root = False

    # Check root privileges
    if hasattr(os, "geteuid"):
        is_root = (os.geteuid() == 0)
    else:
        # Windows check
        try:
            import ctypes
            is_root = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            is_root = False

    is_wsl_flag = False
    is_container_flag = False

    if sys_name == "linux":
        is_wsl_flag = _is_wsl()
        is_container_flag = _is_container()
        os_rel = _parse_os_release()
        distro = os_rel.get("ID", "linux").lower()
        version = os_rel.get("VERSION_ID", "")

        # Termux check
        if "PREFIX" in os.environ and "com.termux" in os.environ["PREFIX"]:
            distro = "termux"
            pkg_mgr = PackageManager.PKG
        elif distro in ["debian", "ubuntu", "kali", "linuxmint", "pop"]:
            pkg_mgr = PackageManager.APT
        elif distro in ["fedora", "rhel", "centos", "rocky", "almalinux"]:
            pkg_mgr = PackageManager.DNF
        elif distro in ["arch", "manjaro"]:
            pkg_mgr = PackageManager.PACMAN
        elif distro in ["alpine"]:
            pkg_mgr = PackageManager.APK
        else:
            # Fallback by binary lookup
            if shutil.which("apt-get"):
                pkg_mgr = PackageManager.APT
            elif shutil.which("dnf"):
                pkg_mgr = PackageManager.DNF
            elif shutil.which("pacman"):
                pkg_mgr = PackageManager.PACMAN

    elif sys_name == "darwin":
        distro = "macos"
        mac_ver = platform.mac_ver()[0]
        version = mac_ver if mac_ver else ""
        if shutil.which("brew"):
            pkg_mgr = PackageManager.BREW

    elif sys_name == "windows":
        distro = f"win{platform.release()}".lower()
        version = platform.version()
        if shutil.which("winget"):
            pkg_mgr = PackageManager.WINGET

    return OSInfo(
        system=sys_name,
        distribution=distro,
        version=version,
        arch=machine,
        pkg_manager=pkg_mgr,
        is_root=is_root,
        is_wsl=is_wsl_flag,
        is_container=is_container_flag,
    )
