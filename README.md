# Tiny Service Panel

Tiny Service Panel 是一个轻量 Linux systemd 服务管理面板，用来在浏览器里查看服务状态、CPU/内存占用，并执行启动、停止、重启、开机自启管理等操作。

核心设计：默认使用 **systemd socket activation**。开机自启的是 `tiny-service-panel.socket` 监听端口，Python 后端只有在访问面板/API 时才会被 systemd 拉起，空闲 10 分钟后自动退出，所以平时资源占用接近 0。

## 新服务器最快安装

如果要在手机或电脑上直接通过 `http://服务器IP:8765` 访问，推荐在新服务器执行：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env BIND_HOST=0.0.0.0 bash
```

首次公网安装会询问登录密码：直接回车无效，会要求重输；输入 `r` 后回车会生成随机强密码并在安装完成时只打印一次。

安装完成后打开：

```text
http://服务器IP:8765
```

如果只想本机访问，或者准备用 SSH 隧道访问，执行默认安装即可：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo bash
```

注意：

- 需要 `root` 或 `sudo`，因为脚本会安装到 `/opt/tiny-service-panel`，并写入 `/etc/systemd/system`。
- 默认会启用 `tiny-service-panel.socket` 开机自启；`tiny-service-panel.service` 不会常驻，只在访问时启动，空闲 10 分钟后退出。
- 公网访问还需要服务器防火墙/云安全组放行 TCP `8765`。
- 完全卸载：
  ```bash
  sudo bash /opt/tiny-service-panel/uninstall.sh
  ```

## 功能概览

- 列出 systemd units，并显示运行状态、描述、CPU/内存占用。
- 支持 `start / stop / restart` 服务。
- 支持查看和管理开机自启：`systemctl enable/disable`。
- 支持收藏和备注。
- 支持隐藏常见 systemd 噪音项，并可单独查看 systemd 基础、登录/会话、设备/挂载、系统定时器、D-Bus 等屏蔽区。
- 搜索范围可多选：服务名、描述、备注、状态、自启、屏蔽区。
- 支持异常服务置顶，方便优先处理 `failed / activating / auto-restart` 服务。
- 仪表盘显示内存、Swap、Load、根分区、运行时间、重启状态和可收纳的磁盘分区。
- 提供“重启服务器”按钮，需二次确认并输入 `REBOOT`，防止误触。
- 手机浏览器使用卡片布局，同时保留搜索、类型、排序、运行状态和自启状态筛选。
- 默认监听 `127.0.0.1:8765`，可改为 `0.0.0.0:8765` 供外网访问。
- 支持密码登录和“记住此设备”。
- 支持一键在线安装、本地离线安装和一键卸载。

## 在线安装/升级

默认安装：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo bash
```

换端口：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env PORT=9876 bash
```

公网访问，首次安装时交互式设置密码：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env BIND_HOST=0.0.0.0 bash
```

密码输入规则：

- 直接回车无效，会要求重新输入。
- 输入 `r`、`random` 或 `随机` 后回车，会生成随机强密码，并在安装完成时只打印一次。
- 如果是脚本/CI 等没有 TTY 的非交互环境，会自动生成随机强密码，保持兼容。
- 如果服务器已经存在 `/etc/tiny-service-panel/auth.env`，重复安装/升级时默认保留原密码，不会再次询问。

以后修改密码可以重新指定 `AUTH_PASSWORD` 执行安装脚本；密码哈希配置保存在 `/etc/tiny-service-panel/auth.env`：

```bash
sudo env BIND_HOST=0.0.0.0 PORT=8765 AUTH_PASSWORD='新密码' /opt/tiny-service-panel/install.sh
```

也可以不交互，直接在命令里指定密码：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env BIND_HOST=0.0.0.0 AUTH_PASSWORD='换成你的强密码' bash
```

如果想跳过询问并强制生成随机密码：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env BIND_HOST=0.0.0.0 AUTH_RANDOM=1 bash
```

修改“记住此设备”的时间，例如 90 天：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env BIND_HOST=0.0.0.0 AUTH_PASSWORD='换成你的强密码' AUTH_COOKIE_DAYS=90 bash
```

安装/升级脚本会保留已有收藏和备注：

```text
/opt/tiny-service-panel/data/metadata.json
```

## 安装位置和开机自启

默认安装到：

```text
/opt/tiny-service-panel
```

systemd 文件：

```text
/etc/systemd/system/tiny-service-panel.socket
/etc/systemd/system/tiny-service-panel.service
```

安装脚本会默认执行：

```bash
systemctl enable tiny-service-panel.socket
```

因此服务器重启后会自动恢复监听。`tiny-service-panel.service` 不会设置为常驻自启，它只会在访问面板/API 时按需启动，空闲 10 分钟后退出。

## 如何访问

默认只监听本机地址：

```text
127.0.0.1:8765
```

所以默认情况下不能直接用公网 IP 访问 `公网IP:8765`。推荐用 SSH 隧道：

```bash
ssh -L 8765:127.0.0.1:8765 user@server_ip
```

然后在本地浏览器打开：

```text
http://127.0.0.1:8765
```

如果确实要公网访问，需要让 socket 监听所有网卡；首次安装会询问密码：

```bash
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env BIND_HOST=0.0.0.0 bash
```

确认监听地址：

```bash
ss -lntp | grep 8765
```

应能看到类似：

```text
LISTEN ... 0.0.0.0:8765
```

如果仍然打不开 `http://公网IP:8765`，还需要检查服务器防火墙和云厂商安全组是否放行 TCP `8765`。

登录页勾选“记住此设备”后，会在当前浏览器保存 HttpOnly Cookie，默认 30 天内不用重复输入密码。换浏览器、清理 Cookie、点击退出登录、重装并更换密码后，都需要重新登录。

## 本地离线安装/迁移包

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

如需换端口：

```bash
PORT=9876 bash install-local.sh tiny-service-panel.tar.gz
```

如需公网访问，首次安装时询问密码：

```bash
BIND_HOST=0.0.0.0 bash install-local.sh tiny-service-panel.tar.gz
```

也可以直接指定密码，或跳过询问生成随机密码：

```bash
BIND_HOST=0.0.0.0 AUTH_PASSWORD='换成你的强密码' bash install-local.sh tiny-service-panel.tar.gz
BIND_HOST=0.0.0.0 AUTH_RANDOM=1 bash install-local.sh tiny-service-panel.tar.gz
```

如果直接使用本项目生成的迁移包，上传这两个文件即可：

```text
tiny-service-panel.tar.gz
install-local.sh
```

然后执行同样的安装命令。压缩包不需要提前上传到 `/opt`，上传到个人目录即可；脚本会自动使用 `sudo` 提权，把程序复制到 `/opt/tiny-service-panel` 并安装 systemd 文件。

迁移包说明：

- 不包含原服务器域名、Cloudflare 配置、主机名等部署信息。
- `data/metadata.json` 默认是空收藏/空备注，升级已有安装时会保留服务器上的现有数据。
- 不包含 Python `__pycache__`、`.pyc` 等运行缓存。
- `uninstall.sh` 已包含在安装包里，安装后位于 `/opt/tiny-service-panel/uninstall.sh`。

### 手动安装

一般推荐使用 `install-local.sh`，如果确实要手动安装，也可以：

```bash
# 1. 解压到 /opt
sudo tar -xzf tiny-service-panel.tar.gz -C /opt

# 2. 安装 systemd socket activation
cd /opt/tiny-service-panel
sudo chmod +x install.sh server.py uninstall.sh
sudo ./install.sh

# 3. 验证本机 API
curl http://127.0.0.1:8765/api/auth/status
```

换端口或公网监听：

```bash
cd /opt/tiny-service-panel
sudo PORT=9876 ./install.sh
sudo BIND_HOST=0.0.0.0 AUTH_PASSWORD='换成你的强密码' ./install.sh
```

## 开机自启管理

面板会合并 `systemctl list-unit-files` 的状态，在列表里显示：

```text
已自启 / 未自启 / static / indirect / generated / masked / unknown
```

当前开放安全的直接操作：

```text
disabled -> 开自启
enabled / enabled-runtime -> 关自启
```

`static`、`indirect`、`generated`、`masked` 等状态只显示，不提供按钮，避免误操作。

注意：

- `开自启` 对应 `systemctl enable xxx`，不会立刻启动服务。
- `关自启` 对应 `systemctl disable xxx`，不会立刻停止服务。
- 如果要立刻启动或停止，请使用 `启动 / 停止 / 重启` 按钮。

## 屏蔽区和搜索范围

面板会把常见、基本不需要手动操作的系统项归入屏蔽区，例如：

```text
systemd 基础 / 登录会话 / 设备挂载 / 系统定时器 / D-Bus / 系统基础
```

默认隐藏屏蔽区，减少服务列表噪音。也可以通过“全部分区 / 常用区 / 屏蔽区”筛选单独查看。

搜索框支持可多选搜索范围，默认全选：

```text
服务名 / 描述 / 备注 / 状态 / 自启 / 屏蔽区
```

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
/etc/tiny-service-panel/auth.env
/opt/tiny-service-panel
/opt/tiny-service-panel.bak.*
```

也就是会删除程序文件、收藏/备注数据、systemd 配置、密码配置和安装脚本升级时留下的备份目录。

如果想卸载程序但保留历史备份目录：

```bash
sudo REMOVE_BACKUPS=0 bash /opt/tiny-service-panel/uninstall.sh
```

如果还想删除当初上传到个人目录的安装包和本地安装脚本，可以再手动执行：

```bash
rm -f ~/tiny-service-panel.tar.gz ~/install-local.sh ~/uninstall.sh
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

# 查看后端服务状态
systemctl status tiny-service-panel.service --no-pager -l

# 查看后端服务日志
journalctl -u tiny-service-panel.service -n 100 --no-pager

# 查看监听端口
ss -lntp | grep 8765

# 在线重新安装/升级
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh | sudo bash

# 公网访问，首次安装交互式设置密码
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env BIND_HOST=0.0.0.0 bash

# 公网访问 + 直接指定密码重新安装/升级
curl -fsSL https://raw.githubusercontent.com/fenghuixianyu/tiny-service-panel/main/install-online.sh \
  | sudo env BIND_HOST=0.0.0.0 AUTH_PASSWORD='换成你的强密码' bash
```

## 私有仓库能不能一键安装？

可以，但不能像公开仓库一样匿名下载。私有仓库下载 `raw.githubusercontent.com` 和源码压缩包时都需要 GitHub Token，例如：

```bash
GITHUB_TOKEN=你的token
curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  https://raw.githubusercontent.com/OWNER/REPO/main/install-online.sh \
  | sudo env GITHUB_TOKEN="${GITHUB_TOKEN}" REPO=OWNER/REPO bash
```

如果只是为了自己多台服务器快速安装，公开仓库最省事；如果必须私有，建议使用权限最小化、可随时吊销的 token。

## 文档位置

更多技术说明在 `docs/` 目录：

- `docs/TECHNICAL_DESIGN.md`：技术设计、部署、API、验证命令。
- `docs/RECREATE_PROMPT.md`：给其它 AI 复刻项目用的完整提示词。

## 安全提醒

此面板可以 start/stop/restart systemd 服务，并默认以 root 运行。即使加了密码，也建议优先放在本机、内网、VPN、Cloudflare Access 或其它可信反向代理后面；如果必须公网开放，请使用强密码，并尽量只放行可信来源 IP。
