#!/usr/bin/env bash
# system.sh - 系统检测与包管理抽象
# 依赖: common.sh

OS_ID=""; OS_VER=""; OS_NAME=""; OS_CODENAME=""; INSTALL_MODE=""

# os-release 路径可注入，便于离线测试各发行版分支（默认读取真实系统）
SS_OS_RELEASE="${SS_OS_RELEASE:-/etc/os-release}"

# 安装方式优先级说明：
#   repo         Teddysun 官方 apt 仓库直装（Debian 10-13 / Ubuntu focal-resolute）
#                秒级完成、GPG 签名、可 apt 升级，是默认且推荐的方式
#   teddysun     调用上游 master 交互脚本（RHEL 系，或需要 rust / v2ray / xray 插件时）
#   legacy       调用固定在 commit dab9bec7 的旧版一键脚本（Debian 9 等仓库未覆盖的系统）
#   libev-source 本仓库源码编译，仅作最终兜底，需 --mode source 显式指定
detect_os() {
    [[ -r "${SS_OS_RELEASE}" ]] || die "无法读取 ${SS_OS_RELEASE}，系统不受支持"
    # shellcheck disable=SC1090
    . "${SS_OS_RELEASE}"
    OS_ID="${ID:-unknown}"
    OS_VER="${VERSION_ID:-0}"
    OS_NAME="${PRETTY_NAME:-${OS_ID} ${OS_VER}}"
    OS_CODENAME="${VERSION_CODENAME:-}"
    OS_VER="${OS_VER%%.*}"   # 22.04 -> 22

    case "${OS_ID}" in
        debian|ubuntu)
            # 以仓库实际提供的 codename 为准，而不是硬编码版本号
            if repo_supported; then
                INSTALL_MODE="repo"
            else
                INSTALL_MODE="legacy"
            fi
            ;;
        centos|rhel|rocky|almalinux|fedora)
            INSTALL_MODE="teddysun"
            ;;
        *)
            die "暂不支持的系统：${OS_NAME}"
            ;;
    esac

    # 允许显式覆盖：SS_FORCE_MODE=repo|teddysun|libev-source
    if [[ -n "${SS_FORCE_MODE:-}" ]]; then
        info "按指定方式安装：${SS_FORCE_MODE}（自动判定为 ${INSTALL_MODE}）"
        INSTALL_MODE="${SS_FORCE_MODE}"
    fi
    info "检测到系统：${OS_NAME}${OS_CODENAME:+ (${OS_CODENAME})}（安装方式：${INSTALL_MODE}）"
}

# Debian 9/10 已 EOL，官方源已下线，需切换到 archive.debian.org
fix_eol_apt_sources() {
    [[ "${OS_ID}" == "debian" && ( "${OS_VER}" == "9" || "${OS_VER}" == "10" ) ]] || return 0
    grep -q "archive.debian.org" /etc/apt/sources.list 2>/dev/null && {
        info "apt 源已指向 archive.debian.org，跳过"
        return 0
    }
    local codename="stretch"
    [[ "${OS_VER}" == "10" ]] && codename="buster"

    info "Debian ${OS_VER} 已停止维护，切换 apt 源到 archive.debian.org"
    cp -a /etc/apt/sources.list "/etc/apt/sources.list.bak.$(date +%Y%m%d%H%M%S)"
    cat >/etc/apt/sources.list <<EOF
deb http://archive.debian.org/debian/ ${codename} main contrib non-free
deb http://archive.debian.org/debian-security ${codename}/updates main contrib non-free
EOF
    echo 'Acquire::Check-Valid-Until "false";' >/etc/apt/apt.conf.d/99no-check-valid-until
}

pkg_update() {
    case "${OS_ID}" in
        debian|ubuntu) DEBIAN_FRONTEND=noninteractive apt-get update -qq ;;
        *)             command -v dnf >/dev/null && dnf -y makecache || yum -y makecache ;;
    esac
}

pkg_install() {
    [[ $# -gt 0 ]] || return 0
    info "安装依赖：$*"
    case "${OS_ID}" in
        debian|ubuntu)
            DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "$@" \
                || die "依赖安装失败：$*"
            ;;
        *)
            { command -v dnf >/dev/null && dnf -y install "$@"; } || yum -y install "$@" \
                || die "依赖安装失败：$*"
            ;;
    esac
}

# 内核参数优化（高并发代理场景），repo 与源码两种安装方式共用
tune_sysctl() {
    local conf="/etc/sysctl.d/99-shadowsocks.conf"
    cat >"${conf}" <<'EOF'
fs.file-max = 1000000
net.core.somaxconn = 4096
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.tcp_fastopen = 3
net.ipv4.tcp_fin_timeout = 30
net.ipv4.tcp_syncookies = 1
EOF
    sysctl --system >/dev/null 2>&1 || true
    info "已写入内核优化参数 ${conf}"
}
