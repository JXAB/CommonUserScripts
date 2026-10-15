#!/usr/bin/env bash
# teddysun.sh - 调用 TeddySun 官方脚本安装
# 依赖: common.sh system.sh
#
# 两条路径：
#   current  master 版（2026-03-07 重写）：仓库安装 libev/rust + v2ray/xray 插件
#            系统要求 RHEL 8+ / Debian 11+ / Ubuntu 20.04+
#   legacy   固定在 commit dab9bec7（2022-06-20）：最后一个支持 Debian 7-10 的版本
#            内部自行编译 libsodium 1.0.18 + mbedtls 2.16.12（下载链接 2026-10-14 实测存活）
#            安装为 SysV init：/etc/init.d/shadowsocks-libev
#
# 固定 commit 而非使用第三方静态站点上的镜像副本（那类副本内容可能与本 commit 字节一致，
# 但来源不可信且可被随时替换），GitHub 的 commit URL 内容不可变。

readonly TEDDY_CURRENT_URL="https://raw.githubusercontent.com/teddysun/shadowsocks_install/master/shadowsocks-all.sh"
readonly TEDDY_LEGACY_COMMIT="dab9bec7"
readonly TEDDY_LEGACY_URL="https://raw.githubusercontent.com/teddysun/shadowsocks_install/${TEDDY_LEGACY_COMMIT}/shadowsocks-all.sh"
readonly TEDDY_WORKDIR="/usr/local/src/shadowsocks-teddysun"

# 用法: teddysun_fetch <current|legacy>
teddysun_fetch() {
    local kind="${1}" url name
    case "${kind}" in
        legacy) url="${TEDDY_LEGACY_URL}";  name="shadowsocks-all-legacy.sh" ;;
        *)      url="${TEDDY_CURRENT_URL}"; name="shadowsocks-all.sh" ;;
    esac

    mkdir -p "${TEDDY_WORKDIR}"
    info "下载官方脚本（${kind}）：${url}"
    curl -fsSL --retry 2 --max-time 60 -o "${TEDDY_WORKDIR}/${name}" "${url}" \
        || wget --no-check-certificate -q -O "${TEDDY_WORKDIR}/${name}" "${url}" \
        || die "TeddySun 脚本下载失败，请检查网络"
    [[ -s "${TEDDY_WORKDIR}/${name}" ]] || die "下载到的脚本为空"
    chmod +x "${TEDDY_WORKDIR}/${name}"
    printf '%s' "${TEDDY_WORKDIR}/${name}"
}

# 用法: teddysun_run <current|legacy> <install|uninstall>
teddysun_run() {
    local kind="${1}" action="${2}" script
    script=$(teddysun_fetch "${kind}")
    cd "${TEDDY_WORKDIR}" || die "工作目录缺失"
    "${script}" "${action}" 2>&1 | tee -a "${TEDDY_WORKDIR}/shadowsocks-all.log"
}

install_teddysun() {
    title "调用 TeddySun 官方脚本安装（${OS_NAME}）"
    pkg_update
    pkg_install ca-certificates curl wget

    cat <<'TIP'

即将进入官方交互式安装，建议选择：

  软件   : 1) Shadowsocks-libev（需要 rust 版则选 2）
  插件   : 1) None（需要伪装再选 v2ray-plugin / xray-plugin）
  加密   : aes-256-gcm
  端口   : 直接回车使用随机端口
  密码   : 直接回车使用随机密码

日志保存在 /usr/local/src/shadowsocks-teddysun/shadowsocks-all.log

TIP
    teddysun_run current install
    teddysun_post_install
}

install_teddysun_legacy() {
    title "调用 TeddySun 旧版一键脚本安装（commit ${TEDDY_LEGACY_COMMIT}，适配 ${OS_NAME}）"
    fix_eol_apt_sources
    pkg_update
    pkg_install ca-certificates curl wget

    cat <<'TIP'

该版本为 4-in-1 交互式脚本，建议选择：

  软件   : 4) Shadowsocks-libev（Python / R / Go 版均已停止维护，不建议选）
  加密   : aes-256-gcm
  端口   : 直接回车使用随机端口
  密码   : 直接回车使用随机密码

注意：该版本会现场编译 libsodium 与 mbedtls，低内存机器建议先加 swap。

TIP
    teddysun_run legacy install
    teddysun_post_install
}

# 安装后统一收尾：放行端口 + 内核优化
teddysun_post_install() {
    local conf port
    if conf=$(detect_conf); then
        port=$(json_get "${conf}" server_port)
        [[ -n "${port}" ]] && open_port "${port}"
        tune_sysctl
        info "安装完成，配置文件：${conf}"
    else
        warn "未检测到配置文件，请检查上方安装输出"
    fi
}

uninstall_teddysun() {
    title "卸载 TeddySun 脚本安装的 Shadowsocks"
    teddysun_run current uninstall
}
