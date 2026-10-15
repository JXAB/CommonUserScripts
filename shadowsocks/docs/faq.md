# 常见问题 FAQ

## 1. 客户端连不上

按顺序排查：

```bash
bash install.sh status                      # 服务是否 active
ss -lntup | grep ss-server                  # 端口是否在监听
bash install.sh log                         # 是否有报错
```

若服务正常但仍连不上，多半是**云厂商安全组**未放行端口（脚本只能配置系统防火墙，改不了云控制台）。
请在 VPS 控制台的安全组中放行对应端口的 **TCP 和 UDP**。

## 2. 端口被占用

安装时的随机端口会自动跳过已占用端口。手工指定端口若被占用，脚本会直接报错：

```bash
bash install.sh install --port 12345 -y
```

查看占用：

```bash
ss -lntup | grep ':12345'
```

## 3. 修改端口后旧端口还通

脚本修改端口时会放行新端口并回收旧端口的防火墙规则，但云厂商安全组需要手工同步。

## 4. Debian 9/10 执行 apt-get 报 404 / 证书过期

这两个系统已 EOL，脚本会自动把源切换到 `archive.debian.org` 并关闭 `Valid-Until` 校验。
若此前手工改过源，脚本检测到已包含 `archive.debian.org` 就会跳过。原文件备份为
`/etc/apt/sources.list.bak.<时间戳>`。

注意 Debian 10 默认走 apt 仓库安装（不编译），但基础依赖仍来自归档源，所以这一步仍然必要。

## 5. GPG 公钥指纹不匹配

报错 `GPG 公钥指纹不匹配` 说明从 `dl.lamp.sh` 取到的公钥不是预期的那把
（`8B22B39B30A0E20328FD16A5A930C227F704BE66`）。这可能是上游轮换了密钥，也可能是
网络被劫持。**不要绕过这个检查**，先手工核对：

```bash
curl -fsSL https://dl.lamp.sh/shadowsocks/DEB-GPG-KEY-Teddysun | gpg --show-keys
```

确认无误后再更新 `lib/repo.sh` 里的 `TEDDY_GPG_FPR`。

## 6. 编译失败（legacy / source 方式）

完整日志在 `/var/log/shadowsocks-install.log`：

```bash
tail -n 100 /var/log/shadowsocks-install.log
```

常见原因是依赖缺失或内存不足。512MB 以下的机器编译 mbedtls 容易被 OOM killer 打断，
建议先加 swap：

```bash
fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
```

如果系统在 Teddysun 仓库覆盖范围内（Debian 10-13 / Ubuntu 20.04+），优先用
`--mode repo`，根本不需要编译。

## 7. BBR 没生效

```bash
sysctl net.ipv4.tcp_congestion_control    # 期望输出 bbr
lsmod | grep bbr
uname -r                                  # 需要 >= 4.9
```

OpenVZ / LXC 架构的 VPS 无法开启 BBR，需要 KVM。配置已写入 `/etc/sysctl.d/99-bbr.conf`，
部分系统需要重启后生效。

## 8. 没有显示二维码

二维码依赖 `qrencode`：

```bash
apt-get install -y qrencode     # Debian/Ubuntu
```

安装后重新执行 `bash install.sh info`。

## 9. 备份放在哪里，会不会无限增长

备份目录 `/root/ss_backup/<时间戳>-<原因>/`，包含配置文件、systemd 单元和 `meta.txt`。
脚本仅保留**最近 10 份**，超出自动清理。

恢复：

```bash
bash install.sh restore
```

## 10. 如何完全重装

```bash
bash install.sh reinstall
```

流程：自动备份 → 卸载 → 重新安装 → 输出新的连接信息。

## 11. 想换加密方式

```bash
bash install.sh method
```

支持 `aes-256-gcm`、`aes-192-gcm`、`aes-128-gcm`、`chacha20-ietf-poly1305`、`xchacha20-ietf-poly1305`。
ARM 等无 AES 硬件加速的机器建议使用 `chacha20-ietf-poly1305`。
