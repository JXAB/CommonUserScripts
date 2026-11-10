# CommonUserScripts

> **常用服务器一键脚本集合。**
>
> 把常用的服务器操作做成一键脚本：复制一条命令、粘贴回车就能跑，不用再翻文档拼参数。

![平台](https://img.shields.io/badge/平台-Linux%20%7C%20macOS-blue)
![脚本](https://img.shields.io/badge/脚本-2-green)

## 🗂️ 脚本目录

| # | 目录 | 是什么 | 适用系统 |
|---|------|--------|----------|
| 1 | [cus](cus/) | 🚀 CommonUserScripts V2 — 跨平台 OS-Aware 环境安装与调度引擎（8 大一键场景） | Linux / macOS |
| 2 | [shadowsocks](shadowsocks/) | 🔒 Shadowsocks 全功能一键安装与管理 | Debian 9–13、Ubuntu 18.04+、CentOS/RHEL 8+ |

## 🌳 仓库结构

```
CommonUserScripts/
├── cus/                    # 🚀 CUS V2 跨平台调度引擎（8 大场景）
│   ├── install.sh          # 一键安装入口
│   ├── cus.py              # 引擎入口（status / profile）
│   ├── cus.sh              # 快捷启动包装
│   ├── core/               # 六阶段调度引擎、安全拦截底座、系统探测
│   ├── data/               # 场景（profiles.json）与模块（modules.json）定义
│   ├── docs/               # 架构、路线图、任务清单
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

## 🚀 CUS V2 — 跨平台环境安装与调度引擎

跨平台的 OS-Aware 全场景环境安装、开发运维、AI 工具链与服务调度引擎。当前版本 M0（基础框架：系统探测、安全拦截底座、六阶段调度引擎已完成；各场景的真实安装逻辑随 M1~M5 逐步接入）。

**8 大一键场景**

| 场景 | 说明 |
|------|------|
| `vps-init` | 云服务器安全开荒：时区校准、BBR 加速、核心运维工具安装、基础安全巡检 |
| `ai-workstation` | AI Agent 与开发工作站：Python/uv 环境、Node/fnm、Claude/Gemini 等 |
| `model-api-hub` | 轻量模型 API 网关：CLIProxyAPI / Magpie 协议转换代理、systemd 守护服务 |
| `mobile-build` | Android / Flutter 编译机：JDK 17/21、Android 命令行工具链、自动签署 License |
| `cloud-native` | 全栈容器与微服务环境：Docker CE / Podman 引擎、Docker Compose 等 |
| `mesh-network` | 私有互联与 Mesh 节点：Tailscale / WireGuard 组网、内核转发、端口预检与防火墙 |
| `daily-ops-cleaner` | 日常巡检与安全清理：系统健康体检、包缓存 / journald 日志分析、无损安全清理 |
| `git-ci-runner` | Git 协作与 CI/CD 节点：Git 全局规范化配置、GitHub Actions 离线 Runner 部署等 |

**一键安装（推荐）**

```bash
curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh -o /tmp/cus-install.sh && bash /tmp/cus-install.sh
```

安装后在任意目录输入 `cus` 即可调起交互菜单。安装过程先把 `install.sh` 完整下载到 `/tmp` 落盘再执行（不搞 `curl | bash`），只把 `cus/` 装到 `~/.local/share/cus`，不碰系统目录。

**即用即走（不驻留文件）**

```bash
curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh -o /tmp/cus-run.sh && bash /tmp/cus-run.sh --ephemeral
```

**常用命令**

```bash
cus status              # 查看引擎与环境状态
cus profile list        # 列出 8 大场景
cus profile run <id>    # 执行指定场景（默认演练模式，加 --apply 真执行）
```

完整说明、测试与安全设计见 [cus/README.md](cus/README.md)。

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
