# 开发任务拆解与可验证验收规范

## 工作原则

每张任务卡都需包括：动机、影响平台、输入/输出、依赖、预检、不可做事项、测试、验收证据、回滚边界。主干每次只交付一个可验收批次，不允许“一次性重写所有脚本”。

## M0：工程底座（P0）

- [x] 建立可运行 Python CLI、模块目录 JSON、场景清单。
- [x] 基础发行版识别（Debian 系/dnf 系/Arch/mac/Windows/Termux read-only）。
- [x] `doctor`、`list`、`show`、`plan`、`install`（仅有限原生包）、`history`、`version`、`menu`。
- [x] `--apply` + 交互确认门禁；不支持的第三方适配器拒绝执行；日志不写密钥。
- [x] 初步单元测试（单一 Linux 环境）。
- [ ] 规范 `--json` 在子命令前后的解析行为，并稳定 JSON Schema。
- [ ] 分级错误码、子菜单路由、多语 i18n、TUI 搜索、stdout/stderr 区分。
- [ ] 操作计划输出磁盘需求、网络下载量、写入路径、端口、权限；增加跨系统测试。
- [ ] 安装后功能验证和包管理器数据库检测，修正只有 `which` 的判断。

**M0 验收**：`python3 cus.py doctor`、`python3 cus.py --json plan ai-agent`、`python3 -m unittest discover -s tests` 实际执行；`net-shadowsocks --apply` 返回 BLOCKED；默认查看不改变系统。

## M1：原生包与运行引擎（P0）

- [ ] 定义 `Module`、`Context`、`Result`、`SupportMatrix` 和 `ActionPlan` 严格 Schema。
- [ ] 适配 apt/dnf/pacman/brew/winget，并在不同 OS+架构+版本做可重复测试。
- [ ] 任务依赖拓扑、可选择版本、文件归属、执行锁、操作审计、取消/重试。
- [ ] `detect` 不能仅凭 command -v，确认安装渠道与真实版本。
- [ ] 原子写配置/文件级回滚；不承诺系统更新完全回滚。
- [ ] CI: Linux/macOS/Windows；静态检查、格式检查、ShellCheck、PowerShell PSScriptAnalyzer。

**验收**：3 个已完成模块在 Debian/Ubuntu 实机安装/检测/重复执行无副作用；Windows/macOS 至少只读诊断通过；故障注入不误报成功。

## M2：开发环境（P0/P1）

- [ ] dev-node：Node LTS 版本管理器、npm/pnpm、普通用户安装、网络/环境变量验证。
- [ ] python：uv、venv、pip 系缓存检测、项目隔离；不替换系统 Python。
- [ ] dev-jdk：JDK 17/21 等版本矩阵、Gradle Wrapper 优先、`java -version`/`gradle --version`。
- [ ] dev-android：sdkmanager、platform-tools/adb、build-tools/API、licenses、Flutter、Dart、`flutter doctor -v` 分项验收；SDK 目录写入 user home，避免 root/dev 混用。
- [ ] dev-go、dev-rust 与标准编译工具链；跨架构包校验。

**验收**：全新 Debian 测试机安装 Android 工具后：`java -version`、`sdkmanager --list`、`adb version`、`flutter doctor -v` 有真实状态；若缺硬件或 IDE 明确标记 WARN，而非声称 PASS。

## M3：AI CLI 与模型网关（P1）

- [ ] 适配官方 Codex、Claude Code、Gemini CLI、Grok CLI、ZCF、OpenCode；根据 OS/渠道检测前置条件。
- [ ] 维护安装渠道和版本锁；区分用户级与全局 npm 包；避免 sudo npm。
- [ ] `doctor ai` 实测 CLI `--version`、配置存在性，账号验证由用户授权；不读取不必要 secrets。
- [ ] 第三方 API 配置：base URL、API 模式（chat_completions / responses / anthropic）、模型列表、流式与 tool calls 实际验证；不能只测 `/v1/models` 就称全面兼容。
- [ ] CPA、Magpie：独立 Docker/本地/服务模式，监听地址/端口校验，先检查已运行实例，不覆盖已有数据和端口；私有配置文件权限。
- [ ] 任何公网暴露 API 前必须要求认证、TLS 与网络边界检查。

**验收**：安装器真实回显版本；模拟错误 token / 不支持模型 / 无 tool calls，分别返回不同失败码；执行日志脱敏。

## M4：网络服务与 SSH 安全（P1）

- [ ] JXAB Shadowsocks 适配器：预检脚本来源、固定 revision + sha256、下载后审核，并在隔离 VM 测试所有菜单分支。
- [ ] teddysun 脚本仅作可选兼容参考；老组件先审维护状态与支持矩阵，不默认安装。
- [ ] WireGuard、Tailscale、ZeroTier、FRP 单独插件；服务检测、端口冲突、路由/MTU/防火墙判断。
- [ ] SSH 端口变更：开放新端口 → 配置校验 `sshd -t` → 保留当前会话 → 独立连接检查 → 手工选择是否移除旧规则。云防火墙外部需提示，禁止假定已放行。

**验收**：模拟 SSH 中断、未授权、端口占用、无证书；不会导致新旧端口同时失效。成功安装 Shadowsocks 必须做服务/端口/实际连通性验证。

## M5：维护、Git 与备份（P1）

- [ ] 清理菜单按 apt/npm/pip/go/docker 可清理缓存分类，列出路径和大小，允许逐项勾选。
- [ ] Docker image/build cache 与 named volumes 明确区分，永不默认 `docker system prune --volumes`。
- [ ] Git 同步：拉取优先 fast-forward、未提交状态检查、远程推送前确认。
- [ ] 备份/恢复支持本工具拥有的配置、哈希、版本元数据、校验和恢复演练。
- [ ] 自动更新：检查版本 / 展示变更 / 用户审批 / 下载校验 / 原子切换 / 失败回退。

**验收**：复杂目录含空格、符号链接、非本工具目录、用户 SSH 密钥、Git dirty 状态均不会被误删或覆盖。

## M6：场景部署与发布（P1/P2）

- [ ] profile 能生成有依赖顺序的执行 DAG；支持选择/排除模块、交互预览与保存 JSON 计划。
- [ ] plan hash +审批后的固定计划；任何版本漂移都要求重新批准。
- [ ] AI CLI 最小上下文结果 JSON：每模块状态、证据、耗时、版本与错误码，方便 Codex/Hermes/Claude 读取。
- [ ] 本地离线 bundle；发行包 SHA256、签名、SBOM、Release notes；版本标签不指向可变 main。
- [ ] 制作 `install.sh/install.ps1` 安全启动器，下载验证后调用本地主程序；不能直接 `curl|bash` 执行大脚本。

**验收**：任意一个场景跑完后逐模块返回 `SUCCEEDED/FAILED/BLOCKED/SKIPPED/UNVERIFIED`，验收条件无法满足时不得称整体 PASS；失败后下一次能安全继续。

## 必测异常用例

1. 目标程序已安装且版本不符；2. 普通用户无 sudo；3. SSH 中断；4. DNS 失败；5. TLS/Hash 不匹配；6. 磁盘空间不足；7. apt/dpkg 被锁；8. 端口占用；9. 取消 Ctrl+C；10. 第三方源 404；11. 不能访问 GitHub；12. root/dev 目录归属不同；13. Python 没安装；14. ARM64 不支持的包；15. 安装退出码 0 但命令不可用；16. 配置语法错误；17. 旧版文件与新版本冲突；18. CI 无终端输入。

## Bug/交付报告格式

- `Task-ID`、系统和架构、修改文件、变更摘要、测试命令、exit code、验证证据与剩余限制。
- 本地文件路径/commit hash 不等于 GitHub push 成功；没有 repo URL 和实际远程返回证据不得声称上传。
