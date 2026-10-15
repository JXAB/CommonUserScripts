# 开发日志与核验记录

记录时间：2026-10-14 ~ 2026-10-15
验证环境：Debian 10 (buster)，amd64，483MB 内存 / 1 核 / 15GB 磁盘

本文只记录**经过实际核验的结论**和**产生过代价的教训**，不记录没验证过的推测。
每条结论都附当时的核验方法，以后怀疑它过期了，照着重跑一遍即可。

---

## 1. 起点：最初的方案是错的

最早的设计是「Debian 9/10 源码编译 + Debian 11/12/13 调上游脚本」。
这个分法来自一个未经核实的假设：**老系统的仓库里没有 shadowsocks 包，只能自己编译**。

实际核验后发现假设不成立，见 §2。这是整个开发过程中最大的一次方向修正 ——
教训是：**路由规则不要按版本号硬编码猜测，要以仓库实际提供的内容为准**。

---

## 2. 关键发现：Teddysun 官方 apt 仓库覆盖 Debian 10

Teddysun 在 2026-03-07 重写了 `shadowsocks-all.sh`，**移除了全部源码编译逻辑**
（libsodium、mbedtls），改为从自建 apt/dnf 仓库安装。

核验过程：

```bash
# 仓库提供哪些发行版
curl -fsSL https://dl.lamp.sh/shadowsocks/debian/dists/ | sed -n 's/.*href="\([^"]*\)\/".*/\1/p'
# → buster bullseye bookworm trixie
curl -fsSL https://dl.lamp.sh/shadowsocks/ubuntu/dists/ | sed -n 's/.*href="\([^"]*\)\/".*/\1/p'
# → focal jammy noble resolute

# 具体有哪些包
curl -fsSL https://dl.lamp.sh/shadowsocks/debian/dists/buster/main/binary-amd64/Packages \
  | grep -A1 '^Package: shadowsocks'
# → shadowsocks-libev 3.3.5-12~debian.10~buster, shadowsocks-rust
```

**buster（Debian 10）在列表里**，所以 Debian 10 根本不需要编译。

依赖是否齐全（全部来自 Debian 归档源，非 Teddysun）：

```
libcap2-bin lsb-base libbloom1 libc-ares2 libc6 libcork16
libcorkipset1 libev4 libjsonparser1.1 libmbedtls-dev libpcre3 libsodium23
```

不写系统任何文件的前提下做完整验证（这个手法很有用，排查时可复用）：

```bash
TD=/tmp/aptest; mkdir -p $TD/lists/partial $TD/etc/preferences.d
gpg --dearmor -o $TD/key.gpg teddysun-pubkey.asc
cp /etc/apt/sources.list $TD/etc/sources.list
echo "deb [arch=amd64 signed-by=$TD/key.gpg] https://dl.lamp.sh/shadowsocks/debian/ buster main" >> $TD/etc/sources.list
OPTS="-o Dir::Etc::sourcelist=$TD/etc/sources.list -o Dir::Etc::sourceparts=/dev/null \
      -o Dir::State::lists=$TD/lists -o Dir::Etc::preferencesparts=$TD/etc/preferences.d"
apt-get $OPTS update          # 会做 GPG 签名校验
apt-get $OPTS -s install shadowsocks-libev   # 模拟安装，验证依赖可解析
```

结果：签名校验无错误，依赖全部可满足。

**为什么改用仓库安装（相对源码编译）**：

- 秒级完成，不需要 build-essential 等编译依赖
- 低内存机器不会 OOM —— 本机只剩 ~100MB 可用内存，编译 mbedtls 大概率被 OOM killer 打断
- 可以 `apt upgrade` 升级，源码编译装完就固定在那个版本
- Debian 10-13 与 Ubuntu 各版本走同一条代码路径，只有一处要维护

GPG 公钥指纹（脚本里硬校验这个值，不符即终止，上游脚本没做这一步）：

```
8B22B39B30A0E20328FD16A5A930C227F704BE66
Teddysun (Teddysun Repository) <i@teddysun.com>
```

---

## 3. 第三方脚本评估

评估了 5 个脚本，副本都在 [upstream-scripts/](upstream-scripts/)。

| 脚本 | sha256 前缀 | 结论 |
|------|-------------|------|
| teddysun master (2026-03-07) | `0852aa568f2f9c51` | ✅ 采用，用于 RHEL 系与插件/rust 场景 |
| teddysun legacy `dab9bec7` (2022-06-20) | `1d2d9969fa2d1f50` | ✅ 采用，用于 Debian 9 等仓库未覆盖的老系统 |
| Fmmx enhanced | `db49cb6c49911f6b` | ❌ 不采用 |
| idlm enhanced | `98f0e5ba4db45706` | ❌ 不采用 |
| 来源不明的 48K 变体 | `02fbd4b5fd6fcce0` | ❌ 不采用，仅存档 |

网上流传的「Debian 9/10 备用」一键脚本，经校验与 teddysun@`dab9bec7` **字节完全一致**
（sha256 均为 `1d2d9969fa2d1f50...`）。因此不使用那类第三方副本，改用：

```
https://raw.githubusercontent.com/teddysun/shadowsocks_install/dab9bec7/shadowsocks-all.sh
```

内容相同、来源可信，而且 **commit URL 的内容不可变**。第三方静态站点的文件可以随时被替换，
而这是以 root 身份执行的安装脚本，被换掉就是整机失陷。

**为什么不用 Fmmx / idlm 增强版**：两者主要卖点是"支持 Debian 12/13"，但官方仓库已原生覆盖
bookworm 与 trixie（§2 已验证）。它们仍是源码编译 + SysV init，且含已停止维护的
Python/R/Go 版本。在收益为零的情况下引入来源不明的 fork，只增加供应链风险。

**legacy 脚本的内部依赖链接是否还活着**（2026-10-14 实测，均 200）：

```
https://github.com/jedisct1/libsodium/releases/download/1.0.18-RELEASE/libsodium-1.0.18.tar.gz
https://github.com/Mbed-TLS/mbedtls/archive/refs/tags/v2.16.12.tar.gz
```

---

## 4. 上游集成点（容易踩的地方）

| 项目 | 值 |
|------|-----|
| 新脚本/apt 包的服务名 | `shadowsocks-libev-server`、`shadowsocks-rust-server`（**带 `-server` 后缀**） |
| 新脚本/apt 包的配置 | `/etc/shadowsocks/shadowsocks-libev-config.json` |
| legacy 脚本的服务 | `/etc/init.d/shadowsocks-libev`（SysV，systemd 会生成同名 unit） |
| legacy 脚本的配置 | `/etc/shadowsocks-libev/config.json` |
| apt 包的 systemd 单元 | `Type=forking`，`ExecStart=/usr/bin/ss-server -c <conf> -f <pid>` |
| apt 包的多实例模板 | `shadowsocks-libev-server@.service`，读 `/etc/shadowsocks/%i.json` |
| 上游脚本的卸载入口 | `./shadowsocks-all.sh uninstall`（master 与 legacy 都支持） |

**踩过的坑**：最初 `detect_service` 只匹配 `shadowsocks-libev`（而且带 `^` 锚定），
导致 Debian 11/12/13 装完后 `info`/`restart`/`port`/`password` 全部报"未检测到服务"。
排查方法：

```bash
grep -nE 'systemctl (enable|start)' shadowsocks-all.sh
systemctl list-unit-files | grep shadow
```

---

## 5. 真机验证记录（Debian 10）

### 5.1 apt 仓库安装（通过）

```
包      shadowsocks-libev 3.3.5-12~debian.10~buster
服务    shadowsocks-libev-server active
监听    IPv4 + IPv6，TCP + UDP
流量    ss-local 走通，curl 经 SOCKS5 出站正常，HTTP 200
```

端到端流量验证手法（排查"装上了但连不上"时最有用）：

```bash
/usr/bin/ss-local -s 127.0.0.1 -p <端口> -l 10808 -k '<密码>' -m aes-256-gcm -f /tmp/ssl.pid
curl -s --socks5-hostname 127.0.0.1:10808 https://api.ipify.org
kill "$(cat /tmp/ssl.pid)"
```

### 5.2 完整的拆除 → 重装（通过）

拆掉 2025 年的 legacy 安装（init.d + `/usr/local/bin` + 后加的 systemd 单元），
用 apt 仓库重装到**原端口、原密码**，客户端无需改任何配置。

重装前务必先做回滚快照：

```bash
SNAP=/root/ss_rollback_$(date +%Y%m%d-%H%M%S); mkdir -p "$SNAP"
cp -a /etc/shadowsocks-libev/config.json "$SNAP/"
cp -a /etc/systemd/system/shadowsocks-libev.service "$SNAP/"
tar czf "$SNAP/local-bin.tar.gz" -C / usr/local/bin/ss-server
tar czf "$SNAP/mbedtls-libs.tar.gz" -C / lib/libmbedcrypto.so.3 lib/libmbedcrypto.so
```

本次没用上回滚，但这一步是敢动生产机的前提。

---

## 6. 修过的 bug（都是真机才暴露的）

### 6.1 `set -euo pipefail` 下网络探测失败会中止整个脚本

```bash
ip=$(curl -fsS4 ... | tr -d '[:space:]')   # curl 失败 → pipefail → 整脚本退出(码 7)
```

修法：这类"失败也要继续"的取值一律加 `|| true`，并对结果做格式校验。

### 6.2 日志污染函数返回值 ← 最隐蔽

`teddysun_fetch` 用 stdout 返回脚本路径，而函数内部的 `info` 也写 stdout，
命令替换把日志一起吃进去，结果变成"日志文本+路径"，执行时报 `No such file or directory`。

**根治**：`info/warn/err/title` 一律写 stderr，stdout 只留给返回值。
写 shell 函数时这是条应该默认遵守的规则。

### 6.3 `pkill -f` 误杀无关进程 ← 最危险

```bash
pkill -f '/usr/local/bin/ss-server'
```

`-f` 匹配**整条命令行**，任何命令行里恰好含这个路径的进程都会被杀 ——
实测把调用它的 shell 杀掉了（exit 144）。

正确做法：

```bash
for pid in $(pgrep -x ss-server); do
    [[ "$(readlink -f /proc/$pid/exe)" == "/usr/local/bin/ss-server" ]] && kill "$pid"
done
```

### 6.4 多实例并存时误操作到另一个节点

`detect_conf` 取首个匹配，两个实例并存时 `info` 显示错节点，
`port`/`password` 会改到**正在使用的生产节点**上。

修法：只读操作展示全部实例；写操作必须经 `select_install` 选定目标，
非交互且未指定 `--target` 时直接拒绝并列出候选。

### 6.5 命令替换吃掉文件末尾换行

```bash
pkgs=$(curl ... Packages); printf '%s' "$pkgs" > Packages-amd64
```

存下来的索引少了末尾换行，sha256 与 `InRelease` 中声明的对不上，镜像审计链断裂。
改为 `curl -o` 直接落盘。**凡是要保持字节精确的文件，绝不要过 `$(...)`**。

### 6.6 委托交互式脚本做卸载，无法无人值守

legacy 安装原本委托上游脚本的 `uninstall`，但那是交互式的。
改为本地确定性拆除：systemd 单元 → init.d 脚本 → rc.d 链接 → 二进制 → 配置。

---

## 7. 镜像备份的设计取舍

上游 `dl.lamp.sh` 失效会让 `repo` 方式整体不可用，故将包备份到 `shadowsocks/mirror/`。

| 项目 | 决定 | 理由 |
|------|------|------|
| `shadowsocks-libev` | 镜像（16 个包 3.5MB） | repo 方式实际安装的包 |
| `shadowsocks-rust` | 不镜像 | 每个 7-13MB，全量 140MB+，本脚本不装它 |
| 依赖包 | 不镜像 | 来自 Debian/Ubuntu 官方源，不随上游消失 |

信任链三环（`tools/verify-mirror.sh` 可复验，当前 40/40）：

1. 上游公钥验证 `InRelease` 的 GPG 签名
2. `InRelease` 声明的哈希 == 镜像保存的 `Packages` 实际哈希
3. deb 哈希 == `MANIFEST.txt` == 上游索引中的哈希

**镜像是快照**，上游出安全更新不会自动跟进，需定期 `bash tools/sync-mirror.sh`。

---

## 8. 尚未验证的部分

截至归档时，**只有 Debian 10 做过真机验证**。以下仅通过离线路由测试（15/15）与资料核对：

| 系统 | 风险评估 |
|------|----------|
| Debian 11/12/13 | 低 —— 与 Debian 10 是同一条代码路径，仅 codename 不同，包已确认存在 |
| Ubuntu 20.04/22.04/24.04 | 低 —— 同上 |
| Debian 9 / Ubuntu 18.04 | 中 —— legacy 路径，且上游脚本是交互式的，无法 `-y` 无人值守 |
| RHEL / CentOS / Rocky / Alma | 中 —— 同样是交互式上游脚本 |

另外这几项功能尚未实现：多实例**安装**（只支持识别与管理）、rust 版直装、
v2ray/xray 插件配置、多用户（`port_password`）。
