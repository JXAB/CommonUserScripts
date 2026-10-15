#!/usr/bin/env bash
# repo.sh - 通过 Teddysun 官方 apt 仓库安装（Debian 10-13 / Ubuntu 20.04-25.x）
# 依赖: common.sh system.sh config.sh firewall.sh
#
# 相比源码编译与交互式脚本的优势：
#   - 秒级安装，无需编译依赖，低配机器不会 OOM
#   - GPG 签名验证，且后续可随 apt upgrade 升级
#   - Debian 10/11/12/13 与 Ubuntu 各版本行为完全一致，只有一条代码路径
#
# 仓库内容核实（2026-10-14）：
#   dists: buster bullseye bookworm trixie / focal jammy noble resolute
#   包    : shadowsocks-libev 3.3.5-12、shadowsocks-rust
#   包内  : /etc/shadowsocks/shadowsocks-libev-config.json
#           /lib/systemd/system/shadowsocks-libev-server.service

readonly TEDDY_REPO_BASE="https://dl.lamp.sh/shadowsocks"
readonly TEDDY_GPG_URL="${TEDDY_REPO_BASE}/DEB-GPG-KEY-Teddysun"
readonly TEDDY_GPG_FPR="8B22B39B30A0E20328FD16A5A930C227F704BE66"
readonly TEDDY_KEYRING="/usr/share/keyrings/deb-gpg-key-teddysun.gpg"
readonly TEDDY_LIST="/etc/apt/sources.list.d/teddysun.list"
readonly TEDDY_CONF="/etc/shadowsocks/shadowsocks-libev-config.json"
readonly TEDDY_SERVICE="shadowsocks-libev-server"

# 本仓库的镜像备份：上游 dl.lamp.sh 不可用时从这里安装
# 由 tools/sync-mirror.sh 同步，内含 shadowsocks-libev 的 deb 与 SHA256 清单
readonly SS_MIRROR_BASE="https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks/mirror"

# 仓库实际提供的发行版代号
readonly TEDDY_CODENAMES="buster bullseye bookworm trixie focal jammy noble resolute"

repo_supported() {
    [[ -n "${OS_CODENAME}" ]] || return 1
    # shellcheck disable=SC2086
    printf '%s\n' ${TEDDY_CODENAMES} | grep -qx "${OS_CODENAME}"
}

# 导入并校验 GPG 公钥：指纹不符或下载失败返回非 0，由调用方决定回退
repo_add_key() {
    local tmp
    tmp=$(mktemp)
    info "下载 Teddysun 仓库 GPG 公钥"
    if ! curl -fsSL --retry 2 --max-time 30 -o "${tmp}" "${TEDDY_GPG_URL}"; then
        rm -f "${tmp}"; warn "GPG 公钥下载失败"; return 1
    fi

    local fpr
    fpr=$(gpg --show-keys --with-colons "${tmp}" 2>/dev/null \
        | awk -F: '/^fpr:/{print $10; exit}')
    if [[ "${fpr}" != "${TEDDY_GPG_FPR}" ]]; then
        rm -f "${tmp}"
        die "GPG 公钥指纹不匹配！期望 ${TEDDY_GPG_FPR}，实际 ${fpr:-空}"
    fi
    info "公钥指纹校验通过：${fpr}"

    if ! gpg --dearmor --yes -o "${TEDDY_KEYRING}" "${tmp}" >/dev/null 2>&1; then
        rm -f "${tmp}"; warn "GPG 公钥转换失败"; return 1
    fi
    chmod a+r "${TEDDY_KEYRING}"
    rm -f "${tmp}"
}

repo_add_source() {
    local arch
    arch=$(dpkg --print-architecture)
    printf 'deb [arch=%s signed-by=%s] %s/%s/ %s main\n' \
        "${arch}" "${TEDDY_KEYRING}" "${TEDDY_REPO_BASE}" "${OS_ID}" "${OS_CODENAME}" \
        >"${TEDDY_LIST}"
    info "已添加软件源：${TEDDY_REPO_BASE}/${OS_ID}/ ${OS_CODENAME} main"
}

# 上游是否可达：用发行索引探测，比 ping 域名可靠
upstream_reachable() {
    curl -fsI --max-time 15 \
        "${TEDDY_REPO_BASE}/${OS_ID}/dists/${OS_CODENAME}/InRelease" >/dev/null 2>&1
}

# 从上游 apt 仓库安装；任一步失败返回非 0 由调用方回退，不直接终止
install_pkg_from_upstream() {
    repo_add_key   || return 1
    repo_add_source
    pkg_update     || return 1
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
        shadowsocks-libev || return 1
}

# ---------------------------------------------------------------------------
# 镜像回退：从本仓库备份的 deb 安装
# ---------------------------------------------------------------------------

# 读取清单。本地有仓库副本就用本地，否则从 GitHub 取
mirror_manifest() {
    if [[ -n "${SS_LOCAL_ROOT:-}" && -f "${SS_LOCAL_ROOT}/mirror/MANIFEST.txt" ]]; then
        cat "${SS_LOCAL_ROOT}/mirror/MANIFEST.txt"
    else
        curl -fsSL --retry 2 --max-time 30 "${SS_MIRROR_BASE}/MANIFEST.txt"
    fi
}

install_pkg_from_mirror() {
    local arch entry ver sha rel tmp got
    arch=$(dpkg --print-architecture)

    entry=$(mirror_manifest 2>/dev/null \
        | grep -v '^#' \
        | awk -F'|' -v c="${OS_CODENAME}" -v a="${arch}" \
              '$1==c && $2==a && $3=="shadowsocks-libev" {print; exit}') \
        || true
    [[ -n "${entry}" ]] \
        || die "镜像中没有 ${OS_CODENAME}/${arch} 的 shadowsocks-libev，请改用 --mode source"

    ver=$(printf '%s' "${entry}" | cut -d'|' -f4)
    sha=$(printf '%s' "${entry}" | cut -d'|' -f5)
    rel=$(printf '%s' "${entry}" | cut -d'|' -f6)

    tmp=$(mktemp -d)
    local deb="${tmp}/$(basename "${rel}")"

    if [[ -n "${SS_LOCAL_ROOT:-}" && -f "${SS_LOCAL_ROOT}/mirror/${rel}" ]]; then
        info "使用本地镜像：mirror/${rel}"
        cp "${SS_LOCAL_ROOT}/mirror/${rel}" "${deb}"
    else
        info "从本仓库镜像下载 ${ver}"
        curl -fsSL --retry 2 --max-time 120 -o "${deb}" "${SS_MIRROR_BASE}/${rel}" \
            || { rm -rf "${tmp}"; die "镜像下载失败：${SS_MIRROR_BASE}/${rel}"; }
    fi

    got=$(sha256sum "${deb}" | cut -d' ' -f1)
    [[ "${got}" == "${sha}" ]] \
        || { rm -rf "${tmp}"; die "镜像包 SHA256 不匹配！期望 ${sha}，实际 ${got}"; }
    info "SHA256 校验通过：${ver}"

    # 依赖全部来自发行版官方源，不受上游影响
    pkg_update || warn "apt update 有告警，继续尝试安装"
    if ! DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${deb}" >>"${SS_LOG}" 2>&1; then
        dpkg -i "${deb}" >>"${SS_LOG}" 2>&1 || true
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq -f >>"${SS_LOG}" 2>&1 \
            || { rm -rf "${tmp}"; die "依赖修复失败，详见 ${SS_LOG}"; }
    fi
    rm -rf "${tmp}"

    dpkg-query -W -f='${Status}' shadowsocks-libev 2>/dev/null | grep -q "install ok" \
        || die "镜像安装未成功，详见 ${SS_LOG}"
    info "已通过本仓库镜像安装 shadowsocks-libev ${ver}"
}

install_from_repo() {
    local port="${1}" password="${2}" method="${3}" ok=0

    title "安装 shadowsocks-libev（${OS_NAME}）"
    fix_eol_apt_sources
    pkg_update || warn "apt update 有告警，继续"
    pkg_install ca-certificates curl gnupg

    if upstream_reachable; then
        info "上游仓库可达，优先使用 ${TEDDY_REPO_BASE}"
        install_pkg_from_upstream && ok=1 || warn "上游安装失败，回退到本仓库镜像"
    else
        warn "上游仓库 ${TEDDY_REPO_BASE} 不可达，回退到本仓库镜像"
    fi
    [[ ${ok} -eq 1 ]] || install_pkg_from_mirror

    write_config "${TEDDY_CONF}" "${port}" "${password}" "${method}"
    tune_sysctl
    open_port "${port}"

    systemctl enable "${TEDDY_SERVICE}" >/dev/null 2>&1 || true
    systemctl restart "${TEDDY_SERVICE}" \
        || die "服务启动失败：journalctl -u ${TEDDY_SERVICE} -n 50"
    sleep 1
    systemctl is-active --quiet "${TEDDY_SERVICE}" \
        || die "服务未处于运行状态：journalctl -u ${TEDDY_SERVICE} -n 50"

    info "已安装 $(dpkg-query -W -f='${Version}' shadowsocks-libev 2>/dev/null)，服务 ${TEDDY_SERVICE} running"
}

uninstall_repo() {
    title "卸载 apt 仓库安装的 Shadowsocks"
    local svc
    for svc in shadowsocks-libev-server shadowsocks-rust-server; do
        systemctl disable --now "${svc}" >/dev/null 2>&1 || true
    done

    DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq shadowsocks-libev shadowsocks-rust \
        >>"${SS_LOG}" 2>&1 || warn "apt purge 未完全成功，详见 ${SS_LOG}"

    rm -f "${TEDDY_LIST}" "${TEDDY_KEYRING}"
    rm -rf /etc/shadowsocks
    rm -f /etc/sysctl.d/99-shadowsocks.conf
    systemctl daemon-reload
    info "已卸载并移除 Teddysun 软件源（备份保留在 ${SS_BACKUP_DIR}）"
}
