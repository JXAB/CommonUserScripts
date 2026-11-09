# ARCHITECTURE.md — CommonUserScripts (CUS) V2 架构设计规范

## 1. 系统核心设计理念

CUS V2 不是不可控的 `curl | bash` 脚本集合，而是一个具备**全平台状态感知、声明式模块管理、严格风险分级与闭环验收**的现代脚本与环境管理器。

```
┌─────────────────────────────────────────────────────────────┐
│                      用户界面层                             │
│   • 交互式终端 TUI (文本菜单/状态展示)   • 自动化 CLI (--json)     │
├─────────────────────────────────────────────────────────────┤
│                    核心引擎 (Core Engine)                    │
│   [Profile 编排]  ───→  [依赖解析拓扑排序]  ───→  [生命周期调度]  │
│                                                              │
│       ┌─────────┐   ┌──────┐   ┌─────────┐   ┌─────────┐     │
│       │ DETECT  │──→│ PLAN │──→│ APPROVE │──→│  APPLY  │     │
│       └─────────┘   └──────┘   └─────────┘   └─────────┘     │
│                                                   │          │
│                                                   ▼          │
│                                        ┌─────────┐ ┌────────┐│
│                                        │ VERIFY  │ │ REPORT ││
│                                        └─────────┘ └────────┘│
├─────────────────────────────────────────────────────────────┤
│                     安全与事务底座                          │
│   • 权限分级 (L0~L4)  • 变更快照备份 (Backup/Rollback)  • 审计日志│
├─────────────────────────────────────────────────────────────┤
│                    跨平台执行驱动 (Drivers)                  │
│    apt / dnf / pacman / brew / winget │ systemd / launchd    │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 六阶段执行管道（Execution Pipeline）

每一个模块与场景动作均强制经过以下 6 个阶段：

1. **DETECT（状态探测）**：
   - 检查当前操作系统（OS、版本、架构、内核）、特权状态（root / sudo / 普通用户）。
   - 检查目标组件是否已安装、当前版本、依赖项满足情况、端口冲突。
2. **PLAN（变更规划）**：
   - 生成执行计划：需要下载的资源（URL/SHA256）、需要写入的路径、需要变更的系统服务。
   - 评定风险等级（L0 ~ L4）。
3. **APPROVE（用户审批）**：
   - 在交互模式下输出直观变更差异并等待确认；在 CLI 模式下要求显式传入 `--apply` 参数。
4. **APPLY（幂等执行）**：
   - 备份旧配置文件；
   - 按照最小特权原则执行用户级或系统级指令；
   - 保持幂等：重复执行不导致环境被破坏或重复写入。
5. **VERIFY（能力验收）**：
   - 严禁以“命令返回码 0”代表安装成功；
   - 校验：二进制文件是否存在且可执行、`--version` 准确输出、端口正常监听、核心接口探活成功。
6. **REPORT（结果与审计）**：
   - 输出人类友好的彩色摘要；
   - 输出机器可解析的 JSON 结果供 CI 或上层 Agent 读取。

---

## 3. 安全等级定义（遵循 AGENTS.md）

| 级别 | 定义 | 触发条件 | 行为控制 |
|---|---|---|---|
| **L0** | 只读诊断 | 状态查看、端口检测、空间统计 | 默认允许执行，无需提权 |
| **L1** | 用户级安装 | 安装 `uv`、Node 工具链、修改当前用户 Profile | 无需 root，限制在用户家目录 |
| **L2** | 系统包管理 | `apt install`、`dnf install`、配置 systemd | 显式展示所需权限，按需 sudo |
| **L3** | 高风险系统变更 | 改写防火墙、网络端口绑定、清理旧日志 | 强制生成前置快照，二次弹窗确认 |
| **L4** | 危险破坏性操作 | `rm -rf /`、强制重置未提交工作区、清空全盘 | **引擎层面硬编码拦截与禁止** |

---

## 4. 模块描述规范 (Module Manifest Schema)

每个可安装组件或运维操作均以 JSON 规范声明：

```json
{
  "id": "base-python-uv",
  "name": "Python & uv Toolchain",
  "category": "dev_lang",
  "risk_level": "L1",
  "platforms": {
    "linux": ["debian", "ubuntu", "fedora", "arch"],
    "darwin": ["macos"],
    "windows": ["win10", "win11"]
  },
  "detect": {
    "binary": "uv",
    "version_cmd": ["uv", "--version"],
    "version_regex": "uv ([0-9.]+)"
  },
  "install": {
    "mode": "standalone_script",
    "url": "https://astral.sh/uv/install.sh",
    "sha256": "...",
    "require_sudo": false
  },
  "verify": {
    "commands": [
      { "cmd": ["uv", "--version"], "expect_code": 0 },
      { "cmd": ["uv", "python", "list"], "expect_code": 0 }
    ]
  }
}
```

---

## 5. 场景编排规范 (Profile Specification)

场景是将一组原子模块按拓扑依赖顺序编排的一键工作流：

```json
{
  "id": "vps-init",
  "name": "全新云服务器安全开荒",
  "description": "基础网络优化、系统工具、时区校准与基础安全检查",
  "steps": [
    { "module_id": "sys-timezone", "required": true },
    { "module_id": "sys-bbr", "required": false },
    { "module_id": "base-cli-tools", "required": true },
    { "module_id": "sec-ssh-check", "required": true }
  ]
}
```
