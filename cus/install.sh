#!/usr/bin/env bash
# =============================================================================
# CommonUserScripts (CUS) V2 — Safe Remote Installer & Bootstrapper
# Complies with AGENTS.md:
# 1. No blind pipes to bash; downloads completely before execution.
# 2. Verifies environment, Python 3 availability and dependencies.
# 3. Installs only the `cus/` subdirectory of the collection repo into
#    isolated directory ~/.local/share/cus.
# 4. Links entrypoint to ~/.local/bin/cus.
# =============================================================================

set -euo pipefail

REPO_URL="https://github.com/JXAB/CommonUserScripts.git"
REPO_SUBDIR="cus"
INSTALL_DIR="${HOME}/.local/share/cus"
BIN_DIR="${HOME}/.local/bin"
IS_EPHEMERAL=false
CUS_ARGS=()

# Parse arguments (only --ephemeral is consumed here; the rest is forwarded to cus.py)
for arg in "$@"; do
    case "$arg" in
        --ephemeral)
            IS_EPHEMERAL=true
            INSTALL_DIR=$(mktemp -d /tmp/cus-ephemeral-XXXXXX)
            ;;
        *)
            CUS_ARGS+=("$arg")
            ;;
    esac
done

echo -e "\033[36m"
echo "   _____ _    _  _____   __      ______  "
echo "  / ____| |  | |/ ____|  \\ \\    / /___ \\ "
echo " | |    | |  | | (___     \\ \\  / /  __) |"
echo " | |    | |  | |\\___ \\     \\ \\/ /  |__ < "
echo " | |____| |__| |____) |     \\  /   ___) |"
echo "  \\_____|\\____/|_____/       \\/   |____/ "
echo " Installing CommonUserScripts Engine..."
echo -e "\033[0m"

# 1. Check Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "\033[31m[错误] 未检测到 Python 3 运行时。\033[0m"
    echo "CUS V2 采用声明式类型引擎，请先安装 Python 3:"
    echo "  - Debian/Ubuntu: sudo apt update && sudo apt install -y python3 git"
    echo "  - RHEL/Fedora:   sudo dnf install -y python3 git"
    echo "  - Arch Linux:    sudo pacman -Sy python git"
    echo "  - macOS:         brew install python3 git"
    exit 1
fi

# 2. Fetch only the `cus/` subdirectory (git preferred, tarball fallback)
TMP_FETCH="$(mktemp -d /tmp/cus-fetch-XXXXXX)"
mkdir -p "${INSTALL_DIR}"
if command -v git >/dev/null 2>&1; then
    echo "[*] 正在克隆仓库到临时目录..."
    git clone --depth=1 "${REPO_URL}" "${TMP_FETCH}/repo"
    cp -r "${TMP_FETCH}/repo/${REPO_SUBDIR}/." "${INSTALL_DIR}/"
else
    echo -e "\033[33m[*] 未检测到 git，将使用 curl 下载归档压缩包...\033[0m"
    TAR_URL="https://github.com/JXAB/CommonUserScripts/archive/refs/heads/main.tar.gz"
    curl -fsSL "${TAR_URL}" -o "${TMP_FETCH}/repo.tar.gz"
    tar -xz -f "${TMP_FETCH}/repo.tar.gz" -C "${TMP_FETCH}"
    cp -r "${TMP_FETCH}/CommonUserScripts-main/${REPO_SUBDIR}/." "${INSTALL_DIR}/"
fi
rm -rf "${TMP_FETCH}"

# 3. Create CLI symlink if not ephemeral
if [ "$IS_EPHEMERAL" = false ]; then
    mkdir -p "${BIN_DIR}"
    ln -sf "${INSTALL_DIR}/cus.py" "${BIN_DIR}/cus"
    chmod +x "${INSTALL_DIR}/cus.py"

    # Check if BIN_DIR is in PATH
    if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
        echo -e "\033[33m[*] 提示: 请确保 ${BIN_DIR} 在您的环境变量 PATH 中。\033[0m"
        echo "可执行以下命令加入 PATH:"
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
    fi
    echo -e "\033[32m[✓] 安装成功！直接运行 'cus' 即可启动管理器。\033[0m\n"
fi

# 4. Execute immediately
if [ "$IS_EPHEMERAL" = true ]; then
    trap 'rm -rf "${INSTALL_DIR}"' EXIT
    python3 "${INSTALL_DIR}/cus.py" "${CUS_ARGS[@]}"
else
    python3 "${INSTALL_DIR}/cus.py" "${CUS_ARGS[@]}"
fi
