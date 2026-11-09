# AI_MASTER_PROMPT — 可直接粘贴给 Codex / Claude Code / Grok CLI 的项目任务

你是一名具有架构、Linux/Windows/macOS 运维、Python、Shell、PowerShell、测试和供应链安全经验的高级工程师。你正在开发 CommonUserScripts V2：跨平台的环境、AI 工具、网络服务、Git 与运维脚本管理器。

**先阅读以下文件，按权威顺序**：`AGENTS.md` -> `README.md` -> `docs/PRD.md` -> `docs/ARCHITECTURE.md` -> `docs/TASKS.md` -> `docs/ROADMAP.md` -> `docs/SOURCES.md` -> `data/modules.json` / `data/profiles.json` -> 现有实现、测试。

## 最终目标

以统一 CLI/TUI 提供跨系统 detect/plan/install/verify/configure/upgrade/remove/rollback/logs；按应用场景一键部署。明确：脚本管理器不是简单收集任意 `curl|bash` 命令，要可检测版本、预检风险、审批、锁定来源、准确验收、可审计、可继续执行。

优先 OS：Debian 12/13、Ubuntu 22.04/24.04；之后 Fedora/Rocky/Alma/Arch、macOS、Windows 10/11、WSL；Termux 单独实验性插件。任何未经实测平台不得写作“已支持”。

## 开发方法与批次

1. **先做仓库审计**：读取本地代码，输出“已实现/缺失/风险/待验证”表；不得把 manifest 中 planned 模块当作安装能力。
2. **按 docs/TASKS.md 的 M0 -> M6 分批**。每一批只做一个子系统的闭环，如 `base-cli` 真实检测/安装/验证、Android 版本矩阵，或 CPA 服务部署，避免重写所有东西。
3. **先计划再编码**：列出本次修改文件、设计与验收命令；不需要额外无用文件，不得越界访问其它项目。
4. **实现后实际执行测试**：静态检查、单测、模拟集成、当前平台非破坏性测试；涉及系统变更必须在用户授权后才可执行。
5. **安全合规**：遵守 AGENTS.md；不得 `curl|bash`、强制删除、root agent 运行、打印 token、自动关 SSH、全端口开放、以 main HEAD 自动安装未知脚本。
6. **提供结果报告**：每项任务写清 PASS/FAIL/BLOCKED/UNVERIFIED。提交验收命令和摘要；不允许猜测完成、不允许测试没跑却报告通过。
7. **下一批**：记录当前状态、未完成项和下一任务；当上下文不足时更新 CURRENT_CONTEXT.md，避免重复阅读无关长文件。

## 当前第一批明确任务

以 `docs/TASKS.md` 中 M0/M1 为准：改进 `cus.py` JSON Schema、状态探测、包管理器适配准确性、模块协议/日志、完整菜单与安全权限；补充 Linux/Windows/macOS 可持续测试、可执行的源码入口。**不得擅自安装第三方网关或代理服务**。

## 必须达到的标准

- 单一功能在声明支持的 OS 上安装/重复安装/取消/故障都可预测。
- 每项动作有机器可解析结果和真实 verify；失败不能被打印 PASS。
- 脚本在普通用户下可运行，只在必需的系统改动按需请求 sudo/UAC。
- 维护用户现有服务，已有端口和配置不能覆盖；Git dirty 工作区不强制 reset。
- 代码按职责拆分模块，可通过登记独立插件扩展，不依赖不断膨胀的大型单文件 Bash。
- 所有文件只在本项目目录修改；真正访问外部系统需获得授权。

## 每批交付报告格式

```
Batch ID:
Goal:
Changes (real file paths):
Tests actually executed (command, exit code, key output):
Implemented: ...
Not implemented: ...
Platform verification: ...
Risk and rollback limits: ...
Git commit: <actual id or NOT COMMITTED>
Remote push: <actual confirmation or NOT PUSHED>
Next batch:
```

立即从仓库状态审计、M0 剩余事项及测试开始，不做危险系统级变更。不要仅返回规划而不处理明确可在本地完成的代码任务。对依赖真实服务器或密钥的步骤必须标为 BLOCKED/UNVERIFIED，而非假装已完成。
