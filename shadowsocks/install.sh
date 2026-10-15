#!/usr/bin/env bash
#
# Shadowsocks 全功能一键安装脚本
# 仓库: https://github.com/JXAB/CommonUserScripts
# 适用: Debian 9/10/11/12/13、Ubuntu 18+、CentOS/RHEL 8+
#
# 一键命令:
#   bash <(curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks/install.sh)
#
# 子命令:
#   install | uninstall | reinstall | info | backup | restore
#   port | password | method | restart | status | log | bbr | menu
#
set -euo pipefail

readonly SS_REPO_RAW="https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks"
readonly SS_MODULES=(common.sh system.sh bbr.sh firewall.sh config.sh backup.sh repo.sh libev.sh teddysun.sh)

# ---------------------------------------------------------------------------
# 模块加载：本地仓库优先，远程一键执行时自动下载到临时目录
# ---------------------------------------------------------------------------
load_modules() {
    local self_dir lib_dir m
    self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"

    if [[ -n "${self_dir}" && -f "${self_dir}/lib/common.sh" ]]; then
        lib_dir="${self_dir}/lib"
        # 本地仓库副本：镜像文件可直接从磁盘取，无需联网
        export SS_LOCAL_ROOT="${self_dir}"
    else
        lib_dir="$(mktemp -d /tmp/ss-install.XXXXXX)"
        trap 'rm -rf "'"${lib_dir}"'"' EXIT
        echo "[信息] 远程模式，正在下载模块到 ${lib_dir}"
        for m in "${SS_MODULES[@]}"; do
            curl -fsSL --retry 2 --max-time 30 -o "${lib_dir}/${m}" "${SS_REPO_RAW}/lib/${m}" \
                || { echo "[错误] 下载 lib/${m} 失败" >&2; exit 1; }
        done
    fi

    for m in "${SS_MODULES[@]}"; do
        # shellcheck disable=SC1090
        source "${lib_dir}/${m}" || { echo "[错误] 加载 ${m} 失败" >&2; exit 1; }
    done
}
load_modules

# ---------------------------------------------------------------------------
# 安装流程
# ---------------------------------------------------------------------------
do_install() {
    local port="${OPT_PORT}" password="${OPT_PASSWORD}" method="${OPT_METHOD}"

    detect_os

    if is_installed; then
        warn "检测到已安装的 Shadowsocks"
        confirm "是否先备份并覆盖安装？" || { info "已取消"; return 0; }
        backup_config "before-reinstall"
    fi

    # 参数准备：未显式指定时交互询问，回车即用随机值
    [[ -n "${port}" ]]     || port=$(ask "请输入端口" "$(random_port)")
    [[ -n "${password}" ]] || password=$(ask "请输入密码" "$(random_password)")
    [[ -n "${method}" ]]   || method=$(ask "请输入加密方式" "${SS_DEFAULT_METHOD}")

    [[ "${port}" =~ ^[0-9]+$ ]] && (( port > 0 && port < 65536 )) || die "端口不合法：${port}"

    case "${INSTALL_MODE}" in
        repo)         install_from_repo "${port}" "${password}" "${method}" ;;
        legacy)       install_teddysun_legacy ;;
        teddysun)     install_teddysun ;;
        libev-source) install_libev_source "${port}" "${password}" "${method}" ;;
        *)            die "未知安装方式：${INSTALL_MODE}" ;;
    esac

    enable_bbr
    backup_config "after-install"
    show_info
    info "安装完成。再次运行本脚本可进入管理菜单。"
}

# 卸载方式以"实际装了什么"为准，而不是以系统版本推断。
# 入参为选定实例的配置文件路径，多实例并存时只拆掉选中的那一个。
resolve_uninstaller() {
    local conf="${1}"
    case "${conf}" in
        "${SS_TEDDY_LIBEV_CONF}"|"${SS_TEDDY_RUST_CONF}")
            if dpkg-query -W -f='${Status}' shadowsocks-libev 2>/dev/null | grep -q "install ok" \
               || dpkg-query -W -f='${Status}' shadowsocks-rust 2>/dev/null | grep -q "install ok"; then
                printf 'repo'
            else
                printf 'teddysun'
            fi
            ;;
        "${SS_LIBEV_CONF}")
            if [[ -f /etc/init.d/shadowsocks-libev ]]; then
                printf 'legacy'
            else
                printf 'libev-source'
            fi
            ;;
        *)  printf '%s' "${INSTALL_MODE}" ;;
    esac
}

do_uninstall() {
    detect_os
    is_installed || { warn "未检测到已安装的 Shadowsocks"; return 0; }
    select_install

    local kind
    kind=$(resolve_uninstaller "${SS_SEL_CONF}")
    warn "将卸载：${SS_SEL_SVC}（端口 $(json_get "${SS_SEL_CONF}" server_port)，方式 ${kind}）"
    confirm "确认卸载？配置会先自动备份" || { info "已取消"; return 0; }
    backup_config "before-uninstall"

    case "${kind}" in
        repo)                  uninstall_repo ;;
        libev-source|legacy)   uninstall_libev_source ;;
        teddysun)              uninstall_teddysun ;;
        *)                     die "无法判断卸载方式，请手工处理" ;;
    esac
    info "卸载完成，备份保留在 ${SS_BACKUP_DIR}"
}

do_reinstall() {
    detect_os
    backup_config "before-reinstall"
    if is_installed; then
        select_install
        case "$(resolve_uninstaller "${SS_SEL_CONF}")" in
            repo)                  uninstall_repo ;;
            libev-source|legacy)   uninstall_libev_source ;;
            teddysun)              uninstall_teddysun ;;
        esac
    fi
    do_install
}

# ---------------------------------------------------------------------------
# 交互菜单
# ---------------------------------------------------------------------------
show_menu() {
    local state="未安装"
    is_installed && state="已安装"

    cat <<EOF

${C_BOLD}${C_BLUE}============================================${C_OFF}
${C_BOLD}  Shadowsocks 一键管理脚本${C_OFF}
  仓库: JXAB/CommonUserScripts
  状态: ${state}
${C_BOLD}${C_BLUE}============================================${C_OFF}

   1) 安装 Shadowsocks
   2) 查看连接信息 / SS 链接
   3) 修改密码
   4) 修改端口
   5) 修改加密方式
   6) 重启服务
   7) 查看服务状态
   8) 查看运行日志
   9) 备份配置
  10) 恢复配置
  11) 开启 BBR 加速
  12) 重装（备份 → 卸载 → 安装）
  13) 卸载
   0) 退出

EOF
    local choice
    read -r -p "请选择 [0-13]: " choice </dev/tty || choice="0"
    case "${choice}" in
        1)  do_install ;;
        2)  show_info ;;
        3)  change_password ;;
        4)  change_port ;;
        5)  change_method ;;
        6)  restart_service ;;
        7)  service_ctl status ;;
        8)  view_log ;;
        9)  backup_config manual ;;
        10) restore_config ;;
        11) detect_os; enable_bbr ;;
        12) do_reinstall ;;
        13) do_uninstall ;;
        0)  exit 0 ;;
        *)  warn "无效选择：${choice}" ;;
    esac
}

usage() {
    cat <<EOF
用法: $(basename "${0}") [子命令] [选项]

子命令:
  menu           进入交互菜单（默认）
  install        安装 Shadowsocks
  uninstall      卸载
  reinstall      备份后重装
  info           查看连接信息与 ss:// 链接
  backup         备份当前配置
  restore        从备份恢复
  port           修改端口
  password       修改密码
  method         修改加密方式
  restart        重启服务
  status         查看服务状态
  log            查看最近 50 行日志
  bbr            检测并开启 BBR

选项（仅 install 有效）:
  --port <端口>         指定端口，默认随机
  --password <密码>     指定密码，默认随机
  --method <加密方式>    默认 ${SS_DEFAULT_METHOD}
  --mode <安装方式>      默认 auto，按系统自动选择，可选：
                          repo     Teddysun apt 仓库直装（Debian 10-13 / Ubuntu 20.04+）
                                   秒装、GPG 签名、可 apt upgrade 升级
                          teddysun 上游 master 交互脚本（需要 rust 或 v2ray/xray 插件时）
                          legacy   上游旧版一键脚本（固定 commit，Debian 9 等老系统）
                          source   本仓库源码编译（最终兜底）
  -y, --yes             全部确认，非交互安装

选项（管理类子命令）:
  --target <端口|配置路径>  多个实例并存时指定操作对象，例如 --target 34567
                           只有一个实例时无需指定

示例:
  bash install.sh install --port 12345 --method aes-256-gcm -y
  bash install.sh install --mode teddysun          # 需要 rust / 插件时
  bash install.sh password --target 34567          # 只改 34567 那个实例
  bash install.sh info
EOF
}

# ---------------------------------------------------------------------------
# 参数解析与入口
# ---------------------------------------------------------------------------
main() {
    require_root
    mkdir -p "$(dirname "${SS_LOG}")" "${SS_BACKUP_DIR}"
    touch "${SS_LOG}" 2>/dev/null || true

    OPT_PORT=""; OPT_PASSWORD=""; OPT_METHOD=""; OPT_MODE=""
    local cmd="${1:-menu}"
    [[ $# -gt 0 ]] && shift || true

    while [[ $# -gt 0 ]]; do
        case "${1}" in
            --port)     OPT_PORT="${2:-}"; shift 2 ;;
            --password) OPT_PASSWORD="${2:-}"; shift 2 ;;
            --method)   OPT_METHOD="${2:-}"; shift 2 ;;
            --mode)     OPT_MODE="${2:-}"; shift 2 ;;
            --target)   export SS_TARGET="${2:-}"; shift 2 ;;
            -y|--yes)   SS_ASSUME_YES=1; shift ;;
            -h|--help)  usage; exit 0 ;;
            *)          die "未知参数：${1}（-h 查看帮助）" ;;
        esac
    done
    export SS_ASSUME_YES="${SS_ASSUME_YES:-0}"

    case "${OPT_MODE}" in
        ""|auto)            ;;
        repo|teddysun|legacy) export SS_FORCE_MODE="${OPT_MODE}" ;;
        source)             export SS_FORCE_MODE="libev-source" ;;
        *)                  die "未知安装方式：${OPT_MODE}（可选 auto|repo|teddysun|legacy|source）" ;;
    esac

    case "${cmd}" in
        menu)               show_menu ;;
        install)            do_install ;;
        uninstall)          do_uninstall ;;
        reinstall)          do_reinstall ;;
        info)               show_info ;;
        backup)             backup_config manual ;;
        restore)            restore_config ;;
        port)               change_port ;;
        password)           change_password ;;
        method)             change_method ;;
        restart)            restart_service ;;
        status)             service_ctl status ;;
        log)                view_log ;;
        bbr)                detect_os; enable_bbr ;;
        -h|--help|help)     usage ;;
        *)                  die "未知子命令：${cmd}（-h 查看帮助）" ;;
    esac
}

main "$@"
