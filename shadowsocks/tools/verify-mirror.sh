#!/usr/bin/env bash
#
# verify-mirror.sh - 校验本仓库镜像的完整信任链
#
# 验证三环：
#   1. 用镜像保存的公钥验证 dists/<codename>/InRelease 的 GPG 签名
#   2. InRelease 中声明的 Packages SHA256 == 镜像保存的 Packages 实际哈希
#   3. 每个 deb 的实际哈希 == MANIFEST 记录 == Packages 索引中上游给出的哈希
#
# 任何一环不通都说明镜像件与上游签名内容不符，不应继续使用。
#
# 用法: bash tools/verify-mirror.sh
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIRROR="${ROOT}/mirror"
MANIFEST="${MIRROR}/MANIFEST.txt"
KEY="${MIRROR}/DEB-GPG-KEY-Teddysun"

ok=0; bad=0
pass() { printf '  \e[32m✓\e[0m %s\n' "$*"; ok=$((ok + 1)); }
fail() { printf '  \e[31m✗\e[0m %s\n' "$*"; bad=$((bad + 1)); }

[[ -f "${MANIFEST}" ]] || { echo "缺少 ${MANIFEST}"; exit 1; }
[[ -f "${KEY}" ]]      || { echo "缺少 ${KEY}"; exit 1; }

GNUPGHOME=$(mktemp -d); export GNUPGHOME
trap 'rm -rf "${GNUPGHOME}"' EXIT
gpg --quiet --import "${KEY}" 2>/dev/null || { echo "公钥导入失败"; exit 1; }

printf '\n[1/3] InRelease GPG 签名\n'
for f in "${MIRROR}"/dists/*/InRelease; do
    [[ -f "${f}" ]] || continue
    cn=$(basename "$(dirname "${f}")")
    if gpg --quiet --verify "${f}" 2>&1 | grep -q "Good signature"; then
        pass "${cn}"
    else
        fail "${cn} 签名验证失败"
    fi
done

printf '\n[2/3] Packages 索引哈希与 InRelease 声明一致\n'
for f in "${MIRROR}"/dists/*/Packages-*; do
    [[ -f "${f}" ]] || continue
    cn=$(basename "$(dirname "${f}")")
    arch="${f##*Packages-}"
    rel="main/binary-${arch}/Packages"
    declared=$(awk -v t="${rel}" '
        /^SHA256:/ { s=1; next }
        /^[A-Za-z]/ { s=0 }
        s && $3==t { print $1; exit }' "${MIRROR}/dists/${cn}/InRelease")
    actual=$(sha256sum "${f}" | cut -d' ' -f1)
    if [[ -z "${declared}" ]]; then
        fail "${cn}/${arch} InRelease 中找不到 ${rel} 条目"
    elif [[ "${declared}" == "${actual}" ]]; then
        pass "${cn}/${arch}"
    else
        fail "${cn}/${arch} 哈希不符（索引可能已过期，请重新同步）"
    fi
done

printf '\n[3/3] deb 哈希与 MANIFEST、上游索引三方一致\n'
while IFS='|' read -r cn arch pkg ver sha rel; do
    [[ "${cn}" =~ ^# ]] && continue
    [[ -n "${cn:-}" ]] || continue
    deb="${MIRROR}/${rel}"
    if [[ ! -f "${deb}" ]]; then
        fail "${cn}/${arch} 缺少文件 ${rel}"; continue
    fi
    actual=$(sha256sum "${deb}" | cut -d' ' -f1)
    idx="${MIRROR}/dists/${cn}/Packages-${arch}"
    if [[ "${actual}" != "${sha}" ]]; then
        fail "${cn}/${arch} 与 MANIFEST 记录不符"
    elif [[ -f "${idx}" ]] && ! grep -q "${actual}" "${idx}"; then
        fail "${cn}/${arch} 哈希未出现在上游索引中"
    else
        pass "${cn}/${arch} ${pkg} ${ver}"
    fi
done <"${MANIFEST}"

printf '\n通过 %d / 失败 %d\n' "${ok}" "${bad}"
[[ ${bad} -eq 0 ]]
