# ROADMAP.md — 演进路线与版本规划

## 版本里程碑目标

### v0.1.0-alpha (M0 完成)
* 跨平台（Linux、macOS、Windows）核心探测引擎就绪；
* 六阶段（Detect -> Plan -> Approve -> Apply -> Verify -> Report）执行框架就绪；
* 风险评级系统（L0 ~ L4）与 Secret 防泄露检测生效；
* 命令行基础交互支持（`--dry-run`, `--apply`, `--json`）。

### v0.2.0-beta (M1 ~ M2 完成)
* 场景 A（全新云服务器开荒）正式支持；
* 场景 B（AI Agent 工作站）正式支持，覆盖 uv, fnm, AI CLI 系列工具；
* 本地配置自动快照与备份恢复能力。

### v0.3.0-rc (M3 ~ M5 完成)
* 场景 C（模型 API 网关）支持一键服务化与接口探活；
* 场景 D（Android / Flutter 编译环境）实现无交互自动化搭建；
* 场景 E/F/G（Docker、组网、磁盘安全预估与清理）支持。

### v1.0.0 (M6 正式版)
* 完整 20 顶级菜单 TUI 交互界面；
* 支持多机 Profile 清单导出与独立执行；
* 覆盖 Debian 12/13, Ubuntu 22/24, Fedora, Arch, macOS, Windows WSL 实机测试矩阵。
