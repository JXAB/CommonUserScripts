#!/usr/bin/env sh
# ==============================================================================
# CommonUserScripts (CUS) V2 — Universal OS-Aware Bootstrap Loader
# Strictly follows AGENTS.md: No unverified curl|bash, privilege-aware.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check Python 3 environment
if command -v python3 >/dev/null 2>&1; then
    exec python3 "${SCRIPT_DIR}/cus.py" "$@"
fi

echo "[!] 未检测到 Python 3 运行时环境。"
echo "[*] CUS V2 执行引擎基于安全沙盒与类型状态机，需要 Python 3.8+ 支持。"
echo ""
echo "请使用系统官方包管理器安装 Python 3:"
echo "  - Debian / Ubuntu:  sudo apt update && sudo apt install -y python3"
echo "  - RHEL / Fedora:    sudo dnf install -y python3"
echo "  - Arch Linux:       sudo pacman -Sy python"
echo "  - macOS:            brew install python3"
echo ""
exit 1
