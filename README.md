# Tiny Service Panel

Tiny Service Panel 是一个轻量 Linux systemd 服务管理面板，用来查看 systemd 服务状态、CPU/内存占用，并执行启动、停止、重启等操作。

它默认使用 **systemd socket activation**：开机只启动一个 socket 监听，Python 后端只有在访问面板/API 时才会被 systemd 拉起，空闲后自动退出。

## 功能

- 列出 systemd units
- 按服务聚合内存 RSS 和 CPU 占用
- 支持 start / stop / restart systemd 服务
- 支持收藏和备注
- 支持隐藏常见 systemd 噪音项
- 默认监听 `127.0.0.1:8765`
- 支持一键安装和一键卸载

## 一键安装

在服务器上执行：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo bash
```

换端口：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo env PORT=9876 bash
```

安装后验证：

```bash
curl http://127.0.0.1:8765/api/summary
systemctl status tiny-service-panel.socket --no-pager -l
```

默认安装到：

```text
/opt/tiny-service-panel
```

systemd 文件：

```text
/etc/systemd/system/tiny-service-panel.socket
/etc/systemd/system/tiny-service-panel.service
```

## 如何访问

默认只监听本机地址：

```text
127.0.0.1:8765
```

所以不能直接用公网 IP 访问 `公网IP:8765`。推荐用 SSH 隧道：

```bash
ssh -L 8765:127.0.0.1:8765 user@server_ip
```

然后在本地浏览器打开：

```text
http://127.0.0.1:8765
```

不建议裸露到公网，因为这个面板可以控制 systemd 服务。

## 本地离线安装

如果服务器不能直接访问 GitHub，可以先在本地下载仓库压缩包和本地安装脚本，再上传到服务器：

```bash
curl -L -o tiny-service-panel.tar.gz https://github.com/fenghuixianyu/tiny-service-panel/archive/refs/heads/main.tar.gz
curl -fsSL -o install-local.sh https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-local.sh
scp tiny-service-panel.tar.gz install-local.sh user@server:~/
```

服务器上执行：

```bash
bash install-local.sh tiny-service-panel.tar.gz
```

如果直接使用本项目生成的迁移包，也可以上传这两个文件：

```text
tiny-service-panel.tar.gz
install-local.sh
```

然后执行同样的命令。

## 一键卸载

```bash
sudo bash /opt/tiny-service-panel/uninstall.sh
```

卸载脚本会清理：

```text
systemd socket/service 状态
/etc/systemd/system/tiny-service-panel.socket
/etc/systemd/system/tiny-service-panel.service
/etc/systemd/system/sockets.target.wants/tiny-service-panel.socket
/etc/systemd/system/multi-user.target.wants/tiny-service-panel.service
/opt/tiny-service-panel
/opt/tiny-service-panel.bak.*
```

如果想保留历史备份目录：

```bash
sudo REMOVE_BACKUPS=0 bash /opt/tiny-service-panel/uninstall.sh
```

卸载后验证：

```bash
systemctl status tiny-service-panel.socket --no-pager
ss -lntp | grep 8765
```

正常情况下，systemd 会提示找不到对应 unit，且 8765 没有监听。

## 常用命令

```bash
# 查看 socket 状态
systemctl status tiny-service-panel.socket --no-pager -l

# 查看后端服务日志
journalctl -u tiny-service-panel.service -n 100 --no-pager

# 重新安装/升级
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo bash

# 换端口重装
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo env PORT=9876 bash
```

## 私有仓库能不能一键安装？

可以，但不能像公开仓库一样匿名下载。私有仓库下载 `raw.githubusercontent.com` 或源码压缩包时需要 GitHub Token，例如：

```bash
GITHUB_TOKEN=你的token
curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  https://raw.githubusercontent.com/OWNER/REPO/main/install-online.sh | sudo bash
```

这会让安装命令变复杂，也容易在 shell history 里留下 token。为了多台服务器快捷安装，本项目建议公开仓库；不要把服务器密钥、Token、私有配置提交到仓库。

## 安全提醒

此面板默认以 root 运行，能够执行 `systemctl start/stop/restart`。建议只放在本机、内网、VPN、Cloudflare Access、Tailscale/WireGuard 或 SSH 隧道后面，不要裸露到公网。

## 项目结构

```text
server.py                         # HTTP 后端
tiny_service_panel/               # 核心逻辑
static/                           # 前端页面
install-online.sh                 # GitHub 一键在线安装
install-local.sh                  # 本地压缩包安装
install.sh                        # 写入 systemd unit 并启用 socket
uninstall.sh                      # 一键卸载
docs/                             # 设计文档
```
