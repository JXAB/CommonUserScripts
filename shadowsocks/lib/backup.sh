#!/usr/bin/env bash
# backup.sh - 配置备份与恢复
# 依赖: common.sh
#
# 备份目录结构：
#   /root/ss_backup/20261014-213000-install/
#       ├── config.json            # 实际配置文件（按原名保存）
#       ├── shadowsocks-libev.service
#       └── meta.txt               # 时间、系统、来源路径、触发原因

# 用法: backup_config [原因标签]
# 多实例并存时会把所有配置一并备份，恢复时整体还原到各自原路径
backup_config() {
    local reason="${1:-manual}" stamp dest entries=() e conf svc n=0
    mapfile -t entries < <(list_installs)
    [[ ${#entries[@]} -gt 0 ]] || { warn "无配置文件可备份，跳过"; return 0; }

    stamp="$(date +%Y%m%d-%H%M%S)-${reason}"
    dest="${SS_BACKUP_DIR}/${stamp}"
    mkdir -p "${dest}"

    : >"${dest}/meta.txt"
    for e in "${entries[@]}"; do
        conf="${e%%:*}"; svc="${e##*:}"
        cp -a "${conf}" "${dest}/" 2>/dev/null || continue
        n=$((n + 1))
        printf 'source_config_%d=%s\nservice_%d=%s\n' "${n}" "${conf}" "${n}" "${svc}" \
            >>"${dest}/meta.txt"
        local unit="/etc/systemd/system/${svc}.service"
        [[ -f "${unit}" ]] && cp -a "${unit}" "${dest}/" 2>/dev/null || true
    done

    cat >>"${dest}/meta.txt" <<EOF
backup_time=$(date '+%F %T %z')
reason=${reason}
instances=${n}
os=$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME}")
kernel=$(uname -r)
EOF
    chmod -R 600 "${dest}"/* 2>/dev/null || true
    info "已备份 ${n} 个实例的配置到 ${dest}"
    prune_backups
}

# 仅保留最近 10 份备份，避免无限增长
prune_backups() {
    local keep=10 count
    [[ -d "${SS_BACKUP_DIR}" ]] || return 0
    count=$(find "${SS_BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d | wc -l)
    (( count > keep )) || return 0
    find "${SS_BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
        | sort -n | head -n "$(( count - keep ))" | cut -d' ' -f2- \
        | while read -r old; do rm -rf "${old}"; done
    info "已清理旧备份，保留最近 ${keep} 份"
}

list_backups() {
    [[ -d "${SS_BACKUP_DIR}" ]] || { warn "暂无备份目录 ${SS_BACKUP_DIR}"; return 1; }
    local dirs=()
    mapfile -t dirs < <(find "${SS_BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d | sort -r)
    [[ ${#dirs[@]} -gt 0 ]] || { warn "暂无备份记录"; return 1; }

    title "可用备份（共 ${#dirs[@]} 份）"
    local i=1 d
    for d in "${dirs[@]}"; do
        printf '  %2d) %s\n' "${i}" "$(basename "${d}")"
        i=$((i + 1))
    done
    printf '%s\n' "${dirs[@]}" >"${SS_BACKUP_DIR}/.index"
    return 0
}

restore_config() {
    list_backups || return 1
    local choice dirs=() src
    mapfile -t dirs < "${SS_BACKUP_DIR}/.index"

    choice=$(ask "请选择要恢复的编号" "1")
    [[ "${choice}" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#dirs[@]} )) \
        || die "编号不合法：${choice}"
    src="${dirs[$((choice - 1))]}"

    # 从 meta.txt 读回当时的全部实例路径，逐个还原
    local paths=()
    mapfile -t paths < <(grep -E '^source_config_[0-9]+=' "${src}/meta.txt" 2>/dev/null | cut -d= -f2-)
    # 兼容早期只记录单个实例的备份
    [[ ${#paths[@]} -gt 0 ]] || mapfile -t paths < <(grep -m1 '^source_config=' "${src}/meta.txt" 2>/dev/null | cut -d= -f2-)
    [[ ${#paths[@]} -gt 0 ]] || die "备份缺少 meta.txt 记录，无法确定还原位置"

    printf '将要还原 %d 个配置：\n' "${#paths[@]}"
    printf '  %s\n' "${paths[@]}"
    confirm "确认用 $(basename "${src}") 覆盖以上文件？" || { info "已取消"; return 0; }

    backup_config "before-restore"

    local conf base port
    for conf in "${paths[@]}"; do
        base=$(basename "${conf}")
        [[ -f "${src}/${base}" ]] || { warn "备份中缺少 ${base}，跳过"; continue; }
        mkdir -p "$(dirname "${conf}")"
        cp -a "${src}/${base}" "${conf}"
        chmod 600 "${conf}"
        info "已还原 ${conf}"
        port=$(json_get "${conf}" server_port)
        [[ -n "${port}" ]] && open_port "${port}"
    done

    # 还原后逐个重启对应服务
    local e
    while IFS= read -r e; do
        systemctl restart "${e##*:}" >/dev/null 2>&1 \
            && info "已重启 ${e##*:}" \
            || warn "重启 ${e##*:} 失败，请手工检查"
    done < <(list_installs)

    show_info
}
