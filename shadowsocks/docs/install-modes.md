# 安装方式对照与选型依据

脚本会自动选择安装方式，也可以用 `--mode` 手工指定。本文记录每种方式的适用范围，
以及为什么这么选 —— 所有结论都基于 2026-10-14 对各仓库和脚本的实际核验。

## 四种安装方式

| 方式 | 适用系统 | 做什么 | 耗时 |
|------|----------|--------|------|
| `repo`（默认） | Debian 10/11/12/13、Ubuntu 20.04/22.04/24.04/25.x | 添加 Teddysun 官方 apt 仓库，`apt install shadowsocks-libev` | 秒级 |
| `teddysun` | RHEL/CentOS/Rocky/AlmaLinux 8+，或需要 rust 版 / v2ray / xray 插件 | 调用上游 master 交互式 `shadowsocks-all.sh` | 1-2 分钟 |
| `legacy` | Debian 9 及其他仓库未覆盖的老系统 | 调用固定在 commit `dab9bec7` 的旧版一键脚本 | 3-8 分钟（现场编译） |
| `source` | 最终兜底，需显式 `--mode source` | 本仓库自行编译 shadowsocks-libev 3.3.5 | 3-8 分钟 |

自动判定**不按版本号硬编码**，而是以 Teddysun 仓库实际提供的 codename 为准：

```text
Debian : buster bullseye bookworm trixie
Ubuntu : focal jammy noble resolute
```

在列表内 → `repo`；Debian/Ubuntu 不在列表内 → `legacy`；RHEL 系 → `teddysun`。

## 为什么默认用 apt 仓库

Teddysun 在 2026-03-07 重写了官方脚本，**移除了全部源码编译逻辑**（libsodium、mbedtls），
改为从自建 apt/dnf 仓库安装。核验结果：

- 仓库 `https://dl.lamp.sh/shadowsocks/debian/` 提供 `shadowsocks-libev` 与 `shadowsocks-rust`
- **buster（Debian 10）也在其中**，版本 `3.3.5-12~debian.10~buster`
- 全部 11 个依赖在 Debian 10 归档源中可用，`apt-get -s install` 模拟解析通过
- 仓库 `InRelease` 有 GPG 签名，公钥指纹 `8B22B39B30A0E20328FD16A5A930C227F704BE66`

相比源码编译的优势：

- **秒级完成**，不需要 build-essential 等编译依赖
- **低配机器不会 OOM**：128M-512M 内存的小鸡编译 mbedtls 很容易被 OOM killer 打断
- **可升级**：后续 `apt upgrade` 就能更新，源码编译装完就固定在那个版本
- **行为统一**：Debian 10-13 与 Ubuntu 各版本走同一条代码路径，只有一处要维护

本脚本在导入公钥时会**校验指纹**，不匹配直接终止 —— 上游脚本没有做这一步。

## 为什么 Debian 9 用 legacy 而不是源码编译

Teddysun 仓库没有 stretch，Debian 9 只能走脚本。`dab9bec7`（2022-06-20）是上游
最后一个支持 Debian 7-10 的版本，内部自带 libsodium 1.0.18 与 mbedtls 2.16.12 的
编译逻辑，下载链接 2026-10-14 实测仍然存活（均返回 200）。

它比本仓库自己写的编译逻辑经过更多实际环境检验，所以作为 Debian 9 的默认方式，
`source` 只保留为兜底。

### 关于第三方镜像

网上流传的若干「Debian 9/10 备用」一键脚本，经校验其实就是 teddysun@`dab9bec7`
的**字节级副本**（sha256 前 16 位 `1d2d9969fa2d1f50`）。

本脚本不使用那类第三方副本，改用 GitHub 的 commit URL：

```text
https://raw.githubusercontent.com/teddysun/shadowsocks_install/dab9bec7/shadowsocks-all.sh
```

内容相同，但来源可信且 **commit URL 的内容不可变** —— 第三方静态站点的文件可以随时被替换，
而以 root 执行一个被替换过的安装脚本后果是整机失陷。

## 关于其他增强版分支

| 脚本 | 核验结果 | 是否采用 |
|------|----------|----------|
| `Fmmx/shadowsocks-libev-enhance` | 2019 年版 teddysun 4-in-1 的 fork，仍是源码编译 + SysV init，含已停止维护的 Python/R/Go 版本 | 否 |
| `idlm/shadowsocks_install` 增强版 | 同样是 fork，来源与维护状况无法核实 | 否 |

两者声称的主要卖点是"支持 Debian 12/13"，而官方仓库已原生覆盖 bookworm 与 trixie，
再引入来源不明的第三方 fork 只会增加供应链风险，没有实际收益。

需要 rust 版或 v2ray/xray 插件时，用 `--mode teddysun` 调官方 master 脚本即可，
这两项是官方脚本已有的能力。

## 手工指定方式

```bash
bash install.sh install --mode repo -y        # 强制走 apt 仓库
bash install.sh install --mode teddysun       # 需要 rust / 插件
bash install.sh install --mode legacy         # 老系统一键脚本
bash install.sh install --mode source -y      # 自行编译兜底
```

## 各方式安装后的路径

| 方式 | 配置文件 | 服务 |
|------|----------|------|
| `repo` / `teddysun` | `/etc/shadowsocks/shadowsocks-libev-config.json` | `shadowsocks-libev-server` |
| `teddysun`（rust） | `/etc/shadowsocks/shadowsocks-rust-config.json` | `shadowsocks-rust-server` |
| `legacy` | `/etc/shadowsocks-libev/config.json` | `/etc/init.d/shadowsocks-libev`（SysV） |
| `source` | `/etc/shadowsocks-libev/config.json` | `shadowsocks-libev` |

脚本的管理子命令（`info`/`port`/`password`/`restart`/`backup`/`restore`）会自动识别
以上全部组合，卸载时也按实际安装方式路由，不按系统版本猜测。
