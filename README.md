# CommonUserScripts

> **常用服务器一键脚本集合。**
>
> 把常用的服务器操作做成一键脚本：复制一条命令、粘贴回车就能跑，不用再翻文档拼参数。

![平台](https://img.shields.io/badge/平台-Linux%20%7C%20macOS-blue)
![脚本](https://img.shields.io/badge/脚本-2-green)

## 🗂️ 脚本目录

| # | 目录 | 是什么 | 适用系统 |
|---|------|--------|----------|
| 1 | [cus](cus/) | 🚀 CommonUserScripts V2 — 跨平台模块化脚本管理器（50 个模块 / 8 个场景） | Linux / macOS / Windows |
| 2 | [shadowsocks](shadowsocks/) | 🔒 Shadowsocks 全功能一键安装与管理 | Debian 9–13、Ubuntu 18.04+、CentOS/RHEL 8+ |

## 🌳 仓库结构

```
CommonUserScripts/
├── cus/                    # 🚀 CUS V2 跨平台模块化脚本管理器（50 模块 / 8 场景）
│   ├── install.sh          # 一键安装入口
│   ├── cus.py              # 入口（doctor / list / plan / install / menu）
│   ├── src/cus/            # catalog / cli / runtime（引擎）
│   ├── data/               # 模块（modules.json）与场景（profiles.json）定义
│   ├── docs/               # 架构、PRD、路线图、任务清单
│   ├── scripts/            # start.sh / start.ps1 启动器
│   └── tests/              # 单元测试
└── shadowsocks/            # 🔒 Shadowsocks 一键安装与管理
    ├── install.sh          # 一键安装 / 交互菜单
    ├── uninstall.sh        # 卸载
    ├── reinstall.sh        # 重装（备份 → 卸载 → 安装）
    ├── restore.sh          # 从备份恢复
    ├── backup.sh           # 配置备份
    ├── lib/                # BBR、防火墙、配置、仓库等模块
    ├── configs/            # 配置模板
    ├── docs/               # 安装方式对照、FAQ
    └── tests/              # 测试
```

每个目录下都有独立 README，含完整使用说明。下面是各脚本的简介和一键命令，所有命令都放在代码块里，点代码块右上角的复制按钮就能整条复制。

---

## 🚀 CUS V2 — 跨平台模块化脚本管理器

跨平台的模块化脚本管理器（v0.1.0-starter）：50 个模块定义、8 个场景，引擎按 `detect → plan → apply → verify` 执行，默认只做计划，明确 `--apply` 才改机器。

**模块状态**：17 个 `package` 模块可直接安装（Debian 12 上 15 个就绪；net-frp 仅 brew、agent-opencode 仅 pacman/brew）；32 个 `planned` 模块的备注里写清了安装方法与官方来源（AI CLI、网关、服务类需对应的适配器，见 `docs/TASKS.md` M3–M5）；1 个内置 `diagnostics`。

**8 大场景**

| 场景 | 说明 | 模块 |
|------|------|------|
| `minimal-vps` | 新 VPS 最小初始化 | base-cli、git、python、net-firewall、diagnostics |
| `backend-python` | Python 后端开发机 | base-cli、git、python、dev-node、docker、diagnostics |
| `ai-agent` | AI Agent 开发站 | base-cli、git、python、dev-node、ai-claude、ai-codex、ai-gemini、ai-grok、ai-zcf |
| `android-builder` | Android/Flutter 构建机 | base-cli、git、dev-jdk、dev-android、diagnostics |
| `proxy-host` | 代理及 AI API 服务器 | base-cli、net-shadowsocks、gateway-cpa、gateway-magpie、net-firewall、backup |
| `windows-dev` | Windows 本地开发机 | git、python、dev-node、ai-codex、ai-claude、diagnostics |
| `mac-dev` | macOS 开发机 | base-cli、git、python、dev-node、ai-codex、ai-claude、diagnostics |
| `maintenance` | 服务器安全维护 | diagnostics、cleanup-cache、backup、git-sync |

**一键安装（推荐）**

```bash
wget --no-check-certificate -O cus-install.sh https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh
chmod +x cus-install.sh
./cus-install.sh 2>&1 | tee cus-install.log
```

安装后在任意目录输入 `cus` 即可调起交互菜单。安装过程先把 `install.sh` 完整下载到当前目录落盘再执行（不搞 `curl | bash`），只把 `cus/` 装到 `~/.local/share/cus`，不碰系统目录。没有 `wget`（如 macOS）时，第一行改用 `curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh -o cus-install.sh`。

**即用即走（不驻留文件）**

```bash
wget --no-check-certificate -O cus-install.sh https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh
chmod +x cus-install.sh
./cus-install.sh --ephemeral 2>&1 | tee cus-install.log
```

**常用命令**

```bash
cus doctor            # 本机诊断（只读）
cus list              # 列出 50 个模块与状态
cus plan <profile>    # 查看场景的执行计划（不改机器）
cus show <module>     # 查看单个模块的计划
cus install <module> --apply    # 安装指定模块（需确认）
cus menu              # 交互菜单
```

完整说明、架构与任务清单见 [cus/README.md](cus/README.md)。

---

## 🔒 Shadowsocks 一键安装与管理

Shadowsocks 服务器的一键安装、管理、备份、重装、卸载全套脚本。

**能做什么**

- 自动判定安装方式：Debian 10–13 / Ubuntu 20.04+ 走 Teddysun 官方 apt 仓库（秒装、GPG 签名校验、可 `apt upgrade` 升级）；老系统自动回落上游一键脚本
- 默认 `aes-256-gcm`，自动随机端口与密码；自动开 BBR、放行防火墙、开机自启
- 装完直接输出 `ss://` 链接与终端二维码
- 交互菜单：改密码 / 端口 / 加密方式、重启、看状态 / 日志、备份 / 恢复、一键重装、卸载
- 每次变更前自动备份到 `/root/ss_backup`（仅保留最近 10 份）

**一键安装（交互菜单）**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks/install.sh)
```

**全自动静默安装**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks/install.sh) install -y
```

**无 curl 时的备用命令**

```bash
wget -qO- https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks/install.sh | bash
```

完整功能表、安装方式对照与常见问题见 [shadowsocks/README.md](shadowsocks/README.md)。

---

## 使用提示

- 所有命令都在代码块里：GitHub 会在代码块右上角显示复制按钮，点一下整条命令就复制好了，直接粘贴到终端回车即可。
- 建议先读各目录的 README 再执行，尤其是涉及系统服务的脚本。
- 想加新脚本：按现有目录结构放，并更新本页的脚本目录表。
