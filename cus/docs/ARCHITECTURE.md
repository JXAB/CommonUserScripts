# 技术架构与模块协议（目标架构）

## 1. 五层分工

```
[OS-native bootstrap: bash / PowerShell / Termux shell]
              |
[Core: Python 3 stdlib CLI/TUI + registry + settings]
              |
[Engine: detect > plan > lock > approve > apply > verify > report]
              |
[Adapters: apt / dnf / pacman / brew / winget / pkg / systemd / services]
              |
[Modules: dev / AI / gateway / network / git / cleanup / security / backup]
              |
[Profiles: minimal-vps / python-backend / ai-agent / android / proxy / ...]
```

为何选择 Python 主控 + Shell/PowerShell bootstrap：大量交互、配置文件和错误处理在 Bash 中维护成本高；Python stdlib 可以复用相同模块表和 JSON；新机无 Python 时 bootstrap 用对应包管理器提供**受用户确认且版本可信**的安装流程。需要严格控制 Python 最低版本（建议 3.10+，在 CI 固定矩阵测试）。Windows 全局管理员 PowerShell 不应该成为运行前置条件。

## 2. 完整目录结构（下一阶段目标；Starter 仅创建其中一部分）

```
CommonUserScripts/
  install.sh                # Linux/macOS 安装管理器，hash/pin
  install.ps1               # Windows 安装管理器
  cus.py                    # 安装包内入口，后续生成统一 cus 命令
  src/cus/
    cli.py                  # 命令解析
    menu.py                 # TUI 导航
    runtime.py              # 能力发现
    registry.py             # 模块注册与依赖拓扑
    engine.py               # 有状态事务引擎
    policy.py               # 权限、风险分类与执行门禁
    storage.py              # journal、配置/快照、锁
    fetch.py                # 带哈希校验的下载器
    verify.py               # 版本检查/健康测试/能力探测
    secrets.py              # OS Secret Store 接口
    adapters/
      apt.py dnf.py pacman.py brew.py winget.py termux.py
      systemd.py launchd.py windows_service.py
    modules/
      base/ development/ android/ agents/ gateways/ network/
      git/ containers/ maintenance/ backup/ security/
  data/
    modules.json            # 机读模块清单
    profiles.json           # 场景组合
    compatibility.json      # 发行版*架构*版本限制
    sources.lock.json       # 固定外部源与 sha256
  docs/ PRD.md ARCHITECTURE.md TASKS.md ROADMAP.md SOURCES.md
  tests/unit/ tests/integration/ tests/e2e/
  .github/workflows/ci.yml
  AGENTS.md AI_MASTER_PROMPT.md README.md
```

## 3. 模块协议

每个模块实现：

| 接口 | 作用 | 必须保障 |
|---|---|---|
| `detect(ctx)` | 检测已安装版本/归属 | 不修改机器；未检测=unknown |
| `plan(ctx, params)` | 输出步骤与风险 | 列出每个写入位置、端口、依赖、下载 |
| `install(ctx)` | 安装 | 只使用 allowlisted 操作、幂等处理 |
| `verify(ctx)` | 验收 | 真正检查命令、版本、服务与请求 |
| `configure(ctx)` | 修改配置 | 先备份、原子写入、校验格式 |
| `upgrade(ctx)` | 升级 | 用户可选锁定版本，保留原配置 |
| `remove(ctx)` | 卸载 | 只移除归属本模块的资源 |
| `rollback(ctx)` | 回滚 | 只声称能恢复实际备份的文件；系统包安装不保证完全可回滚 |
| `logs(ctx)` | 查看日志 | 敏感值掩码、文件权限保护 |

模块元数据推荐 JSON：

```json
{
  "id": "ai-codex",
  "category": "ai-agent",
  "source": "https://github.com/openai/codex",
  "version_policy": "pinned",
  "support": [{"os": "debian", "arch": "x86_64", "min": "12"}],
  "depends_on": [],
  "risk": "medium",
  "scope": "user",
  "ports": [],
  "file_ownership": ["~/.config/<specific-owned-path>"],
  "operations": ["detect", "plan", "install", "verify", "upgrade"],
  "verify": {"command": ["codex", "--version"]}
}
```

备注：示例定义的是目标协议，并非 Starter 已经实现此安装器。版本策略需要兼容官方原生安装、npm、brew 等不同渠道；同一个 binary 多渠道不能混装。

## 4. 引擎状态机

`NEW -> CHECKED -> PLANNED -> AWAITING_APPROVAL -> EXECUTING -> VERIFYING -> SUCCEEDED`

异常分支：`BLOCKED`、`UNSUPPORTED`、`FAILED`、`CANCELLED`、`PARTIAL`。运行时状态必须是单向可追溯的事件；`FAILED` 不得被后续无关成功掩盖；不能因为进程退出 0 就断言所有目标已满足。

**任务 ID**：时间戳 + 6 位随机值；**锁**：每资源域一把锁；**中断**：SIGINT/SIGTERM 对外部进程可控退出，写入 unfinished 日志，下次进入提供继续/撤销选项；不保证任意系统更新可中断或回滚。

## 5. 适配层必须解决的差异

- Linux：发行版 ID_LIKE、apt/dnf/pacman、systemd/OpenRC、SELinux/AppArmor、sudo/su、iptables/nftables。
- Windows：winget、PowerShell、用户/机器 PATH、管理员 UAC、Windows 服务、计划任务、Defender 防火墙；可将 WSL 视为单独环境。
- macOS：brew、launchd、Keychain、Apple Silicon 与 Intel 架构、系统完整性保护。
- Termux：`pkg`、Android/Bionic、root 与非 root、proot-distro；不得自动使用 glibc 包。

## 6. 数据位置与安全

用户配置：Linux/mac `~/.config/commonuserscripts/`；Windows `%APPDATA%\\CommonUserScripts`。
运行历史：Linux/mac `~/.local/state/commonuserscripts/`；Windows `%LOCALAPPDATA%\\CommonUserScripts`。
下载缓存：平台对应缓存目录，按版本索引，允许手动清理。
服务部署：仅在用户明确选择系统模式时写入 `/etc/...` 和 `/var/lib/...`；记录文件归属。
密钥：优先系统秘密存储；或 `0600` 权限文件，日志必须脱敏，绝不把 Token 明文提交 Git。

## 7. 安装服务与客户端两套权限模型

- 普通用户模块：AI CLI、Git 配置、Python/Node 版本管理器、工作目录，原则上不升权。
- 系统模块：Shadowsocks、Docker 服务、系统包、防火墙，按需 sudo 并单独弹确认。
- Windows 管理员步骤仅对确实需要的服务/系统设置触发 UAC。
- SSH/防火墙变更要求先检测当前登录链路，开放新端口，外部连通性确认后才能考虑旧端口；**自动禁用当前 SSH 端口禁止**。

## 8. Git 与清理模块特殊设计

Git：读取 status → 检测未提交修改/上游/分叉 → fetch → 只对 fast-forward 执行合并；绝不 `git reset --hard` 自动修复。自动提交/推送默认关闭。

清理：展示各缓存路径与可回收量（`unknown` 就注明），只操作明确定义的缓存目录；禁止对 Home、项目、Docker volume、数据库、SSH 密钥、浏览器 Cookie、配置文件做宽泛删除。APT clean、pip cache purge、npm cache clean --force、go clean -cache、journalctl --vacuum-* 分开审查、独立执行和汇报。
