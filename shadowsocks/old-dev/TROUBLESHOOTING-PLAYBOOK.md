# 排查手册

按症状组织，命令可直接复制执行。所有命令都在 Debian 10 真机上跑过。

---

## 先做这三步

```bash
bash install.sh info                 # 实例清单、端口、服务状态（会列出全部实例）
systemctl list-unit-files | grep shadow
ss -lntup | grep ss-server
```

`info` 能正常输出说明配置和服务都认得出来，问题多半在网络层；
`info` 报"未检测到"说明脚本没认出安装形态，看 §3。

---

## 1. 客户端连不上

排查顺序是**从里到外**，先证明服务端自己是好的：

```bash
# 1) 服务在跑吗
systemctl is-active shadowsocks-libev-server

# 2) 端口真的在监听吗（注意要有 tcp 和 udp）
ss -lntup | grep '<端口>'

# 3) 本机自己能不能走通 —— 这一步最关键
/usr/bin/ss-local -s 127.0.0.1 -p <端口> -l 10808 -k '<密码>' -m aes-256-gcm -f /tmp/ssl.pid
curl -s --max-time 15 --socks5-hostname 127.0.0.1:10808 https://api.ipify.org
kill "$(cat /tmp/ssl.pid)"; rm -f /tmp/ssl.pid
```

第 3 步能返回服务器 IP → **服务端完全正常，问题在外部**：

- 云厂商安全组没放行（脚本改不了控制台，必须手工放行 TCP + UDP）
- 本地防火墙：`iptables -L INPUT -n | grep <端口>`
- IP 被墙：换端口通常没用，需要换 IP 或加伪装插件

第 3 步不通 → 看服务端日志：

```bash
journalctl -u shadowsocks-libev-server -n 50 --no-pager
```

---

## 2. 装上了但服务起不来

```bash
systemctl status shadowsocks-libev-server --no-pager
journalctl -u shadowsocks-libev-server -n 50 --no-pager
```

常见原因：

| 现象 | 原因 | 处理 |
|------|------|------|
| `bind: Address already in use` | 端口被占 | `ss -lntup \| grep <端口>` 看谁占了 |
| `invalid config file` | JSON 语法错 | `python3 -m json.tool <配置文件>` |
| 起来又立刻退出 | 加密方式不被支持 | 改回 `aes-256-gcm` |

手工前台跑一次能看到最直接的报错：

```bash
/usr/bin/ss-server -c /etc/shadowsocks/shadowsocks-libev-config.json -v
```

---

## 3. 脚本认不出已有安装

脚本靠「配置文件路径 + 服务名」的组合识别，共四种形态：

| 安装来源 | 配置文件 | 服务 |
|----------|----------|------|
| apt 仓库 / teddysun master | `/etc/shadowsocks/shadowsocks-libev-config.json` | `shadowsocks-libev-server` |
| teddysun rust | `/etc/shadowsocks/shadowsocks-rust-config.json` | `shadowsocks-rust-server` |
| legacy 脚本 | `/etc/shadowsocks-libev/config.json` | `/etc/init.d/shadowsocks-libev` |
| 源码编译 | `/etc/shadowsocks-libev/config.json` | `shadowsocks-libev` |

出现新形态时这样确认，再把组合补进 `lib/common.sh` 的 `ss_install_map`：

```bash
ls -l /etc/shadowsocks* /etc/init.d/shadowsocks* 2>/dev/null
systemctl list-unit-files | grep shadow
dpkg -l | grep shadowsocks
readlink -f /proc/$(pgrep -x ss-server | head -1)/exe    # 二进制到底是哪个
```

最后一条特别有用 —— 能区分 `/usr/bin/ss-server`（apt 包）和
`/usr/local/bin/ss-server`（源码或 legacy 编译）。

---

## 4. apt 安装失败

```bash
# 源配置对不对
cat /etc/apt/sources.list.d/teddysun.list

# 上游通不通
curl -fsI https://dl.lamp.sh/shadowsocks/debian/dists/$(. /etc/os-release; echo $VERSION_CODENAME)/InRelease

# 签名有没有问题
apt-get update 2>&1 | grep -iE 'NO_PUBKEY|not signed|GPG error'

# 依赖能不能解析（模拟，不实际装）
apt-get install -s shadowsocks-libev
```

上游不可达时脚本会自动回退到 `mirror/`。手工强制走镜像：

```bash
# 查本机对应的包
. /etc/os-release
grep "^${VERSION_CODENAME}|$(dpkg --print-architecture)|" mirror/MANIFEST.txt
# 校验后安装
sha256sum mirror/<路径>
apt-get install -y ./mirror/<路径>
```

### Debian 9/10 报 404 或证书过期

这两个系统已 EOL，官方源已下线，必须切到归档源：

```bash
cp /etc/apt/sources.list /etc/apt/sources.list.bak
cat >/etc/apt/sources.list <<'EOF'
deb http://archive.debian.org/debian/ buster main contrib non-free
deb http://archive.debian.org/debian-security buster/updates main contrib non-free
EOF
echo 'Acquire::Check-Valid-Until "false";' >/etc/apt/apt.conf.d/99no-check-valid-until
apt-get update
```

脚本的 `fix_eol_apt_sources` 会自动做这件事。

---

## 5. 不改动系统的前提下验证 apt 行为

排查生产机时非常有用 —— 全程只写 `/tmp`：

```bash
TD=/tmp/aptest; rm -rf $TD; mkdir -p $TD/lists/partial $TD/etc/preferences.d
cp /etc/apt/sources.list $TD/etc/sources.list
# 需要额外源就追加到 $TD/etc/sources.list
OPTS="-o Dir::Etc::sourcelist=$TD/etc/sources.list -o Dir::Etc::sourceparts=/dev/null \
      -o Dir::State::lists=$TD/lists -o Dir::Etc::preferencesparts=$TD/etc/preferences.d"
apt-get $OPTS update
apt-get $OPTS -s install <包名>
apt-cache $OPTS policy <包名>
```

---

## 6. 多实例相关

```bash
bash install.sh info                       # 列出全部实例
bash install.sh status   --target <端口>   # 指定实例
bash install.sh password --target <端口>
bash install.sh uninstall --target <端口>  # 只拆这一个
```

非交互（`-y`）且存在多个实例时，脚本会**拒绝执行并列出候选**，这是刻意设计的：
防止误改到正在使用的节点。

apt 包自带多实例模板单元，手工加第二个节点：

```bash
cp /etc/shadowsocks/shadowsocks-libev-config.json /etc/shadowsocks/node2.json
# 编辑 node2.json 改端口和密码
systemctl enable --now shadowsocks-libev-server@node2
```

---

## 7. 备份与回滚

```bash
bash install.sh backup                 # 备份全部实例
ls /root/ss_backup/                    # 历史备份（自动保留最近 10 份）
bash install.sh restore                # 选择并还原
```

动生产机之前，额外做一份脚本管不到的快照：

```bash
SNAP=/root/ss_rollback_$(date +%Y%m%d-%H%M%S); mkdir -p "$SNAP"
cp -a /etc/shadowsocks* "$SNAP/" 2>/dev/null
cp -a /etc/systemd/system/shadowsocks-*.service "$SNAP/" 2>/dev/null
cp -a /etc/init.d/shadowsocks-* "$SNAP/" 2>/dev/null
tar czf "$SNAP/local-bin.tar.gz" -C / usr/local/bin/ss-server 2>/dev/null
dpkg -l | grep shadowsocks > "$SNAP/dpkg.txt"
```

回滚（源码/legacy 形态）：

```bash
tar xzf "$SNAP/local-bin.tar.gz" -C /
cp -a "$SNAP/shadowsocks-libev.service" /etc/systemd/system/
mkdir -p /etc/shadowsocks-libev && cp -a "$SNAP/config.json" /etc/shadowsocks-libev/
systemctl daemon-reload && systemctl enable --now shadowsocks-libev
```

---

## 8. BBR / 内核

```bash
sysctl net.ipv4.tcp_congestion_control    # 期望 bbr
lsmod | grep bbr
uname -r                                  # 需要 >= 4.9
cat /etc/sysctl.d/99-bbr.conf /etc/sysctl.d/99-shadowsocks.conf
```

OpenVZ / LXC 架构的 VPS 开不了 BBR，需要 KVM。配置写进去了但要重启才生效的情况也常见。

---

## 9. 镜像完整性

```bash
bash tools/verify-mirror.sh     # 三环校验，当前应为 40/40
bash tools/sync-mirror.sh       # 上游出新版时重新同步
```

校验失败说明镜像件与上游签名内容不符，**不要继续使用**，先重新同步。

---

## 10. 低内存机器（≤512MB）的坑

本机在开发过程中实际遇到的：

| 症状 | 原因 | 处理 |
|------|------|------|
| `git push` 报 `Out of memory, malloc failed` | git 默认 pack 内存远超可用 | `git config pack.windowMemory 16m; git config pack.threads 1` |
| 编译 mbedtls 中途被杀 | OOM killer | 先加 swap，或改用 `--mode repo` 根本不编译 |
| 偶发 fork 失败导致测试假阴性 | 内存紧张 | 复跑几次确认是否稳定复现 |

加 swap：

```bash
fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
```
