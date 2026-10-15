# 上游与第三方脚本副本

归档时间：2026-10-15。保留副本是为了**对照上游行为**（配置路径、服务名、卸载入口等），
不是为了直接执行。要安装请用仓库的 `install.sh`。

## 清单

| 文件 | 来源 | sha256 前缀 | 大小 | 结论 |
|------|------|-------------|------|------|
| `teddysun-master-2026-03-07.sh` | [teddysun/shadowsocks_install@master](https://github.com/teddysun/shadowsocks_install) | `0852aa568f2f9c51` | 23KB | ✅ 用于 RHEL 系与插件/rust 场景 |
| `teddysun-legacy-dab9bec7.sh` | 同上，commit `dab9bec7`（2022-06-20） | `1d2d9969fa2d1f50` | 46.7KB | ✅ 用于 Debian 9 等老系统 |
| `fmmx-enhanced.sh` | [Fmmx/shadowsocks-libev-enhance](https://github.com/Fmmx/shadowsocks-libev-enhance) | `db49cb6c49911f6b` | 52.9KB | ❌ 不采用 |
| `idlm-enhanced.sh` | [idlm/shadowsocks_install](https://github.com/idlm/shadowsocks_install) | `98f0e5ba4db45706` | 33.6KB | ❌ 不采用 |
| `unknown-variant-48k.sh` | 本机 `/home/devs/` 残留，来源不明 | `02fbd4b5fd6fcce0` | 48KB | ❌ 仅存档 |

## 各脚本要点

### teddysun-master-2026-03-07.sh

2026-03-07 的重写版，**移除了全部源码编译逻辑**，改为 apt/dnf 仓库安装。

```text
声明支持   CentOS/RHEL 8+, Debian 11+, Ubuntu 20.04+
软件源     https://dl.lamp.sh/shadowsocks/{debian,ubuntu}/
公钥       https://dl.lamp.sh/shadowsocks/DEB-GPG-KEY-Teddysun
配置       /etc/shadowsocks/shadowsocks-{libev,rust}-config.json
服务       shadowsocks-libev-server / shadowsocks-rust-server
入口       ./shadowsocks-all.sh [install|uninstall]
新增能力   shadowsocks-rust、v2ray-plugin、xray-plugin
```

注意它**用版本号硬性拒绝 Debian 10**（脚本第 164 行附近），
但其 apt 仓库里实际是有 buster 包的 —— 本仓库正是利用这一点让 Debian 10 也能走仓库安装。

### teddysun-legacy-dab9bec7.sh

master 之前的最后一个版本，也是最后一个支持 Debian 7-10 的版本。

```text
声明支持   CentOS 6+, Debian 7+, Ubuntu 12+
形态       4-in-1（Python / R / Go / libev），源码编译
内部依赖   libsodium 1.0.18、mbedtls 2.16.12（2026-10-14 实测链接均存活）
配置       /etc/shadowsocks-{python,r,go,libev}/config.json
服务       /etc/init.d/shadowsocks-*（SysV）
入口       ./shadowsocks-all.sh [install|uninstall]
```

**网上流传的若干「Debian 9/10 备用」一键脚本与本文件字节完全一致。**
不要用那类第三方副本 —— 内容虽同，但静态站点的文件随时可被替换，而这是以 root 执行的
安装脚本。本仓库改用内容不可变的 GitHub commit URL：

```
https://raw.githubusercontent.com/teddysun/shadowsocks_install/dab9bec7/shadowsocks-all.sh
```

### fmmx-enhanced.sh / idlm-enhanced.sh

都是上述 legacy 版本的 fork，自称"支持 Debian 12/13"。不采用的理由：

- 官方仓库已原生覆盖 bookworm 与 trixie，它们的主要卖点已失效
- 仍是源码编译 + SysV init，比仓库安装慢且不可升级
- 含 Python / ShadowsocksR / Go 版本，均已停止维护
- 来源与维护状况无法核实

收益为零的情况下引入第三方 fork，只是单纯增加供应链风险。
需要 rust 或 v2ray/xray 插件时，用官方 master 脚本即可（`--mode teddysun`）。

### unknown-variant-48k.sh

本机 `/home/devs/shadowsocks-all.sh`，48082 字节，与任何已知上游版本都不一致。
推测是此前某次会话下载或改写过的中间产物。**不要使用**，仅作为考古线索保留 ——
本机 2025 年的安装形态可能与它有关。

## 怎么用这些副本排查问题

对照上游实际行为，而不是依赖文档描述：

```bash
# 配置文件路径
grep -nE "^shadowsocks_[a-z]+_config=" <脚本>

# 它创建什么服务
grep -nE 'systemctl (enable|start)|/etc/init.d/' <脚本>

# 卸载入口怎么调
grep -nE '^action=|install\|uninstall' <脚本>

# 内部要下载什么、链接还活着吗
grep -oE 'https?://[^"'"'"' ]+\.(tar\.gz|tar\.bz2)' <脚本> | sort -u
```

想确认某个副本是否仍与上游一致：

```bash
curl -fsSL https://raw.githubusercontent.com/teddysun/shadowsocks_install/master/shadowsocks-all.sh | sha256sum
sha256sum teddysun-master-2026-03-07.sh
```
