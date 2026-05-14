# Tiny Service Panel 技术文档

## 目标

Tiny Service Panel 是一个可移植、低资源占用的 Linux systemd 服务控制面板，用来满足：

1. **方便管理服务**：自动列出 systemd units，支持 start / stop / restart。
2. **按内存占用排序**：聚合每个 systemd unit 下所有进程的 RSS，默认按内存从大到小排序。
3. **平时几乎 0 占用**：使用 systemd socket activation。没人访问时只有 `.socket` 监听，实测 socket 约 8KB；Python Web 进程退出。
4. **使用时才完全打开**：浏览器访问端口后，systemd 临时启动 Python 后端；用户停止访问约 10 分钟后自动退出。
5. **便携**：项目为零第三方 Python 依赖，复制 `/opt/tiny-service-panel` 到其它服务器，运行 `install.sh` 即可。

## 迁移包说明

本压缩包是可迁移版本，不包含原服务器的主机名、域名、Cloudflare 配置、收藏、备注或其它本机状态。

默认安装参数：

- 推荐目录：`/opt/tiny-service-panel`
- 默认本地监听：`http://127.0.0.1:8765`
- systemd socket：`tiny-service-panel.socket`
- systemd service：`tiny-service-panel.service`

如需通过 Cloudflare Tunnel、Nginx、Caddy 或其它反向代理暴露访问，请在目标服务器上单独配置，把入口转发到 `http://127.0.0.1:8765`。不要直接把管理面板裸露到公网。

## 文件结构

```text
/opt/tiny-service-panel/
├── server.py                         # HTTP 后端，支持普通端口运行和 systemd socket 激活
├── install.sh                        # 安装/更新 systemd socket + service
├── tiny_service_panel/
│   ├── __init__.py
│   ├── core.py                       # 纯函数：解析 systemctl/ps、聚合内存、排序、生成 unit 文件
│   └── system.py                     # 调用 systemctl/ps/free/df/hostname/journalctl 的系统适配层
├── static/
│   ├── index.html                    # 单页前端
│   ├── style.css                     # 深色轻量样式
│   └── app.js                        # 拉取 API、排序、过滤、操作按钮
├── tests/
│   └── test_core.py                  # 核心逻辑单元测试
└── docs/
    └── TECHNICAL_DESIGN.md           # 本文档
```

## 架构理念

### 为什么不用常驻服务

常驻 Web 面板即使没人看也会占内存、CPU、文件句柄。这个项目的理念是：

> 服务管理面板不是核心业务进程，应该在用户需要时才出现，用完自动消失。

所以采用 systemd socket activation：

1. `tiny-service-panel.socket` 常驻，监听 `127.0.0.1:8765`。
2. 有连接进入时，systemd 启动 `tiny-service-panel.service`。
3. Python 后端处理请求。
4. 约 10 分钟无新请求后，后端退出。
5. 端口继续由 systemd socket 监听，等待下次访问。

### 为什么用 Python 标准库

为了方便迁移到其它服务器，不依赖 Node、Go 编译、pip 包、数据库。只要求：

- Linux + systemd
- Python 3
- systemctl / ps / free / df / journalctl 等常见命令

### 为什么从 systemd unit 聚合内存

Linux 进程天然很多，用户真正关心的是“哪个服务吃内存”。实现方式：

```bash
ps -eo pid=,rss=,unit=,comm=,args=
```

后端按 `unit` 字段分组，把同一个 systemd unit 下的所有进程 RSS 相加，得到 `memory_mb`。

然后与：

```bash
systemctl list-units --all --type=service --type=socket --type=timer --type=target --no-legend --plain
```

结果合并。这样页面能自动捕获系统中已有服务，不需要像 Monit 那样逐个写配置。

## API

### `GET /api/summary`

返回主机名、load、内存、根分区使用情况。

### `GET /api/units?sort=memory&dir=desc&type=all`

返回 unit 列表。常用参数：

- `sort=memory|unit|active|sub|load`
- `dir=desc|asc`
- `type=all|service|socket|timer|target`

默认就是按内存从大到小。

### `GET /api/status?unit=xxx.service`

返回 `systemctl status xxx.service` 文本。

### `GET /api/logs?unit=xxx.service&lines=120`

返回最近 journal 日志。

### `POST /api/action`

请求体：

```json
{"unit":"xxx.service","action":"restart"}
```

支持：`start`、`stop`、`restart`。

安全处理：unit 名称必须匹配白名单正则，只允许常见 systemd unit 字符和后缀，拒绝 `;`、空格、路径穿越等注入风险。

## systemd unit 设计

`tiny-service-panel.socket`：

```ini
[Socket]
ListenStream=127.0.0.1:8765
Accept=no
NoDelay=true
```

`tiny-service-panel.service`：

```ini
[Service]
Type=simple
User=root
WorkingDirectory=/opt/tiny-service-panel
ExecStart=/usr/bin/python3 /opt/tiny-service-panel/server.py --systemd-socket
StandardInput=socket
Environment=TSP_IDLE_TIMEOUT=600
TimeoutStopSec=5
KillMode=process
```

这里使用 root 是为了能执行 `systemctl start/stop/restart`。如果只想查看，不想控制服务，可以改成低权限用户并移除操作 API。

## 部署到其它服务器

```bash
# 1. 复制项目
scp -r /opt/tiny-service-panel root@目标机器:/opt/tiny-service-panel

# 2. 登录目标机器
ssh root@目标机器

# 3. 安装 systemd socket
cd /opt/tiny-service-panel
chmod +x install.sh server.py
./install.sh

# 4. 验证
curl http://127.0.0.1:8765/api/summary
curl 'http://127.0.0.1:8765/api/units?sort=memory&dir=desc&type=all'
```

如需换端口：

```bash
PORT=9876 ./install.sh
```

如需只在局域网访问，可以把 socket 里的 `ListenStream=127.0.0.1:8765` 改为 `0.0.0.0:8765`，但不建议直接暴露到公网。

## 验证命令

```bash
# 单元测试
PYTHONPATH=/opt/tiny-service-panel python3 -m unittest discover -s /opt/tiny-service-panel/tests -v

# 本地健康
curl http://127.0.0.1:8765/api/summary

# 按内存排序
curl 'http://127.0.0.1:8765/api/units?sort=memory&dir=desc&type=all'

# 查看 idle 状态
systemctl status tiny-service-panel.socket tiny-service-panel.service --no-pager -l
```

预期：

- 访问时：`tiny-service-panel.service` 是 active，内存约 9–20MB。
- 停止访问约 10 分钟后：`tiny-service-panel.service` 变为 inactive/dead。
- `tiny-service-panel.socket` 仍为 active/listening，内存约 8KB。

## 性能取舍

- 后端每次刷新会调用 `systemctl` 和 `ps`，不是常驻采集器。
- 好处：平时 0 采集、0 数据库、0 后台循环。
- 代价：打开页面/刷新时会有一次命令调用开销。
- 对低配置盒子，这比 Netdata/1Panel 这类常驻监控更符合“用时打开”的理念。

## 后续可扩展

1. 增加“确认停止服务”的自定义非阻塞确认弹窗，替代浏览器 confirm。
2. 增加 `/api/processes`，显示进程级 TOP 列表。
3. 增加只读模式。
4. 增加 token 或 Basic Auth；当前建议只放在 Cloudflare Access、VPN、内网或可信 tunnel 后面。

## 复刻提示词模块

当前实现的完整功能、API、UI 行为、socket activation 设计、隐藏系统项、收藏、备注、操作后局部刷新等复刻细节，已单独整理到：

```text
/opt/tiny-service-panel/docs/RECREATE_PROMPT.md
```

以后要在其它服务器让 AI 还原本项目时，优先把该文件全文提供给 AI。它记录了当前版本的全部关键设计约束：

- systemd socket activation，平时只保留 `.socket`；
- `.service` 访问时启动，空闲 10 分钟退出；
- Python 标准库后端，无 pip/Node/数据库依赖；
- systemctl + ps 聚合 service/socket/timer 状态、内存、CPU、进程数；
- 默认按内存降序；
- start/stop/restart/status/logs 操作；
- 操作后使用 toast + 局部刷新，不做整页 reload；
- 默认隐藏常见系统噪音项；
- 支持收藏列表；
- 支持 unit 备注并显示为 `unit（备注）`；
- 移动端友好的深色轻量 UI；
- 单元测试与部署验证命令。

## 移动端列表布局约定

为保证手机上少横向滚动即可完成高频操作，当前列表列顺序与桌面/移动端规则如下：

1. 列顺序为：`Unit / 内存 / 状态 / CPU / 进程 / 描述 / 操作`。
2. 状态列放在内存后面，因为移动端可通过快捷开关按钮大致判断运行状态。
3. 移动端在 Unit 单元格右侧显示一个快捷按钮：运行中显示“停止”，非运行中显示“启动”。
4. 服务名允许换行，目标是在手机首屏同时看到：服务名称、快捷开关按钮、内存信息。
5. 收藏星标不再放在最左侧，改放到最右侧完整操作区，避免挤占服务名空间。
6. 右侧完整操作区仍保留：收藏、启动、重启、停止、备注、状态、日志。
7. 移动端隐藏 CPU、进程、描述等次要列，保留 Unit、内存、状态、操作。
8. 表格使用 `border-collapse: collapse` 并保持所有单元格统一 `border-bottom`，避免服务名单元格下方横线和右侧横线断开。
