#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 not found. Install with your operating system package manager first.' >&2
  exit 2
fi
exec python3 "$root/cus.py" "$@"
