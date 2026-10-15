#!/usr/bin/env bash
# bbr.sh - BBR 拥塞控制检测与开启
# 依赖: common.sh

bbr_enabled() {
    [[ "$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null)" == "bbr" ]]
}

bbr_supported() {
    # BBR 需要内核 >= 4.9
    local major minor
    major=$(uname -r | cut -d. -f1)
    minor=$(uname -r | cut -d. -f2)
    [[ "${major}" -gt 4 || ( "${major}" -eq 4 && "${minor}" -ge 9 ) ]]
}

enable_bbr() {
    if bbr_enabled; then
        info "BBR 已启用，跳过"
        return 0
    fi
    if ! bbr_supported; then
        warn "当前内核 $(uname -r) 不支持 BBR（需 >= 4.9），跳过"
        return 0
    fi

    info "开启 BBR 加速"
    modprobe tcp_bbr 2>/dev/null || true

    local conf="/etc/sysctl.d/99-bbr.conf"
    cat >"${conf}" <<'EOF'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF
    sysctl --system >/dev/null 2>&1 || sysctl -p "${conf}" >/dev/null 2>&1 || true

    if bbr_enabled; then
        info "BBR 已启用"
    else
        warn "BBR 配置已写入 ${conf}，重启后生效"
    fi
}
