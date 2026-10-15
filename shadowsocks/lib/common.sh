#!/usr/bin/env bash
# common.sh - 公共变量、输出与工具函数
# 单一职责：只提供基础设施，不做任何安装逻辑

# 防止重复 source 导致 readonly 变量报错
[[ -n "${SS_COMMON_LOADED:-}" ]] && return 0
SS_COMMON_LOADED=1

# ---------- 路径常量 ----------
readonly SS_LIBEV_DIR="/etc/shadowsocks-libev"
readonly SS_LIBEV_CONF="${SS_LIBEV_DIR}/config.json"
readonly SS_TEDDY_LIBEV_CONF="/etc/shadowsocks/shadowsocks-libev-config.json"
readonly SS_TEDDY_RUST_CONF="/etc/shadowsocks/shadowsocks-rust-config.json"
readonly SS_BACKUP_DIR="/root/ss_backup"
readonly SS_LOG="/var/log/shadowsocks-install.log"
readonly SS_DEFAULT_METHOD="aes-256-gcm"
readonly SS_LIBEV_VERSION="3.3.5"

# ---------- 颜色 ----------
if [[ -t 1 ]]; then
    C_RED=$'\e[31m'; C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'
    C_BLUE=$'\e[36m'; C_BOLD=$'\e[1m'; C_OFF=$'\e[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_OFF=""
fi

# ---------- 输出 ----------
# 所有日志一律写 stderr：函数用 stdout 返回值（如路径、端口），
# 日志混进 stdout 会污染命令替换的结果。
log()  { printf '%s [%s] %s\n' "$(date '+%F %T')" "${1}" "${2}" >>"${SS_LOG}" 2>/dev/null || true; }
info() { printf '%s[信息]%s %s\n' "${C_GREEN}" "${C_OFF}" "$*" >&2; log INFO "$*"; }
warn() { printf '%s[警告]%s %s\n' "${C_YELLOW}" "${C_OFF}" "$*" >&2; log WARN "$*"; }
err()  { printf '%s[错误]%s %s\n' "${C_RED}" "${C_OFF}" "$*" >&2; log ERROR "$*"; }
die()  { err "$*"; exit 1; }
title(){ printf '\n%s==== %s ====%s\n' "${C_BOLD}${C_BLUE}" "$*" "${C_OFF}" >&2; }

# ---------- 前置检查 ----------
require_root() {
    [[ ${EUID} -eq 0 ]] || die "请使用 root 用户运行（sudo -i 后重试）"
}

require_cmd() {
    local c
    for c in "$@"; do
        command -v "${c}" >/dev/null 2>&1 || die "缺少命令：${c}"
    done
}

# 询问确认，默认否；SS_ASSUME_YES=1 时直接通过
confirm() {
    local prompt="${1} [y/N]: " reply
    [[ "${SS_ASSUME_YES:-0}" == "1" ]] && return 0
    read -r -p "${prompt}" reply </dev/tty || return 1
    [[ "${reply}" =~ ^[Yy]$ ]]
}

# 读取输入，带默认值；-y 或无终端时直接返回默认值
# 注意：本函数用于命令替换取值，提示语由 read -p 输出到 stderr，不会污染返回值
ask() {
    local prompt="${1}" default="${2}" reply
    if [[ "${SS_ASSUME_YES:-0}" == "1" ]] || [[ ! -e /dev/tty ]]; then
        printf '%s' "${default}"; return 0
    fi
    read -r -p "${prompt}[${default}]: " reply </dev/tty || reply=""
    printf '%s' "${reply:-${default}}"
}

# ---------- 随机参数 ----------
random_port() {
    local port
    while :; do
        port=$(shuf -i 10000-65000 -n 1)
        port_in_use "${port}" || { printf '%s' "${port}"; return 0; }
    done
}

port_in_use() {
    if command -v ss >/dev/null 2>&1; then
        ss -lntu 2>/dev/null | awk '{print $5}' | grep -qE "[:.]${1}\$"
    else
        netstat -lntu 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${1}\$"
    fi
}

random_password() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 18 | tr -d '\n/+=' | cut -c1-16
    else
        tr -dc 'A-Za-z0-9' </dev/urandom | head -c 16
    fi
}

# ---------- 网络信息 ----------
# 网络不可达时返回空串而非中断脚本（调用方运行在 set -e 下）
get_public_ipv4() {
    local ip api
    for api in "https://api.ipify.org" "https://ipv4.icanhazip.com" "https://ifconfig.me/ip"; do
        ip=$(curl -fsS4 --max-time 8 "${api}" 2>/dev/null | tr -d '[:space:]' || true)
        [[ "${ip}" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] && { printf '%s' "${ip}"; return 0; }
    done
    ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || true)
    printf '%s' "${ip}"
    return 0
}

get_public_ipv6() {
    local ip
    ip=$(curl -fsS6 --max-time 6 "https://ipv6.icanhazip.com" 2>/dev/null | tr -d '[:space:]' || true)
    printf '%s' "${ip}"
    return 0
}

# ---------- SS 链接 ----------
# 用法: ss_link <method> <password> <host> <port> [tag]
ss_link() {
    local method="${1}" password="${2}" host="${3}" port="${4}" tag="${5:-SS-${3}}"
    local userinfo
    userinfo=$(printf '%s:%s' "${method}" "${password}" \
        | base64 -w0 2>/dev/null || printf '%s:%s' "${method}" "${password}" | base64 | tr -d '\n')
    # 转为 URL-safe base64（RFC 4648 §5），去掉填充
    userinfo="${userinfo//+/-}"; userinfo="${userinfo//\//_}"; userinfo="${userinfo//=/}"
    [[ "${host}" == *:* ]] && host="[${host}]"
    printf 'ss://%s@%s:%s#%s' "${userinfo}" "${host}" "${port}" "${tag}"
}

print_qrcode() {
    command -v qrencode >/dev/null 2>&1 || return 0
    printf '\n二维码：\n'
    qrencode -t ANSIUTF8 -o - "${1}" 2>/dev/null || true
}

# ---------- JSON 读取（无 jq 依赖） ----------
# 用法: json_get <文件> <键>
json_get() {
    local file="${1}" key="${2}"
    [[ -r "${file}" ]] || return 1
    if command -v jq >/dev/null 2>&1; then
        jq -r --arg k "${key}" '.[$k] // empty' "${file}" 2>/dev/null
    else
        sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^\",}]*\)\"\{0,1\}.*/\1/p" \
            "${file}" | head -n1 | tr -d '[:space:]'
    fi
}

# 用法: json_set <文件> <键> <新值>（字符串与数字自动判定）
json_set() {
    local file="${1}" key="${2}" value="${3}"
    [[ -w "${file}" ]] || die "配置文件不可写：${file}"
    if [[ "${value}" =~ ^[0-9]+$ ]]; then
        sed -i "s|\"${key}\"[[:space:]]*:[[:space:]]*[^,}]*|\"${key}\":${value}|" "${file}"
    else
        sed -i "s|\"${key}\"[[:space:]]*:[[:space:]]*\"[^\"]*\"|\"${key}\":\"${value}\"|" "${file}"
    fi
}

# ---------- 服务与配置定位 ----------
# 已知的「配置文件:服务名」组合，覆盖四种安装来源：
#   源码编译 / legacy SysV → /etc/shadowsocks-libev/config.json + shadowsocks-libev
#   apt 仓库 / teddysun    → /etc/shadowsocks/shadowsocks-*-config.json + *-server
ss_install_map() {
    printf '%s\n' \
        "${SS_LIBEV_CONF}:shadowsocks-libev" \
        "${SS_TEDDY_LIBEV_CONF}:shadowsocks-libev-server" \
        "${SS_TEDDY_RUST_CONF}:shadowsocks-rust-server"
}

# 输出当前实际存在的全部实例，每行「配置文件:服务名」；一个都没有则返回 1
list_installs() {
    local entry conf found=1
    while IFS= read -r entry; do
        conf="${entry%%:*}"
        [[ -f "${conf}" ]] || continue
        printf '%s\n' "${entry}"
        found=0
    done < <(ss_install_map)
    return ${found}
}

# 选定要操作的实例，结果写入 SS_SEL_CONF / SS_SEL_SVC
# 多实例并存时必须明确指定，避免误改到另一个正在用的节点
select_install() {
    local entries=() pick="" e
    mapfile -t entries < <(list_installs)
    [[ ${#entries[@]} -gt 0 ]] || die "未检测到已安装的 Shadowsocks"

    if [[ ${#entries[@]} -eq 1 ]]; then
        pick="${entries[0]}"
    elif [[ -n "${SS_TARGET:-}" ]]; then
        # SS_TARGET 可以是端口号，也可以是配置文件完整路径
        for e in "${entries[@]}"; do
            if [[ "${e%%:*}" == "${SS_TARGET}" ]] \
               || [[ "$(json_get "${e%%:*}" server_port)" == "${SS_TARGET}" ]]; then
                pick="${e}"; break
            fi
        done
        [[ -n "${pick}" ]] || die "没有与 --target ${SS_TARGET} 匹配的实例"
    elif [[ "${SS_ASSUME_YES:-0}" == "1" || ! -e /dev/tty ]]; then
        err "检测到 ${#entries[@]} 个 Shadowsocks 实例，非交互模式下必须指定操作对象："
        print_installs >&2
        die "请加 --target <端口|配置文件路径>"
    else
        title "检测到多个 Shadowsocks 实例"
        print_installs
        local n
        read -r -p "请选择要操作的实例 [1-${#entries[@]}]: " n </dev/tty || n=""
        [[ "${n}" =~ ^[0-9]+$ ]] && (( n >= 1 && n <= ${#entries[@]} )) \
            || die "选择不合法：${n}"
        pick="${entries[$((n - 1))]}"
    fi

    SS_SEL_CONF="${pick%%:*}"
    SS_SEL_SVC="${pick##*:}"
}

print_installs() {
    local i=1 e conf svc
    while IFS= read -r e; do
        conf="${e%%:*}"; svc="${e##*:}"
        printf '  %d) 端口 %-6s %-26s %-9s %s\n' \
            "${i}" "$(json_get "${conf}" server_port)" "${svc}" \
            "$(systemctl is-active "${svc}" 2>/dev/null || echo unknown)" "${conf}"
        i=$((i + 1))
    done < <(list_installs)
}

# 输出当前生效的配置文件路径；找不到返回 1（单实例场景的便捷入口）
detect_conf() {
    local e
    e=$(list_installs | head -n1) || return 1
    [[ -n "${e}" ]] || return 1
    printf '%s' "${e%%:*}"
}

# 输出当前已安装的服务名；找不到返回 1
# 注意：TeddySun/apt 包创建的单元名带 -server 后缀，本仓库源码安装为 shadowsocks-libev
detect_service() {
    local s
    for s in shadowsocks-libev-server shadowsocks-rust-server shadowsocks-libev shadowsocks-rust; do
        systemctl list-unit-files 2>/dev/null | grep -q "^${s}\.service" \
            && { printf '%s' "${s}"; return 0; }
    done
    return 1
}

is_installed() {
    list_installs >/dev/null 2>&1
}
