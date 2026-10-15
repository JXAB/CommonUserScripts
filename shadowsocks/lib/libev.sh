#!/usr/bin/env bash
# libev.sh - Debian 9/10（EOL 系统）源码编译安装 shadowsocks-libev
# 依赖: common.sh system.sh config.sh firewall.sh

readonly SS_SRC_DIR="/usr/local/src"
readonly SS_BIN="/usr/local/bin/ss-server"
readonly SS_SERVICE_FILE="/etc/systemd/system/shadowsocks-libev.service"

libev_build_deps() {
    fix_eol_apt_sources
    pkg_update
    pkg_install ca-certificates curl wget xz-utils tar \
        build-essential autoconf automake libtool pkg-config gettext \
        libpcre3-dev zlib1g-dev libev-dev libc-ares-dev libsodium-dev libmbedtls-dev
}

libev_download() {
    local ver="${SS_LIBEV_VERSION}"
    local tarball="shadowsocks-libev-${ver}.tar.gz"
    local urls=(
        "https://github.com/shadowsocks/shadowsocks-libev/releases/download/v${ver}/${tarball}"
        "https://ghproxy.net/https://github.com/shadowsocks/shadowsocks-libev/releases/download/v${ver}/${tarball}"
    )
    mkdir -p "${SS_SRC_DIR}"
    cd "${SS_SRC_DIR}" || die "无法进入 ${SS_SRC_DIR}"

    if [[ -d "shadowsocks-libev-${ver}" ]]; then
        info "源码目录已存在，复用 ${SS_SRC_DIR}/shadowsocks-libev-${ver}"
        return 0
    fi

    local u
    for u in "${urls[@]}"; do
        info "下载源码：${u}"
        if curl -fsSL --retry 2 --max-time 180 -o "${tarball}" "${u}"; then
            tar -xzf "${tarball}" && return 0
            warn "解压失败，尝试下一个源"
        fi
    done
    die "shadowsocks-libev ${ver} 源码下载失败，请检查网络"
}

libev_compile() {
    local ver="${SS_LIBEV_VERSION}"
    cd "${SS_SRC_DIR}/shadowsocks-libev-${ver}" || die "源码目录缺失"
    info "开始编译 shadowsocks-libev ${ver}（约 1-3 分钟）"
    ./configure --disable-documentation >>"${SS_LOG}" 2>&1 \
        || die "configure 失败，详见 ${SS_LOG}"
    make -j"$(nproc)" >>"${SS_LOG}" 2>&1 \
        || die "make 失败，详见 ${SS_LOG}"
    make install >>"${SS_LOG}" 2>&1 \
        || die "make install 失败，详见 ${SS_LOG}"
    ldconfig
    [[ -x "${SS_BIN}" ]] || die "编译完成但未找到 ${SS_BIN}"
    info "编译安装完成：$(${SS_BIN} -h 2>&1 | head -n1)"
}

libev_write_service() {
    info "写入 systemd 服务单元"
    cat >"${SS_SERVICE_FILE}" <<EOF
[Unit]
Description=Shadowsocks-libev server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
LimitNOFILE=32768
ExecStart=${SS_BIN} -c ${SS_LIBEV_CONF} -u
Restart=on-failure
RestartSec=5
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable shadowsocks-libev >/dev/null 2>&1
}

# 主流程：仓库未覆盖的系统（如 Debian 9）源码安装
install_libev_source() {
    local port="${1}" password="${2}" method="${3}"

    title "源码编译安装 shadowsocks-libev ${SS_LIBEV_VERSION}（${OS_NAME}）"
    libev_build_deps
    libev_download
    libev_compile
    write_config "${SS_LIBEV_CONF}" "${port}" "${password}" "${method}"
    libev_write_service
    tune_sysctl
    open_port "${port}"

    systemctl restart shadowsocks-libev || die "服务启动失败：journalctl -u shadowsocks-libev -n 50"
    sleep 1
    systemctl is-active --quiet shadowsocks-libev \
        || die "服务未处于运行状态：journalctl -u shadowsocks-libev -n 50"
    info "shadowsocks-libev 已启动并设为开机自启"
}

# 本地安装的统一拆除逻辑，同时覆盖两种来源：
#   libev-source 本仓库编译 → systemd 单元 + /usr/local/bin
#   legacy       旧版 teddysun 脚本 → SysV init + /usr/local/bin（可能另被加过 systemd 单元）
# 不调用上游脚本的 uninstall，因为那是交互式的，无法无人值守执行。
uninstall_libev_source() {
    title "拆除本地安装的 shadowsocks-libev"

    # systemd 单元
    systemctl disable --now shadowsocks-libev >/dev/null 2>&1 || true
    rm -f "${SS_SERVICE_FILE}"
    systemctl daemon-reload >/dev/null 2>&1 || true

    # SysV init（旧版脚本安装的形态）
    if [[ -f /etc/init.d/shadowsocks-libev ]]; then
        /etc/init.d/shadowsocks-libev stop >/dev/null 2>&1 || true
        if command -v update-rc.d >/dev/null 2>&1; then
            update-rc.d -f shadowsocks-libev remove >/dev/null 2>&1 || true
        elif command -v chkconfig >/dev/null 2>&1; then
            chkconfig --del shadowsocks-libev >/dev/null 2>&1 || true
        fi
        rm -f /etc/init.d/shadowsocks-libev
        info "已移除 SysV init 脚本"
    fi

    # 若存在本仓库解压的源码目录，先走一遍 make uninstall
    local src="${SS_SRC_DIR}/shadowsocks-libev-${SS_LIBEV_VERSION}"
    [[ -d "${src}" ]] && { (cd "${src}" && make uninstall >>"${SS_LOG}" 2>&1) || true; }

    rm -f /usr/local/bin/ss-server /usr/local/bin/ss-local \
          /usr/local/bin/ss-tunnel /usr/local/bin/ss-redir /usr/local/bin/ss-manager
    rm -rf "${SS_LIBEV_DIR}"
    rm -f /etc/sysctl.d/99-shadowsocks.conf

    # 残留进程兜底：按进程名取候选，再用 /proc/<pid>/exe 核对真实可执行文件。
    # 不用 pkill -f，那会匹配到命令行里恰好含该路径的无关进程（包括调用者自己的 shell）。
    local pid
    for pid in $(pgrep -x ss-server 2>/dev/null || true); do
        if [[ "$(readlink -f "/proc/${pid}/exe" 2>/dev/null)" == "/usr/local/bin/ss-server" ]]; then
            kill "${pid}" 2>/dev/null || true
            info "已结束残留进程 PID ${pid}"
        fi
    done

    info "已拆除本地安装（备份保留在 ${SS_BACKUP_DIR}）"
}
