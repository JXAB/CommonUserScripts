# CURRENT_CONTEXT — 交接状态

- 日期：2026-11-01
- 目标：CommonUserScripts V2 跨平台模块化脚本管理器
- 当前实现：v0.1.0-starter，非 v2.0 完成品。
- 50 个模块定义 / 8 个场景定义；其中 17 个为 `package`（原生包管理器可装，见 data/modules.json）、32 个仍为 `planned` 占位、1 个 `builtin`。
- 能执行的安装适配器：17 个 package 模块（base-cli、git、python、dev-jdk、dev-php、dev-db、dev-nginx、dev-toolchains、net-wireguard、net-dns、net-frp、agent-opencode、sys-monitor、ops-ports、ops-storage、ops-cloud、ops-backup-remote）使用 apt/dnf/pacman/brew，各模块实际支持的管理器见 data/modules.json（net-frp 仅 brew，agent-opencode 仅 pacman/brew），Windows winget 仅 git。实际系统安装从未在当前环境执行。
- 所有安装默认 plan；明确 `--apply` 才可能修改机器；非交互还需 `--yes`。
- 已验证：Linux Debian 13 x86_64 的 doctor、plan、version；Python compileall；5 项 unittest PASS；Shadowsocks 未实现安装被正确阻断 (exit 2)。
- 未验证：macOS、Windows、Termux 实际运行，包安装的真实成败，服务健康，SSH/防火墙变更，完整回滚。
- 优先下一批：docs/TASKS.md 的 M0 剩余和 M1：JSON Schema、跨 OS 平台验证、核心事务引擎、支持矩阵、准确包探测、TUI 路由。
- 只修改本项目目录；不要访问其它用户文件或做危险系统变更。
