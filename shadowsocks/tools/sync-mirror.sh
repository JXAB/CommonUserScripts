#!/usr/bin/env bash
#
# sync-mirror.sh - 把 Teddysun 官方仓库的 shadowsocks-libev 包镜像到本仓库
#
# 目的：上游 dl.lamp.sh 一旦不可用（域名到期 / 账号问题 / 被墙），
#       install.sh 仍能从本仓库的镜像完成安装。
#
# 只镜像 shadowsocks-libev：
#   - 它是 repo 安装方式实际使用的包，每个约 150-200KB，全量镜像 ~3MB
#   - shadowsocks-rust 每个 7-13MB，全量 140MB+，不适合放进 git，且本脚本不装它
#   - 其余依赖（libbloom1/libcork16/libsodium23 等）均来自 Debian/Ubuntu 官方源，
#     不随上游消失
#
# 同时保存可审计的信任链：
#   dists/<codename>/InRelease  上游 GPG 签名的发行索引
#   dists/<codename>/Packages   包索引（含上游给出的 SHA256）
#   MANIFEST.txt                本镜像每个文件的 SHA256
#
# 用法: bash tools/sync-mirror.sh [codename ...]    不带参数则同步全部
#
set -euo pipefail

UPSTREAM="https://dl.lamp.sh/shadowsocks"
GPG_URL="${UPSTREAM}/DEB-GPG-KEY-Teddysun"
PKG="shadowsocks-libev"
ARCHES=(amd64 arm64)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIRROR="${ROOT}/mirror"
MANIFEST="${MIRROR}/MANIFEST.txt"

declare -A DISTRO_OF=(
    [buster]=debian [bullseye]=debian [bookworm]=debian [trixie]=debian
    [focal]=ubuntu  [jammy]=ubuntu    [noble]=ubuntu    [resolute]=ubuntu
)

CODENAMES=("$@")
[[ ${#CODENAMES[@]} -gt 0 ]] || CODENAMES=(buster bullseye bookworm trixie focal jammy noble resolute)

msg()  { printf '\e[32m[同步]\e[0m %s\n' "$*"; }
warn() { printf '\e[33m[跳过]\e[0m %s\n' "$*"; }
die()  { printf '\e[31m[错误]\e[0m %s\n' "$*" >&2; exit 1; }

command -v dpkg >/dev/null 2>&1 || die "需要 dpkg 来比较包版本"

mkdir -p "${MIRROR}"

# 公钥副本
msg "同步 GPG 公钥"
curl -fsSL --max-time 30 -o "${MIRROR}/DEB-GPG-KEY-Teddysun" "${GPG_URL}" \
    || die "公钥下载失败"

tmp_manifest=$(mktemp)
printf '# 由 tools/sync-mirror.sh 生成，请勿手工编辑\n' >"${tmp_manifest}"
printf '# 同步时间: %s\n' "$(date -u '+%F %T UTC')" >>"${tmp_manifest}"
printf '# 格式: codename|arch|package|version|sha256|相对路径\n' >>"${tmp_manifest}"

total=0
for codename in "${CODENAMES[@]}"; do
    distro="${DISTRO_OF[${codename}]:-}"
    [[ -n "${distro}" ]] || { warn "${codename}：未知发行版，跳过"; continue; }

    # 签名过的发行索引，供离线审计
    dists_dir="${MIRROR}/dists/${codename}"
    mkdir -p "${dists_dir}"
    curl -fsSL --max-time 30 -o "${dists_dir}/InRelease" \
        "${UPSTREAM}/${distro}/dists/${codename}/InRelease" 2>/dev/null \
        || warn "${codename}：InRelease 获取失败"

    for arch in "${ARCHES[@]}"; do
        pkgs_url="${UPSTREAM}/${distro}/dists/${codename}/main/binary-${arch}/Packages"
        pkgs_file="${dists_dir}/Packages-${arch}"

        # 必须直接落盘：用 $(curl) 取会丢掉文件末尾换行，
        # 存下来的索引就不再字节精确，InRelease 里的 SHA256 对不上，审计链断裂
        curl -fsSL --max-time 30 -o "${pkgs_file}" "${pkgs_url}" 2>/dev/null || {
            warn "${codename}/${arch}：Packages 获取失败"; continue; }

        # 取该包的最高版本及其 Filename / SHA256
        best_ver=""; best_file=""; best_sha=""
        while IFS='|' read -r v f s; do
            [[ -n "${v}" ]] || continue
            if [[ -z "${best_ver}" ]] || dpkg --compare-versions "${v}" gt "${best_ver}"; then
                best_ver="${v}"; best_file="${f}"; best_sha="${s}"
            fi
        done < <(awk -v pkg="${PKG}" '
            /^Package: /   { cur=$2 }
            /^Version: /   { if (cur==pkg) v=$2 }
            /^Filename: /  { if (cur==pkg) f=$2 }
            /^SHA256: /    { if (cur==pkg) s=$2 }
            /^$/           { if (cur==pkg && v!="") { print v "|" f "|" s; v=""; f=""; s="" } cur="" }
            END            { if (cur==pkg && v!="") print v "|" f "|" s }' "${pkgs_file}")

        [[ -n "${best_ver}" ]] || { warn "${codename}/${arch}：仓库中无 ${PKG}"; continue; }

        out_dir="${MIRROR}/${distro}/${codename}"
        out_file="${out_dir}/$(basename "${best_file}")"
        mkdir -p "${out_dir}"

        if [[ -f "${out_file}" ]] && [[ "$(sha256sum "${out_file}" | cut -d' ' -f1)" == "${best_sha}" ]]; then
            msg "${codename}/${arch} ${best_ver} 已是最新，跳过下载"
        else
            msg "下载 ${codename}/${arch} ${PKG} ${best_ver}"
            curl -fsSL --max-time 180 -o "${out_file}" "${UPSTREAM}/${distro}/${best_file}" \
                || { warn "${codename}/${arch}：deb 下载失败"; continue; }
            # 对照上游 Packages 中的 SHA256，确保镜像件未被篡改
            got=$(sha256sum "${out_file}" | cut -d' ' -f1)
            [[ "${got}" == "${best_sha}" ]] \
                || { rm -f "${out_file}"; die "${codename}/${arch}：SHA256 不匹配，上游期望 ${best_sha}，实际 ${got}"; }
        fi

        # 清理同目录下的旧版本，避免仓库无限膨胀
        find "${out_dir}" -name "${PKG}_*_${arch}.deb" ! -name "$(basename "${out_file}")" -delete 2>/dev/null || true

        printf '%s|%s|%s|%s|%s|%s\n' \
            "${codename}" "${arch}" "${PKG}" "${best_ver}" "${best_sha}" \
            "${distro}/${codename}/$(basename "${out_file}")" >>"${tmp_manifest}"
        total=$((total + 1))
    done
done

mv "${tmp_manifest}" "${MANIFEST}"
msg "完成，共 ${total} 个包，清单：${MANIFEST}"
du -sh "${MIRROR}"
