# Tiny Service Panel 迁移包

这是 Tiny Service Panel 的可迁移安装包，已移除原服务器信息：

- 不包含原服务器域名、Cloudflare 配置、主机名等部署信息。
- `data/metadata.json` 已重置为空收藏/空备注。
- 不包含 Python `__pycache__`、`.pyc` 等运行缓存。

## GitHub 在线安装

如果服务器可以访问 GitHub，推荐直接执行：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo bash
```

换端口：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo env PORT=9876 bash
```

## 推荐：本地一键安装

把下面两个文件上传到服务器的个人目录即可，例如 `/home/你的用户/` 或 `/root/`：

- `tiny-service-panel.tar.gz`
- `install-local.sh`

卸载脚本 `uninstall.sh` 已包含在安装包里，安装后会位于 `/opt/tiny-service-panel/uninstall.sh`。

然后执行：

```bash
bash install-local.sh tiny-service-panel.tar.gz
```

如需换端口：

```bash
PORT=9876 bash install-local.sh tiny-service-panel.tar.gz
```

脚本会自动使用 `sudo` 提权，把程序安装到：

```text
/opt/tiny-service-panel
```

并写入 systemd 文件：

```text
/etc/systemd/system/tiny-service-panel.socket
/etc/systemd/system/tiny-service-panel.service
```

## 手动安装

如果不使用 `install-local.sh`，也可以手动执行：

```bash
# 1. 解压到 /opt
sudo tar -xzf tiny-service-panel.tar.gz -C /opt

# 2. 安装 systemd socket activation
cd /opt/tiny-service-panel
sudo chmod +x install.sh server.py
sudo ./install.sh

# 3. 访问本机 API 验证
curl http://127.0.0.1:8765/api/summary
```

默认监听 `127.0.0.1:8765`。如需换端口：

```bash
cd /opt/tiny-service-panel
sudo PORT=9876 ./install.sh
```

## 是否需要 root 权限？

需要。原因是安装过程要写入 `/opt` 和 `/etc/systemd/system`，并执行 `systemctl daemon-reload`、`systemctl enable --now`。

但压缩包不需要上传到 `/opt`。你可以先上传到个人目录，再运行一键安装脚本，脚本会通过 `sudo` 完成复制和安装。


## 一键卸载

安装完成后，可以用包内自带脚本一键卸载：

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

也就是会删除程序文件、收藏/备注数据、systemd 配置和安装脚本升级时留下的备份目录。

如果你想卸载程序但保留历史备份目录：

```bash
sudo REMOVE_BACKUPS=0 bash /opt/tiny-service-panel/uninstall.sh
```

如果你还想删除当初上传到个人目录的安装包和本地安装脚本，可以再手动执行：

```bash
rm -f ~/tiny-service-panel.tar.gz ~/install-local.sh ~/uninstall.sh
```

卸载后验证：

```bash
systemctl status tiny-service-panel.socket --no-pager
ss -lntp | grep 8765
```

正常情况下，systemd 会提示找不到对应 unit，且 8765 没有监听。

## 文档位置

说明文件在项目里的 `docs/` 目录：

- `docs/TECHNICAL_DESIGN.md`：技术设计、部署、API、验证命令。
- `docs/RECREATE_PROMPT.md`：给其它 AI 复刻项目用的完整提示词。

## 安全提醒

此面板能 start/stop/restart systemd 服务，默认以 root 运行。建议只放在本机、内网、VPN、Cloudflare Access 或其它可信反向代理后面，不要裸露到公网。
