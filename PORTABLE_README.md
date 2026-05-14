# Tiny Service Panel 迁移包

这是 Tiny Service Panel 的可迁移安装包，已移除原服务器信息：

- 不包含原服务器域名、Cloudflare 配置、主机名等部署信息。
- `data/metadata.json` 已重置为空收藏/空备注。
- 不包含 Python `__pycache__`、`.pyc` 等运行缓存。
- 支持查看和管理 systemd 开机自启状态，并为手机浏览器优化了卡片布局。
- 开机自启的是 systemd socket；Python 后端访问时才启动，空闲 10 分钟后退出。
- 仪表盘包含内存、Swap、Load、根分区、运行时间、重启状态和默认收纳的磁盘分区。
- 支持屏蔽区分类和搜索范围多选，减少系统服务噪音。

## GitHub 在线安装

如果服务器可以访问 GitHub，推荐直接执行：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo bash
```

换端口：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo env PORT=9876 bash
```

公网访问并设置密码：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env BIND_HOST=0.0.0.0 AUTH_PASSWORD='换成你的强密码' bash
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

如需公网访问并设置密码：

```bash
BIND_HOST=0.0.0.0 AUTH_PASSWORD='换成你的强密码' bash install-local.sh tiny-service-panel.tar.gz
```

如果公网安装时不传 `AUTH_PASSWORD`，脚本会自动生成随机密码并只打印一次。登录页勾选“记住此设备”后，当前浏览器默认 30 天内不用重复输入密码；可通过 `AUTH_COOKIE_DAYS=90` 修改。

脚本会自动使用 `sudo` 提权，把程序安装到：

```text
/opt/tiny-service-panel
```

并写入 systemd 文件：

```text
/etc/systemd/system/tiny-service-panel.socket
/etc/systemd/system/tiny-service-panel.service
```

脚本会默认启用 `tiny-service-panel.socket` 开机自启；`tiny-service-panel.service` 不常驻，只在访问面板时按需启动。

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
curl http://127.0.0.1:8765/api/auth/status
```

默认监听 `127.0.0.1:8765`。如需换端口：

```bash
cd /opt/tiny-service-panel
sudo PORT=9876 ./install.sh
```

如需改为外网监听：

```bash
cd /opt/tiny-service-panel
sudo BIND_HOST=0.0.0.0 AUTH_PASSWORD='换成你的强密码' ./install.sh
```

## 屏蔽区和搜索范围

常见的 systemd 基础、登录/会话、设备/挂载、系统定时器、D-Bus 等会归入屏蔽区。默认隐藏屏蔽区，但可以通过分区筛选单独查看。搜索范围支持服务名、描述、备注、状态、自启、屏蔽区多选，默认全选。

## 开机自启管理

服务列表会显示 `已自启 / 未自启 / static / masked` 等状态。

- `开自启`：执行 `systemctl enable xxx`，不会立刻启动服务。
- `关自启`：执行 `systemctl disable xxx`，不会立刻停止服务。
- `static / indirect / generated / masked` 等状态默认只显示，不提供按钮，避免误操作。

手机浏览器中会使用卡片式布局，同时保留搜索、类型、排序、运行状态和自启状态筛选。

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
/etc/tiny-service-panel/auth.env
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

此面板能 start/stop/restart systemd 服务，默认以 root 运行。即使加了密码，也建议优先放在本机、内网、VPN、Cloudflare Access 或其它可信反向代理后面；如果必须公网开放，请使用强密码并只放行可信来源 IP。
