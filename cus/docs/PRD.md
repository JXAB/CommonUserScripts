# PRD — 全场景脚本与环境管理器

## 1. 产品边界

**定位**：本机优先的 OS-aware 环境安装、开发运维、脚本管理与故障排查工具，不是自动化越权工具，不是云服务器控制台或用户机配置的任意远程执行平台。

### 用户故事

1. 新 VPS：一条命令启动本机管理器；识别系统 → 只安装必要的软件 → 展示版本、端口与下一步。
2. Android 编译机：检测 Java、Gradle、ADB、SDK cmdline-tools、build-tools、licenses、Flutter/Dart、架构；按依赖安装与逐项验收。
3. AI 工具站：安装 Claude/Codex/Gemini/Grok/ZCF；帮助配置官方或自选兼容网关 URL，不碰账号密钥；核实 binary/version、API 能力和最小工具调用。
4. AI API 服务：CPA/Magpie 区分模式、选端口、备份配置、只监听 127.0.0.1 或需要时安全发布；验证 /v1/models 和真实请求、区分无权限/无余额/协议不支持。
5. 代理/VPN：将 Shadowsocks、WireGuard、Tailscale、ZeroTier、FRP 作为独立插件；预检端口与防火墙，展示配置归属，支持恢复。
6. 日常运维：发现磁盘空间不足，列举可清缓存和预估大小；用户勾选后执行，并提供前后数据。
7. Git：安全配置远程，fetch/status/diff；分支状态正常才允许 pull --ff-only；push 前二次确认。
8. 多机：同一场景 profile 可以导出离线清单，但每台机器独立执行，不默认跨 SSH 远程投递脚本。

## 2. 顶级菜单（目标正式版本）

00 退出（任何子菜单 0 返回，主菜单 0 退出）

01 系统总览 / 一键体检
02 新 VPS 初始化 / 基础软件
03 编程语言与工具链（Python/uv、Node/fnm、Go、Rust、PHP、JDK/Gradle、C/C++）
04 Android / Flutter / Java 开发环境
05 AI Agent CLI（Claude、Codex、Gemini、Grok、ZCF、OpenCode、MCP）
06 模型 API 网关（CLIProxyAPI、Magpie、服务健康、协议探测）
07 网络与代理（Shadowsocks、WireGuard、Tailscale、ZeroTier、FRP、DNS）
08 Docker / Podman / Compose / 常用应用模板
09 Git / SSH / GitHub Actions / 定时同步
10 服务器服务（Nginx、Caddy、PostgreSQL、Redis、systemd）
11 磁盘 / 包缓存 / 日志清理
12 监控 / 网络 / 端口 / 性能诊断
13 防火墙 / SSH / 账户 / 权限 / 备份恢复
14 一键场景部署（Profiles）
15 已安装应用管理（状态、配置、更新、卸载、日志）
16 脚本中心（搜索、收藏、第三方来源管理、锁定版本）
17 设置（语言、镜像、超时、代理、JSON、日志、安全等级）
18 任务历史 / 结果证据 / 导出报告
19 关于 / 更新管理器

### 统一子菜单约定

1 安装 / 2 查询状态 / 3 配置 / 4 启动 / 5 停止 / 6 重启 / 7 升级 / 8 卸载 / 9 日志 / 0 返回。
按软件的能力显示相应选项；如某工具没有 daemon 服务，不应出现启动、停止项。退出动作始终清晰可见。所有输入有超时/异常/空值处理和合法性校验。

## 3. 多系统兼容战略

| 环境 | 首版 | 目标 | 技术路径与限制 |
|---|---|---|---|
| Debian 12/13 | 核心首发 | 完整 | apt、systemd；WSL 要识别服务限制 |
| Ubuntu 22.04/24.04 | 核心首发 | 完整 | apt、systemd；遵守发行版生命周期 |
| Fedora / Rocky / AlmaLinux | 部分适配 | 完整 | dnf、SELinux、firewalld；须做实机验收 |
| Arch / Manjaro | 部分适配 | 完整 | pacman；滚动版本更需要预检 |
| macOS Intel / Apple Silicon | 入口可用，未实机验收 | 开发环境完整 | Homebrew、launchd、原生 app，server 插件单独限定 |
| Windows 10/11 | Python CLI 入口 + 少量 winget | 原生支持 | PowerShell、winget、任务计划程序/服务管理 |
| WSL2 | 计划支持 | 完整开发场景 | 根据 WSL/systemd/端口行为选择路径 |
| Android Termux | 识别、只读 | 基础工具与 AI CLI 部分支持 | pkg 与 bionic/架构限制，禁止套用 Debian 二进制 |
| Alpine / BusyBox / NAS | 不保证 | 研究支持 | musl、OpenRC、权限/容器限制 |
| Windows 7/8 | 不支持 | 不承诺 | 现代组件缺少维护与安全更新 |

系统支持分级：`verified`（实机 CI+验收）、`experimental`（可尝试、提供限制）、`read-only`（仅诊断）、`unsupported`（禁止安装）。支持状态应由 `os+version+arch+module` 矩阵决定，不是按发行版名称臆断。

## 4. 功能与优先级

### P0 必须交付
- 系统识别、权限状态、可用磁盘/内存、网络诊断、目录权限；交互菜单和 CLI 共用单一业务引擎。
- 原生包管理器安装、准确安装状态、幂等、超时、重试和中断。
- 所有动作有 detect -> plan -> approval -> apply -> verify -> report；错误码结构统一。
- `--dry-run` 默认、`--apply` 明确执行，`--json` 可被 Agent/CI 解析。
- 不同危险等级的许可门槛；变更前配置快照；已知安装文件的卸载清单。
- 至少 3 种场景；APT/Python/Git/基础工具真实完成闭环。

### P1 第二阶段
- JDK/Gradle/Android SDK/Flutter；Node/Go；Docker Compose；AI CLI。
- Git 同步与冲突处理、调度、磁盘清理预估、自动更新检测。
- AI API 网关、Shadowsocks 独立适配器，端口/认证/日志自检。
- backup/rollback 的管理器归属文件恢复能力，禁止虚构系统级回滚。

### P2 后续增强
- Web 可选面板（默认不启用对外服务）、加密异地备份、多机清单、TUI 搜索、离线缓存与镜像代理。
- 任务依赖图、重入锁、可续执行、导出 Markdown/JSON 报告、Metrics/Tracing。
- 沙盒中预跑外部脚本、签名校验、社区脚本市场（默认禁用第三方执行）。

## 5. 脚本管理中心

统一录入官方包、源码发行包、容器、经审核的第三方脚本。每个安装器必须写清：来源、发布版本、许可证、平台矩阵、权限、网络、文件写入列表、安装命令、检查命令、卸载行为和风险等级。

对于社区第三方脚本：**下载到本地缓存 → 校验来源/哈希/版本 → 静态审核 → 显示摘要 → 用户授权 → 调用固定接口**。不得自动信任 main 分支变化。

## 6. 完成标准

- 安装软件不是“脚本返回 0”就算成功，必须检查目标版本、路径和必要能力。
- 无论成功/失败，都有机读结果，失败可重试且不会静默误报。
- 普通安装不用 root 启动整个管理器，具体步骤按需 sudo。
- 不对用户系统中非本工具安装的资源执行卸载或重置。
- 每项模块有平台适配/脚本版本/最小依赖和真实验证证据，无法支持则明确拒绝。
