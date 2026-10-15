# old-dev —— 开发过程归档

本目录保存 `shadowsocks/` 脚本成型过程中用到的**参考资料、上游脚本副本、本机考古结论和踩过的坑**。
不参与安装流程，纯粹是给以后排查问题时提供线索和方法。

出问题时的建议顺序：

1. 先看 [TROUBLESHOOTING-PLAYBOOK.md](TROUBLESHOOTING-PLAYBOOK.md) —— 可直接复制执行的排查命令
2. 再看 [DEVELOPMENT-LOG.md](DEVELOPMENT-LOG.md) —— 每个设计决策背后的核验依据，以及已经踩过的坑
3. 需要对照上游行为时，看 [upstream-scripts/](upstream-scripts/) 里的脚本副本
4. 涉及本机历史安装的，看 [machine-history/](machine-history/)

## 目录

| 路径 | 内容 |
|------|------|
| [DEVELOPMENT-LOG.md](DEVELOPMENT-LOG.md) | 开发全过程：核验结论、方案取舍、修过的 bug |
| [TROUBLESHOOTING-PLAYBOOK.md](TROUBLESHOOTING-PLAYBOOK.md) | 排查手册，按症状组织的实用命令 |
| [upstream-scripts/](upstream-scripts/) | 评估过的 5 个上游/第三方脚本副本（含 sha256 与结论） |
| [machine-history/](machine-history/) | 本机 2025 年原始安装的考古结论与残留文件 |

## 核心结论速查

| 问题 | 结论 | 出处 |
|------|------|------|
| Debian 10 要不要源码编译 | **不要**。Teddysun apt 仓库有 buster 包 | DEVELOPMENT-LOG §2 |
| 第三方增强版（Fmmx / idlm）值不值得用 | **不值得**。官方仓库已原生覆盖 Debian 12/13 | DEVELOPMENT-LOG §3 |
| 网传的「Debian 9/10 备用」脚本是什么 | teddysun@`dab9bec7` 的**字节级副本**，应改用 GitHub commit URL | DEVELOPMENT-LOG §3 |
| 上游服务名到底叫什么 | apt/新脚本是 `shadowsocks-libev-server`（带 `-server`） | DEVELOPMENT-LOG §4 |
| 本机原来是怎么装的 | 2025-02-28 用 **legacy 脚本**装的，不是源码编译 | machine-history/README.md |

## 安全说明

本目录中所有文件已脱敏：**不含真实 IP、密码**。归档前已逐项核对。
后续往这里添内容时请保持同样原则 —— 这是公开仓库。
