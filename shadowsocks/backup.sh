#!/usr/bin/env bash
# backup.sh - 备份配置（薄封装，实际逻辑在 install.sh，避免重复实现）
set -euo pipefail
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install.sh" backup "$@"
