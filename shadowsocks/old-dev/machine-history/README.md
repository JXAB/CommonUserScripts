# 本机安装形态考古

记录 2026-10-15 重装之前，这台 Debian 10 上原有安装的形态。
价值在于：**同一台机器上可能叠着好几层历史安装**，排查时得先搞清楚现状是怎么来的。

## 结论

原有安装是 **2025-02-28 用 teddysun legacy 脚本装的**，不是源码编译，
后来（2026-10-14 上午）又被手工加了一个 systemd 单元。

判断依据：

```bash
$ ls -l /etc/init.d/shadowsocks-libev
-rwxr-xr-x 1 root root 2125 Feb 28  2025 /etc/init.d/shadowsocks-libev

$ ls -l /lib/libmbedcrypto.so.3
-rwxr-xr-x 1 root root 529992 Feb 28  2025 /lib/libmbedcrypto.so.3

$ dpkg -S /lib/libmbedcrypto.so.3
dpkg-query: no path found matching pattern       # 不属于任何包 → 源码编译装的

$ ls -l --time-style=full-iso /etc/systemd/system/shadowsocks-libev.service
-rw-r--r-- 1 root root 328 2026-10-14 10:08:36   # 比 init.d 晚一年半
```

`/etc/init.d/` 脚本 + `/lib/` 下不属于任何 dpkg 包的 mbedtls，
正是 legacy 脚本「现场编译 libsodium 与 mbedtls」的典型痕迹。

### 这个判断为什么重要

一开始我按"源码编译"来理解这台机器，设计卸载逻辑时差点按错误前提走。
实际卸载时脚本判定为 `legacy`，当时我以为是误判，核实后发现**脚本是对的，我的认知是错的**。

教训：**判断安装形态要靠文件系统证据，不要靠记忆或他人描述。** 三条最有用的证据：

```bash
readlink -f /proc/$(pgrep -x ss-server | head -1)/exe   # 跑的是哪个二进制
dpkg -S <那个二进制路径>                                  # 属不属于某个包
ls -l --time-style=full-iso /etc/init.d/shadowsocks-* /etc/systemd/system/shadowsocks-*
```

## 残留文件

| 文件 | 说明 |
|------|------|
| `shadowsocks-libev.service.orig` | 2026-10-14 上午被加上的 systemd 单元，指向 `/usr/local/bin/ss-server` |
| `config.json.redacted` | 原配置，**密码已脱敏** |

原 `/etc/init.d/shadowsocks-libev` 随卸载删除，未留存。
需要参考其内容的话，它由 [`../upstream-scripts/teddysun-legacy-dab9bec7.sh`](../upstream-scripts/teddysun-legacy-dab9bec7.sh) 生成。

## 新旧形态对比

| 维度 | 原有（legacy，2025-02） | 现在（apt 仓库，2026-10） |
|------|------------------------|--------------------------|
| 二进制 | `/usr/local/bin/ss-server`（自行编译） | `/usr/bin/ss-server`（dpkg 管理） |
| 版本 | 3.3.5 | 3.3.5-12~debian.10~buster |
| 加密库 | `/lib/libmbedcrypto.so.3`，无包归属 | 系统 `libmbedtls` 包 |
| 服务 | `/etc/init.d/` + 后加的 systemd 单元 | `shadowsocks-libev-server.service` |
| 配置 | `/etc/shadowsocks-libev/config.json` | `/etc/shadowsocks/shadowsocks-libev-config.json` |
| 监听 | 仅 IPv4 | IPv4 + IPv6 |
| 升级 | 只能重新编译 | `apt upgrade` |

重装时沿用了原端口与原密码，客户端配置无需改动。
