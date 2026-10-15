#!/usr/bin/env bash
# firewall.sh - 多防火墙兼容的端口放行/回收
# 依赖: common.sh

# 返回当前使用的防火墙：ufw / firewalld / iptables / none
detect_firewall() {
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qi "^Status: active"; then
        printf 'ufw'
    elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
        printf 'firewalld'
    elif command -v iptables >/dev/null 2>&1; then
        printf 'iptables'
    else
        printf 'none'
    fi
}

open_port() {
    local port="${1}" fw
    fw=$(detect_firewall)
    case "${fw}" in
        ufw)
            ufw allow "${port}/tcp" >/dev/null 2>&1
            ufw allow "${port}/udp" >/dev/null 2>&1
            info "ufw 已放行端口 ${port} (tcp/udp)"
            ;;
        firewalld)
            firewall-cmd --permanent --add-port="${port}/tcp" >/dev/null 2>&1
            firewall-cmd --permanent --add-port="${port}/udp" >/dev/null 2>&1
            firewall-cmd --reload >/dev/null 2>&1
            info "firewalld 已放行端口 ${port} (tcp/udp)"
            ;;
        iptables)
            iptables -C INPUT -p tcp --dport "${port}" -j ACCEPT 2>/dev/null \
                || iptables -I INPUT -p tcp --dport "${port}" -j ACCEPT
            iptables -C INPUT -p udp --dport "${port}" -j ACCEPT 2>/dev/null \
                || iptables -I INPUT -p udp --dport "${port}" -j ACCEPT
            persist_iptables
            info "iptables 已放行端口 ${port} (tcp/udp)"
            ;;
        *)
            warn "未检测到防火墙，跳过端口放行"
            ;;
    esac
}

close_port() {
    local port="${1}" fw
    fw=$(detect_firewall)
    case "${fw}" in
        ufw)
            ufw delete allow "${port}/tcp" >/dev/null 2>&1
            ufw delete allow "${port}/udp" >/dev/null 2>&1
            ;;
        firewalld)
            firewall-cmd --permanent --remove-port="${port}/tcp" >/dev/null 2>&1
            firewall-cmd --permanent --remove-port="${port}/udp" >/dev/null 2>&1
            firewall-cmd --reload >/dev/null 2>&1
            ;;
        iptables)
            iptables -D INPUT -p tcp --dport "${port}" -j ACCEPT 2>/dev/null || true
            iptables -D INPUT -p udp --dport "${port}" -j ACCEPT 2>/dev/null || true
            persist_iptables
            ;;
    esac
    info "已回收端口 ${port} 的放行规则"
}

persist_iptables() {
    if command -v netfilter-persistent >/dev/null 2>&1; then
        netfilter-persistent save >/dev/null 2>&1 || true
    elif command -v iptables-save >/dev/null 2>&1 && [[ -d /etc/iptables ]]; then
        iptables-save >/etc/iptables/rules.v4 2>/dev/null || true
    fi
}
