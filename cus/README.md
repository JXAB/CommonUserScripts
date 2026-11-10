# CommonUserScripts V2 — 跨平台脚本与环境管理中心

> 交付类型：**完整规划文档 + 可运行的安全 Starter（v2.1.0，含零依赖终端控制台）**。不要把目录里列出的所有模块当成已开发完成。

## 目标

把单机 Bash 一键脚本升级为跨平台、模块化、可扩展、可审计的系统工具箱：

- **One CLI, multiple adapters**：Linux/macOS/Windows 使用统一 CLI 和专用系统包管理器；Termux/WSL 单独识别。
- **One module, one responsibility**：每个工具有 detect/plan/install/verify/upgrade/remove/backup（后五项按阶段交付）。
- **Plan before apply**：默认只显示执行计划，不修改系统。
- **Profiles**：VPS、Python 后端、AI Agent、Android/Flutter、网络服务、Windows、macOS、维护等方案。
- **Evidence-oriented**：退出码、版本查询、健康检查、证据日志分离；不能以 `echo success` 作为交付。

## 当前 Starter 实现范围

已实现：

- 系统/发行版/架构/包管理器识别，诊断信息显示。
- JSON 模块目录（共 50 个规划模块）和 8 个场景组合。
- 支持查看、按场景生成计划、CLI 与简单交互菜单，包含 `0` / `q` 安全退出。
- Debian/Ubuntu `apt`、Fedora/RHEL 系 `dnf`、Arch 系 `pacman`、macOS `brew` 的 17 个 `package` 模块本机包安装适配（完整列表见 `data/modules.json`；各模块支持的管理器不同，如 `net-frp` 仅 brew、`agent-opencode` 仅 pacman/brew）；Windows `winget` 当前仅 `git`。
- **M1 安装适配器（2026-11-10）**：8 个模块真正可安装——`net-firewall`（ufw/firewalld/iptables，SSH 安全顺序）、`dev-node`（fnm + Node LTS，NodeSource 备选）、`ai-codex`/`ai-gemini`（npm）、`ai-claude`/`ai-grok`（官方安装器下载 + sha256 校验后执行）、`ai-zcf`（npx 直跑）、`backup`（restic 加密备份 + 保留策略）。设计见 `docs/ARCHITECTURE.md` §10；场景 `minimal-vps` 与 `ai-agent` 在 Debian 12 一次性容器里真实跑通过（154 项 unittest 全过）。
- 只有用户显式 `--apply` 且确认才会安装；非交互执行还须 `--yes`。
- 执行返回码日志，不记录密钥；对未实现的第三方脚本执行明确拒绝。
- Python `unittest` 基本验证。
- **终端控制台 CUS CONSOLE v2.1**：`cus` 进入循环多级菜单（场景 / 分类模块 / 详情 / 历史与设置），顶部 SYSTEM 仪表盘实时显示 OS、CPU、RAM、磁盘、网卡速率；`cus dashboard` 只读查看仪表盘，`cus dashboard --json` 输出纯 JSON。纯 Python 标准库，零第三方依赖，不启动后台进程。

**未实现**：Shadowsocks/CPA/Magpie 部署；Git 自动同步；清理、备份恢复演练；真正的系统级一键安装器；Windows 原生完整安装；Termux 安装；服务状态及 API 协议检测。这些在 docs/TASKS.md 和 docs/ROADMAP.md 里是开发任务，而非已有功能。

## 终端控制台（V2.1）

输入 `cus` 进入控制台（需终端；重定向输出时自动关闭颜色）：

- 主界面：SYSTEM 仪表盘（CPU 用 /proc/stat 两次采样、RAM 用 MemTotal−MemAvailable、磁盘用 shutil.disk_usage("/")、网卡用默认路由接口速率，缺失显示 N/A）+ WORKSPACE 菜单（7 组：场景部署、开发环境、AI Agent · API 网关、网络服务、容器 · 自动化、系统管理 · 维护、历史记录与设置）。
- 导航：`0`/`B` 返回、`R` 刷新、`H` 帮助、`Q` 退出、Enter 在主菜单退出、Ctrl+C 安全退出；无效输入提示后可重输。
- 场景详情：[P] 预览计划、[D] 检测状态、[B] 返回；模块详情只显示计划与真实 CLI 安装命令，不在菜单内执行安装。
- 布局自适应终端宽度（≥100 / 70–99 / 40–69 / <40 列四档），中文按显示宽度对齐；`CUS_ASCII=1` 强制纯 ASCII；非 TTY 时自动无色。
- 控制台不显示、不记录任何密码、密钥、订阅链接；`--apply` 仍是唯一的安装入口，且验证通过不等于安装成功。

## 运行（不联网、不修改系统）

先将本 ZIP 解压到本地：

```bash
cd CommonUserScripts-V2
python3 cus.py doctor
python3 cus.py list
python3 cus.py plan ai-agent
python3 cus.py --json plan android-builder
python3 cus.py show net-shadowsocks
python3 cus.py dashboard            # 只读仪表盘
python3 cus.py dashboard --json     # 纯 JSON 仪表盘
python3 cus.py install base-cli                 # 只看计划，不安装
python3 cus.py menu
```

Linux/macOS 快捷入口：`bash scripts/start.sh doctor`。Windows（需已有 Python 3）：`powershell -File scripts/start.ps1 doctor`。

安装 **已接入原生包管理器** 的模块：

```bash
python3 cus.py install base-cli --apply        # 交互确认后调用包管理器
python3 cus.py install git --apply --yes      # 明确跳过交互，谨慎用于自动化
```

**提醒**：本脚本尚无自动回滚与快照；即使是 apt 安装也属于系统变更。建议首先在新建测试 VPS/VM 上验证。Windows 和 macOS 的入口仅提供代码，尚未在真实机器上测试，不应声称平台验收通过。

## 一键安装

从 GitHub 安装管理器到本机（先完整下载再执行，不走 `curl|bash`）：

```bash
wget --no-check-certificate -O cus-install.sh https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh
chmod +x cus-install.sh
./cus-install.sh 2>&1 | tee cus-install.log
```

装完自动调起管理器；命令为 `cus`（安装目录 `~/.local/share/cus`，入口 `~/.local/bin/cus`）。临时试用、不留痕迹：

```bash
./cus-install.sh --ephemeral
```

没有 `wget` 的系统（macOS 默认无 wget），第一行改用 curl：

```bash
curl -fsSL -o cus-install.sh https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh
```

## 文档导航

- [产品完整规划](docs/PRD.md)
- [技术架构与模块协议](docs/ARCHITECTURE.md)
- [系统安全与 Agent 边界](AGENTS.md)
- [开发任务、验收证据](docs/TASKS.md)
- [分期发布计划](docs/ROADMAP.md)
- [原项目与官方安装资料](docs/SOURCES.md)
- [交给 Codex/Claude 的主 Prompt](AI_MASTER_PROMPT.md)

## 设计底线

不使用 `curl|bash`、`wget|sh` 当作默认执行通道；不关闭已有 SSH；不开放所有入站端口；不打印 API Key/Cookie；不误删宿主机缓存、Docker 数据卷、Git 变更；不将“未检查”当作“成功”。

版本日期：2026-11-10；控制台 v2.1.0；此目录为规划与 starter，不是生产就绪软件。
