# 路线图、发行策略与里程碑

| 版本 | 主题 | 交付边界 | 验收方式 |
|---|---|---|---|
| v0.1 Starter（随包附带） | 本地入口+模块注册+场景规划 | 3 类原生 package 有限安装、diagnostics、其他目录只读 | 当前测试脚本 + Linux 只读实际验证 |
| v0.2 Core | CLI/TUI 工程化 | 统一引擎、回退/错误/平台矩阵、日志、锁、版本检测 | Linux/Windows/macOS CI + 真实 VM 验收 |
| v0.3 Developer | 开发环境 | Node、Go、JDK、Android SDK、Flutter、Python、Docker | 全新测试机安装与实际编译 |
| v0.4 AI Workstation | AI CLI / API | Codex/Claude/Gemini/Grok/ZCF、CPA/Magpie | CLI 版本、模型协议/工具调用、服务健康证据 |
| v0.5 Infrastructure | 网络与系统运维 | Shadowsocks、SSH/防火墙、缓存、Git、备份 | 端口冲突、安全演练、恢复测试 |
| v0.6 Automation | 场景部署与插件市场 | Profile 执行、离线源、版本锁、报告和安全升级 | 断点恢复/失败注入/跨 OS 集成 |
| v1.0 Stable | 稳定发布 | 完成明确的支持矩阵、签名发布、运维手册 | 所有声明支持的环境回归验证 |

## 重点决策

- 不要因为存在模块定义就展示“安装完成”；模块能力分 `planned / available / verified / partial / blocked / unsupported`。
- 不把完整 Docker/Magpie/CPA/Android 套件塞进核心安装依赖。
- 首发聚焦 Debian/Ubuntu，再在 CI + VM 中逐个平台提升支持等级。
- 首个交付周期优先把系统基础、开发环境与 AI CLI 做深，而不是先开发 Web 面板。
- 产品命令统一 `cus`，源代码 Starter 用 `python3 cus.py`，待正式发布完成部署入口与 PATH 安装后才启用全局 `cus` 命令。
