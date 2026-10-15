# Shadowsocks 全功能一键安装脚本

适用于 **Debian 9/10/11/12/13**、Ubuntu 18.04+、CentOS/RHEL 8+ 的 Shadowsocks 一键安装与管理脚本。

默认走 **Teddysun 官方 apt 仓库**安装（秒级、GPG 签名校验、可 `apt upgrade` 升级），
仓库未覆盖的老系统自动回落到上游一键脚本。默认加密 `aes-256-gcm`，自动随机端口与密码，
自动开启 BBR、放行防火墙、配置开机自启，并直接输出 `ss://` 链接与二维码。

---

## 一键命令

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks/install.sh)
```

备用（无 curl 时）：

```bash
wget -qO- https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks/install.sh | bash
```

执行后进入交互菜单。全自动静默安装：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks/install.sh) install -y
```

---

## 安装方式自动判定

| 系统 | 方式 | 说明 |
|------|------|------|
| Debian 10/11/12/13 | `repo` | Teddysun 官方 apt 仓库，`shadowsocks-libev 3.3.5-12`，秒装可升级 |
| Ubuntu 20.04/22.04/24.04/25.x | `repo` | 同上 |
| Debian 9、Ubuntu 18.04 | `legacy` | 上游旧版一键脚本，固定 commit `dab9bec7`（最后一个支持 Debian 7-10 的版本） |
| CentOS/RHEL/Rocky/AlmaLinux 8+ | `teddysun` | 上游 master 交互脚本 |
| 需要 rust 版 / v2ray / xray 插件 | `teddysun` | `--mode teddysun` 手工指定 |

判定依据是 Teddysun 仓库实际提供的发行版代号（`buster bullseye bookworm trixie` /
`focal jammy noble resolute`），不是硬编码版本号。详细选型依据见
[安装方式对照](docs/install-modes.md)。

---

## 功能

| 功能 | 说明 |
|------|------|
| 自动选择安装方式 | 以仓库实际覆盖范围为准，可用 `--mode` 覆盖 |
| GPG 指纹校验 | 导入 Teddysun 公钥时校验指纹 `8B22B39B...F704BE66`，不符即终止 |
| 默认加密 | `aes-256-gcm`，可选 `chacha20-ietf-poly1305` 等 |
| 随机参数 | 端口 10000-65000（自动避开占用端口），16 位随机密码 |
| IPv4 / IPv6 | 同时监听 `0.0.0.0` 与 `::0`，自动探测公网地址 |
| TCP + UDP | `mode: tcp_and_udp` |
| BBR | 自动检测内核并开启（内核 ≥ 4.9） |
| 防火墙 | 自动识别 ufw / firewalld / iptables 并放行端口 |
| 内核优化 | 写入 `/etc/sysctl.d/99-shadowsocks.conf`（文件句柄、队列、TFO） |
| 配置备份 | 每次变更前自动备份到 `/root/ss_backup`，仅保留最近 10 份 |
| 一键恢复 | 列出历史备份并选择恢复 |
| 连接信息 | 输出 `ss://` 链接（SIP002 格式）+ 终端二维码 |
| 多来源识别 | 自动识别 apt 包 / 上游脚本 / SysV / 源码编译四种安装结果 |
| 安装日志 | `/var/log/shadowsocks-install.log` |

---

## 管理菜单

直接运行脚本即可进入：

```text
   1) 安装 Shadowsocks
   2) 查看连接信息 / SS 链接
   3) 修改密码
   4) 修改端口
   5) 修改加密方式
   6) 重启服务
   7) 查看服务状态
   8) 查看运行日志
   9) 备份配置
  10) 恢复配置
  11) 开启 BBR 加速
  12) 重装（备份 → 卸载 → 安装）
  13) 卸载
   0) 退出
```

---

## 命令行用法

```bash
# 克隆后本地使用
git clone https://github.com/JXAB/CommonUserScripts.git
cd CommonUserScripts/shadowsocks

bash install.sh                                   # 交互菜单
bash install.sh install                           # 交互式安装
bash install.sh install --port 12345 -y           # 指定端口静默安装
bash install.sh install --mode teddysun           # 需要 rust / 插件时
bash install.sh install --port 12345 --password 'YourPass' --method aes-256-gcm -y

bash install.sh info          # 查看连接信息与 ss:// 链接
bash install.sh port          # 修改端口（自动放行新端口、回收旧端口）
bash install.sh password      # 修改密码
bash install.sh method        # 修改加密方式
bash install.sh restart       # 重启服务
bash install.sh status        # 服务状态
bash install.sh log           # 最近 50 行日志
bash install.sh backup        # 备份配置
bash install.sh restore       # 从备份恢复
bash install.sh bbr           # 检测并开启 BBR
bash install.sh reinstall     # 备份 → 卸载 → 重新安装
bash install.sh uninstall     # 卸载（按实际安装方式路由）
bash install.sh --help        # 帮助
```

等价的独立入口（内部转发到 `install.sh`，不重复实现逻辑）：

```bash
bash uninstall.sh   bash reinstall.sh   bash backup.sh   bash restore.sh
```

### 选项

| 选项 | 说明 |
|------|------|
| `--port <端口>` | 指定端口，默认随机且避开已占用端口 |
| `--password <密码>` | 指定密码，默认 16 位随机 |
| `--method <加密>` | 默认 `aes-256-gcm` |
| `--mode <方式>` | `auto`(默认) / `repo` / `teddysun` / `legacy` / `source` |
| `-y, --yes` | 跳过所有确认，用于无人值守 |

---

## 目录结构

```text
shadowsocks/
├── install.sh                 # 统一入口：子命令 + 交互菜单 + 远程模块引导
├── uninstall.sh               # 薄封装 → install.sh uninstall
├── reinstall.sh               # 薄封装 → install.sh reinstall
├── backup.sh                  # 薄封装 → install.sh backup
├── restore.sh                 # 薄封装 → install.sh restore
├── lib/
│   ├── common.sh              # 常量、日志、随机参数、ss:// 链接、JSON 读写
│   ├── system.sh              # 系统识别、安装方式路由、EOL 源修复、内核调优
│   ├── repo.sh                # Teddysun apt 仓库安装（默认方式）
│   ├── teddysun.sh            # 上游 master / legacy 脚本调用
│   ├── libev.sh               # 源码编译兜底
│   ├── bbr.sh                 # BBR 检测与开启
│   ├── firewall.sh            # ufw / firewalld / iptables 放行与回收
│   ├── config.sh              # 配置读写、连接信息、端口/密码/加密修改
│   └── backup.sh              # 备份、清理、列表、恢复
├── configs/
│   └── config-template.json   # 配置样例（供手工参考，脚本自动生成实际配置）
├── mirror/                    # Teddysun 官方包的本仓库备份（上游失效时自动回退）
│   ├── MANIFEST.txt           # 每个包的版本与 SHA256
│   ├── DEB-GPG-KEY-Teddysun   # 上游公钥副本
│   ├── debian/ ubuntu/        # shadowsocks-libev 的 deb（8 codename × amd64/arm64）
│   └── dists/                 # 上游签名的 InRelease 与 Packages 索引，供离线审计
├── tools/
│   ├── sync-mirror.sh         # 从上游同步镜像
│   └── verify-mirror.sh       # 校验镜像的完整信任链
├── tests/
│   └── os-detect-test.sh      # 离线验证 15 种场景的安装方式判定（不安装任何东西）
├── docs/
│   ├── install-modes.md       # 四种安装方式的对照与选型依据
│   └── faq.md
└── README.md
```

> 通过 `bash <(curl ...)` 远程执行时，`install.sh` 会自动把 `lib/` 下的模块下载到临时目录并在退出时清理，无需手动克隆仓库。

### 自检

```bash
bash tests/os-detect-test.sh    # 验证 Debian 9-14 / Ubuntu / RHEL 系的路由判定
bash tools/verify-mirror.sh     # 验证镜像的 GPG 签名与哈希链（40 项）
```

---

## 上游失效时的自动回退

`repo` 方式依赖 Teddysun 的 `dl.lamp.sh`。为避免上游域名到期、账号异常或被墙导致整个脚本不可用，
本仓库在 `mirror/` 下备份了 `shadowsocks-libev` 的全部安装包。

安装时的决策顺序：

```text
探测上游 InRelease 可达性
├─ 可达   → 走 apt 仓库安装（保留上游 GPG 签名验证）
└─ 不可达 → 回退到 mirror/，校验 SHA256 后用 apt 安装 deb
            本地有仓库副本时直接读磁盘，完全不依赖网络
```

镜像范围与理由：

| 项目 | 是否镜像 | 原因 |
|------|----------|------|
| `shadowsocks-libev` | ✅ 8 codename × amd64/arm64，共 16 个包 3.5MB | `repo` 方式实际安装的包 |
| `shadowsocks-rust` | ❌ | 每个 7-13MB，全量 140MB+，本脚本不安装它 |
| 依赖包（libsodium23 等） | ❌ | 均来自 Debian/Ubuntu 官方源，不随上游消失 |

完整性保障是三层的，`tools/verify-mirror.sh` 可随时复验：

1. 上游公钥验证 `InRelease` 的 GPG 签名
2. `InRelease` 中声明的哈希 == 镜像保存的 `Packages` 索引实际哈希
3. 每个 deb 的哈希 == `MANIFEST.txt` 记录 == 上游索引中给出的哈希

同步新版本：

```bash
bash tools/sync-mirror.sh              # 全部 codename
bash tools/sync-mirror.sh bookworm     # 只同步指定的
```

同步时会逐个对照上游索引的 SHA256，不符即中止；旧版本自动清理，避免仓库膨胀。

---

## 关键路径

| 安装方式 | 配置文件 | 服务 |
|----------|----------|------|
| `repo` / `teddysun`(libev) | `/etc/shadowsocks/shadowsocks-libev-config.json` | `shadowsocks-libev-server` |
| `teddysun`(rust) | `/etc/shadowsocks/shadowsocks-rust-config.json` | `shadowsocks-rust-server` |
| `legacy` | `/etc/shadowsocks-libev/config.json` | `/etc/init.d/shadowsocks-libev` |
| `source` | `/etc/shadowsocks-libev/config.json` | `shadowsocks-libev` |

| 其他 | 路径 |
|------|------|
| 配置备份 | `/root/ss_backup/<时间戳>-<原因>/` |
| 安装日志 | `/var/log/shadowsocks-install.log` |
| 内核优化 | `/etc/sysctl.d/99-shadowsocks.conf`、`/etc/sysctl.d/99-bbr.conf` |

---

## 常用运维命令

```bash
bash install.sh info                              # 配置与连接信息（推荐，自动识别路径）
systemctl status shadowsocks-libev-server         # apt 仓库安装
journalctl -u shadowsocks-libev-server -n 50      # 查看日志
apt upgrade shadowsocks-libev                     # 升级（仅 repo 方式）
```

---

## 安全提示

- 配置文件权限为 `600`，仅 root 可读；备份目录同样限制权限。
- `ss://` 链接内含密码，请勿公开分享或提交到仓库。
- 修改端口后旧端口的防火墙放行会被自动回收。
- 脚本只从 GitHub 官方仓库与 Teddysun 官方源获取内容，不使用任何第三方镜像站，
  旧版脚本以 commit SHA 固定，内容不可变。

---

## 文档

- [安装方式对照与选型依据](docs/install-modes.md)
- [常见问题 FAQ](docs/faq.md)
- [old-dev/ 开发过程归档](old-dev/) —— 排查手册、核验记录、上游脚本副本、本机考古结论

## 致谢

- [shadowsocks-libev](https://github.com/shadowsocks/shadowsocks-libev)
- [teddysun/shadowsocks_install](https://github.com/teddysun/shadowsocks_install)
