# CommonUserScripts (CUS) V2

> 跨平台的 OS-Aware 全场景环境安装、开发运维、AI 工具链与服务调度引擎。

当前版本：M0 基础框架——已完成系统探测、安全拦截底座与六阶段调度引擎；各场景的真实安装逻辑随 M1~M5 逐步接入。

---

## ⚡ 快速一键使用

### 1. 安全一键安装（推荐）

在任意全新 Linux / macOS 机器上执行以下单行命令：

```bash
curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh -o /tmp/cus-install.sh && bash /tmp/cus-install.sh
```

安装后直接在任何目录输入 **`cus`** 即可调起交互菜单。

安装过程说明（不搞 `curl | bash`）：
- 先把 `install.sh` 完整下载到 `/tmp` 落盘，再执行，避免网络中断导致执行半截脚本；
- 只把仓库里 `cus/` 子目录的内容装到用户沙盒 `~/.local/share/cus`，不碰系统目录；
- 在 `~/.local/bin/cus` 创建软链接（需 `~/.local/bin` 在 `PATH` 中）；
- 随后自动调起交互菜单。

### 2. 即用即走模式（不驻留文件）

```bash
curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh -o /tmp/cus-run.sh && bash /tmp/cus-run.sh --ephemeral
```

运行在隔离临时目录中，执行完毕自动清理，不留任何文件。

### 3. 从源码运行

```bash
git clone https://github.com/JXAB/CommonUserScripts.git
cd CommonUserScripts/cus
./cus.sh status
```

---

## 🧰 环境要求

- Python 3.8+（`python3 --version` 可查）
- `git`（可选；没有 git 时自动改用 tarball 下载）
- Linux（Debian/Ubuntu、Fedora/RHEL、Arch、Alpine）或 macOS；Windows 探测已覆盖，安装引导待适配

---

## 🎯 覆盖的八大一键应用场景 (Profiles)

| 场景 ID | 场景名称 | 核心能力 |
|---|---|---|
| `vps-init` | **云服务器安全开荒** | 时区校准、BBR加速、核心运维包、SSH安全预检 |
| `ai-workstation` | **AI Agent 与开发工作站** | Python/uv、Node/fnm、Claude/Gemini/Codex CLI、MCP 生态 |
| `model-api-hub` | **轻量模型 API 网关** | CLIProxyAPI / Magpie 代理、systemd 服务化、端点自检 |
| `mobile-build` | **Android / Flutter 编译机**| JDK 17/21 矩阵、Android 命令行工具、免交互接受 Licenses、Flutter |
| `cloud-native` | **全栈容器与微服务** | Docker CE / Podman、Docker Compose、日志限额保护 |
| `mesh-network` | **私有互联与 Mesh 节点** | Tailscale、WireGuard、内核转发开启、防火墙自适应 |
| `daily-ops-cleaner` | **日常巡检与安全清理** | 健康体检、包缓存/日志预估分析、无损安全清理 |
| `git-ci-runner` | **Git 协作与 CI/CD 节点** | 全局 Git 配置规范、GitHub Actions Runner 快速部署 |

---

## 🛠 命令行参数用法 (CLI)

```bash
# 查看系统环境与底座状态
cus status
cus status --json

# 列出所有可用场景
cus profile list

# 预检模式执行场景（安全 dry-run，不写系统）
cus profile run vps-init

# 确认模式真实执行
cus profile run vps-init --apply

# 机器可读模式（供 CI / Agent 调用）
cus profile run ai-workstation --apply --json
```

注意：不加 `--apply` 时一律是 dry-run 预检，只规划、不写系统；真实执行必须显式加 `--apply`。

---

## 🔄 更新与卸载

```bash
# 更新到最新版：重新执行一键安装命令即可（覆盖程序文件）
curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/cus/install.sh -o /tmp/cus-install.sh && bash /tmp/cus-install.sh

# 卸载
rm -rf ~/.local/share/cus ~/.local/bin/cus
```

---

## 🧪 本地测试

```bash
python3 -m unittest discover -s tests/unit
```

M0 单元测试 10 项（系统探测、安全拦截、执行引擎），macOS 与 Debian 12 实测通过。

---

## 🛡️ 安全承诺与架构标准

本工具严格遵守 `AGENTS.md`：
- **拒绝黑盒执行**：所有动作经过 `Detect -> Plan -> Approve -> Apply -> Verify -> Report` 六阶段；
- **能力级验收**：严禁以“命令返回码 0”代表安装成功，执行真实的 `--version` 与端口端点探活；
- **最小特权**：普通操作无需 root，按需请求提权，绝不以 root 身份盲跑整个管理器；
- **隐私保护**：严格自动脱敏 Token、API Key 与密码。

详细架构见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，任务批次见 [docs/TASKS.md](docs/TASKS.md)，路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)。

---

## 📁 目录结构

```
cus/
├── cus.py                  # 跨平台 Python 主入口（status / profile / TUI）
├── cus.sh                  # POSIX Shell 引导脚本
├── install.sh              # 安全一键安装引导器
├── core/
│   ├── engine.py           # 六阶段生命周期调度器（--dry-run 保护）
│   ├── security.py         # L0~L4 权限审计、危险命令拦截、Secret 脱敏
│   └── platform/
│       └── os_detect.py    # 系统/架构/包管理器探测、容器与 WSL 识别
├── data/
│   ├── profiles.json       # 8 大一键场景编排
│   └── modules.json        # 原子模块检测、验证与风险分级
├── docs/                   # 架构、任务、路线图
└── tests/unit/             # 单元测试套件
```
