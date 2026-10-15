#!/usr/bin/env bash
#
# os-detect-test.sh - 离线验证各发行版的安装方式选择分支
# 不安装任何东西，只喂入伪造的 os-release 检查 detect_os 的判定结果
#
# 用法: bash tests/os-detect-test.sh
#
set -uo pipefail

LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

# 期望矩阵: ID|VERSION_ID|VERSION_CODENAME|PRETTY_NAME|期望的 INSTALL_MODE
# repo 覆盖范围以 Teddysun 仓库实际提供的 dists 为准（buster/bullseye/bookworm/trixie,
# focal/jammy/noble/resolute），不在其中的 Debian/Ubuntu 回落到 legacy 一键脚本。
CASES=(
    "debian|9|stretch|Debian GNU/Linux 9 (stretch)|legacy"
    "debian|10|buster|Debian GNU/Linux 10 (buster)|repo"
    "debian|11|bullseye|Debian GNU/Linux 11 (bullseye)|repo"
    "debian|12|bookworm|Debian GNU/Linux 12 (bookworm)|repo"
    "debian|13|trixie|Debian GNU/Linux 13 (trixie)|repo"
    "debian|14|forky|Debian GNU/Linux 14 (forky)|legacy"
    "ubuntu|18.04|bionic|Ubuntu 18.04.6 LTS|legacy"
    "ubuntu|20.04|focal|Ubuntu 20.04.6 LTS|repo"
    "ubuntu|22.04|jammy|Ubuntu 22.04.4 LTS|repo"
    "ubuntu|24.04|noble|Ubuntu 24.04 LTS|repo"
    "centos|8||CentOS Stream 8|teddysun"
    "rocky|9||Rocky Linux 9.3|teddysun"
    "almalinux|9||AlmaLinux 9.3|teddysun"
)

# 在隔离子 shell 中跑一次判定，返回 INSTALL_MODE
run_detect() {
    (
        export SS_OS_RELEASE="${TMP}/os-release"
        # shellcheck disable=SC1091
        source "${LIB}/common.sh" >/dev/null 2>&1
        # shellcheck disable=SC1091
        source "${LIB}/repo.sh" >/dev/null 2>&1
        # shellcheck disable=SC1091
        source "${LIB}/system.sh" >/dev/null 2>&1
        detect_os >/dev/null 2>&1
        printf '%s' "${INSTALL_MODE}"
    )
}

pass=0; fail=0
printf '%-26s %-12s %-12s %s\n' "系统" "期望" "实际" "结果"
printf '%s\n' "----------------------------------------------------------------"

for c in "${CASES[@]}"; do
    IFS='|' read -r id ver codename pretty expect <<<"${c}"
    {
        printf 'ID=%s\nVERSION_ID="%s"\nPRETTY_NAME="%s"\n' "${id}" "${ver}" "${pretty}"
        [[ -n "${codename}" ]] && printf 'VERSION_CODENAME=%s\n' "${codename}"
    } >"${TMP}/os-release"

    actual=$(run_detect)
    if [[ "${actual}" == "${expect}" ]]; then
        printf '%-26s %-12s %-12s \e[32m通过\e[0m\n' "${id} ${ver}" "${expect}" "${actual}"
        pass=$((pass + 1))
    else
        printf '%-26s %-12s %-12s \e[31m失败\e[0m\n' "${id} ${ver}" "${expect}" "${actual:-空}"
        fail=$((fail + 1))
    fi
done

# --mode 覆盖：SS_FORCE_MODE 应当压过自动判定
printf 'ID=debian\nVERSION_ID="12"\nVERSION_CODENAME=bookworm\nPRETTY_NAME="Debian 12"\n' >"${TMP}/os-release"
forced=$(SS_FORCE_MODE=teddysun run_detect)
if [[ "${forced}" == "teddysun" ]]; then
    printf '%-26s %-12s %-12s \e[32m通过\e[0m\n' "debian 12 + 强制模式" "teddysun" "${forced}"
    pass=$((pass + 1))
else
    printf '%-26s %-12s %-12s \e[31m失败\e[0m\n' "debian 12 + 强制模式" "teddysun" "${forced:-空}"
    fail=$((fail + 1))
fi

# 不支持的系统应当直接报错退出（die 内部会 exit，需再套一层子 shell 捕获）
printf 'ID=alpine\nVERSION_ID="3.19"\nPRETTY_NAME="Alpine Linux v3.19"\n' >"${TMP}/os-release"
if [[ -z "$(run_detect)" ]]; then
    printf '%-26s %-12s %-12s \e[32m通过\e[0m\n' "alpine 3.19" "应拒绝" "rejected"
    pass=$((pass + 1))
else
    printf '%-26s %-12s %-12s \e[31m失败\e[0m\n' "alpine 3.19" "应拒绝" "未拒绝"
    fail=$((fail + 1))
fi

printf '\n通过 %d / 失败 %d\n' "${pass}" "${fail}"
[[ ${fail} -eq 0 ]]
