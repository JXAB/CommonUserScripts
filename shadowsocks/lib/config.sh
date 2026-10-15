#!/usr/bin/env bash
# config.sh - 配置读写、连接信息展示与服务管理
# 依赖: common.sh firewall.sh backup.sh
#
# 多实例原则：只读操作（info）展示全部；写操作（改端口/密码/加密、重启、恢复）
# 必须先经 select_install 明确目标，避免误改到另一个正在使用的节点。

# 用法: write_config <路径> <端口> <密码> <加密方式>
write_config() {
    local conf="${1}" port="${2}" password="${3}" method="${4}"
    mkdir -p "$(dirname "${conf}")"
    cat >"${conf}" <<EOF
{
    "server":["::0","0.0.0.0"],
    "server_port":${port},
    "password":"${password}",
    "timeout":300,
    "method":"${method}",
    "fast_open":false,
    "nameserver":"1.0.0.1",
    "mode":"tcp_and_udp"
}
EOF
    chmod 600 "${conf}"
    info "配置已写入 ${conf}"
}

# 用法: restart_service [服务名]，省略时取 SS_SEL_SVC
restart_service() {
    local svc="${1:-${SS_SEL_SVC:-}}"
    [[ -n "${svc}" ]] || { select_install; svc="${SS_SEL_SVC}"; }
    systemctl restart "${svc}" || die "重启失败：journalctl -u ${svc} -n 50"
    sleep 1
    systemctl is-active --quiet "${svc}" \
        && info "服务运行正常：${svc}" \
        || die "服务未运行：journalctl -u ${svc} -n 50"
}

service_ctl() {
    local action="${1}"
    select_install
    case "${action}" in
        status) systemctl status "${SS_SEL_SVC}" --no-pager ;;
        *)      systemctl "${action}" "${SS_SEL_SVC}" && info "服务已${action}：${SS_SEL_SVC}" ;;
    esac
}

# 打印单个实例的连接信息
print_instance_info() {
    local conf="${1}" svc="${2}" ipv4="${3}" ipv6="${4}"
    local port password method plugin state link
    port=$(json_get "${conf}" server_port)
    password=$(json_get "${conf}" password)
    method=$(json_get "${conf}" method)
    plugin=$(json_get "${conf}" plugin)
    state=$(systemctl is-active "${svc}" 2>/dev/null || echo "inactive")

    printf '  服务器 IPv4 : %s\n' "${ipv4:-未获取到}"
    [[ -n "${ipv6}" ]] && printf '  服务器 IPv6 : %s\n' "${ipv6}"
    printf '  端口        : %s\n' "${port}"
    printf '  密码        : %s\n' "${password}"
    printf '  加密方式    : %s\n' "${method}"
    [[ -n "${plugin}" ]] && printf '  插件        : %s %s\n' "${plugin}" "$(json_get "${conf}" plugin_opts)"
    printf '  配置文件    : %s\n' "${conf}"
    printf '  服务/状态   : %s / %s\n' "${svc}" "${state}"

    if [[ -n "${ipv4}" && -n "${port}" ]]; then
        link=$(ss_link "${method}" "${password}" "${ipv4}" "${port}")
        printf '\n  SS 链接     : %s\n' "${link}"
        if [[ -n "${plugin}" ]]; then
            warn "该节点启用了插件，上面的链接未包含 plugin 参数，客户端需手工填写"
        else
            print_qrcode "${link}"
        fi
    fi
    printf '\n'
}

show_info() {
    local entries=()
    mapfile -t entries < <(list_installs)
    [[ ${#entries[@]} -gt 0 ]] || die "未找到配置文件，Shadowsocks 可能尚未安装"

    local ipv4 ipv6
    ipv4=$(get_public_ipv4)
    ipv6=$(get_public_ipv6)

    local i=1 e
    for e in "${entries[@]}"; do
        if [[ ${#entries[@]} -gt 1 ]]; then
            title "Shadowsocks 连接信息（实例 ${i}/${#entries[@]}）"
        else
            title "Shadowsocks 连接信息"
        fi
        print_instance_info "${e%%:*}" "${e##*:}" "${ipv4}" "${ipv6}"
        i=$((i + 1))
    done
    printf '  BBR         : %s\n\n' "$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || echo 未知)"
}

change_password() {
    select_install
    local new
    new=$(ask "为 ${SS_SEL_SVC}(端口 $(json_get "${SS_SEL_CONF}" server_port)) 设置新密码（回车随机）" "$(random_password)")
    backup_config "change-password"
    json_set "${SS_SEL_CONF}" password "${new}"
    restart_service "${SS_SEL_SVC}"
    info "密码已更新"
    print_instance_info "${SS_SEL_CONF}" "${SS_SEL_SVC}" "$(get_public_ipv4)" ""
}

change_port() {
    select_install
    local old new
    old=$(json_get "${SS_SEL_CONF}" server_port)
    new=$(ask "为 ${SS_SEL_SVC}(当前 ${old}) 设置新端口（回车随机）" "$(random_port)")

    [[ "${new}" =~ ^[0-9]+$ ]] && (( new > 0 && new < 65536 )) || die "端口不合法：${new}"
    [[ "${new}" != "${old}" ]] && port_in_use "${new}" && die "端口 ${new} 已被占用"

    backup_config "change-port"
    json_set "${SS_SEL_CONF}" server_port "${new}"
    open_port "${new}"
    [[ -n "${old}" && "${old}" != "${new}" ]] && close_port "${old}"
    restart_service "${SS_SEL_SVC}"
    info "端口已由 ${old} 更新为 ${new}"
    print_instance_info "${SS_SEL_CONF}" "${SS_SEL_SVC}" "$(get_public_ipv4)" ""
}

change_method() {
    select_install
    local new
    printf '可选加密方式：aes-256-gcm / aes-128-gcm / chacha20-ietf-poly1305\n'
    new=$(ask "为 ${SS_SEL_SVC} 设置加密方式" "${SS_DEFAULT_METHOD}")
    case "${new}" in
        aes-256-gcm|aes-192-gcm|aes-128-gcm|chacha20-ietf-poly1305|xchacha20-ietf-poly1305) ;;
        *) die "不支持的加密方式：${new}" ;;
    esac
    backup_config "change-method"
    json_set "${SS_SEL_CONF}" method "${new}"
    restart_service "${SS_SEL_SVC}"
    info "加密方式已更新为 ${new}"
    print_instance_info "${SS_SEL_CONF}" "${SS_SEL_SVC}" "$(get_public_ipv4)" ""
}

view_log() {
    select_install
    journalctl -u "${SS_SEL_SVC}" -n 50 --no-pager
}
