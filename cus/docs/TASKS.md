# TASKS.md — 任务分批与里程碑计划 (M0 ~ M6)

遵循 `AGENTS.md`：**先测后写、分批交付、实际运行验证、输出结构化报告**。

---

## 里程碑总览

| 里程碑 | 主题 | 目标产出 | 状态 |
|---|---|---|---|
| **M0** | 核心底座与架构 | OS/硬件探测、L0~L4安全审计器、六阶段状态机、CLI骨架、单测套件 | 进行中 |
| **M1** | 场景 A：云服务器开荒 | 系统信息总览、时区管理、BBR优化检测、基础运维工具闭环 | 待开始 |
| **M2** | 场景 B：AI Agent 工作站 | `uv` / Python 环境、`fnm` / Node 环境、Claude/Gemini/Codex CLI 探测与集成 | 待开始 |
| **M3** | 场景 C：模型 API 网关 | CLIProxyAPI / Magpie 适配器、端口冲突预检、systemd 守护进程与 `/v1/models` 探活 | 待开始 |
| **M4** | 场景 D：移动端/跨平台编译 | JDK 17/21 矩阵、Android SDK 命令行工具、自动签署 Licenses、Flutter 环境 | 待开始 |
| **M5** | 场景 E/F/G：容器/组网/诊断 | Docker/Podman 适配器、Tailscale/WireGuard 适配器、磁盘/日志安全预估与清理 | 待开始 |
| **M6** | 场景 H 与 TUI 终端主控 | Git 自动化与 CI Runner、全屏交互式主菜单（20个一级项）、多系统端到端测试 | 待开始 |

---

## M0 详细任务分解（当前执行批次）

- [x] 1. 设计系统架构规范 `docs/ARCHITECTURE.md` 与演进路线 `docs/ROADMAP.md`。
- [ ] 2. 建立模块与场景数据清单：
  - `data/modules.json`
  - `data/profiles.json`
- [ ] 3. 编写 `core/platform/os_detect.py` 的测试用例 `tests/unit/test_os_detect.py`（TDD 先行）。
- [ ] 4. 实现 `core/platform/os_detect.py`：支持 Linux (Debian/Ubuntu/Fedora/Arch/Alpine/Termux)、macOS、Windows 的准确识别。
- [ ] 5. 编写安全审计模块 `core/security.py` 及测试：实现 L0~L4 权限拦截、Secret/Token 脱敏校验。
- [ ] 6. 编写状态机与执行引擎 `core/engine.py` 及测试：实现 Detect -> Plan -> Approve -> Apply -> Verify -> Report 六阶段闭环。
- [ ] 7. 实现入口命令行 `cus.py`（支持 `--dry-run`、`--apply`、`--json`、`status`、`profile` 子命令）。
- [ ] 8. 运行本地自动化测试，生成真实测试命令与证据，产出 M0 交付报告。
