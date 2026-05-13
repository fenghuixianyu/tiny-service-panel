# Tiny Service Panel 复刻提示词

把本文直接喂给其它 AI，可以在任意 Linux/systemd 服务器上复刻当前 Tiny Service Panel 的设计和功能。

## 复刻目标

请实现一个轻量、便携、按需启动的 Linux systemd Web 管理面板，名字可以叫 Tiny Service Panel。

核心要求：

1. **平时几乎 0 占用**：使用 systemd socket activation。只 enable `.socket`，不要 enable `.service`。
2. **访问时才启动**：用户打开 Web 页面或 API 时，systemd 自动启动 Python 后端。
3. **空闲自动退出**：服务进程 60 秒没有新请求后主动退出，释放内存。
4. **零第三方依赖**：后端用 Python 标准库，前端用静态 HTML/CSS/JS，不需要 pip、Node、数据库。
5. **自动列出服务**：通过 `systemctl list-units --all` 自动捕获 service/socket/timer。
6. **按内存排序**：通过 `ps -eo unit,pid,comm,rss,%cpu` 按 systemd unit 聚合 RSS，默认按内存从大到小排序。
7. **方便操作**：支持 start/stop/restart、status、journal 日志。
8. **移动端友好**：深色、简洁、顺眼，不要花哨动画，不要大框架。
9. **操作后不要整页刷新**：按钮操作后只异步刷新数据，用页面内 toast 显示结果，不要用 alert 弹窗阻塞页面。
10. **支持隐藏系统繁琐项**：默认隐藏常见 systemd/user/session/dbus/timer/mount/slice 等噪音项。
11. **支持收藏列表**：每个 unit 有星标收藏按钮，可一键切换只看收藏。
12. **支持备注**：每个 unit 可写备注，显示为 `unit（备注）`。
13. **可迁移**：项目目录可以直接复制到其它服务器运行安装脚本。

## 推荐目录结构

```text
/opt/tiny-service-panel/
├── server.py
├── install.sh
├── tiny_service_panel/
│   ├── __init__.py
│   ├── core.py
│   └── system.py
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/
│   └── metadata.json
├── tests/
│   └── test_core.py
└── docs/
    ├── TECHNICAL_DESIGN.md
    ├── SOCKET_ACTIVATED_DESIGN_PATTERN.md
    └── RECREATE_PROMPT.md
```

## systemd 设计

`tiny-service-panel.socket`：

```ini
[Unit]
Description=Tiny Service Panel Socket

[Socket]
ListenStream=127.0.0.1:8765
Accept=no
NoDelay=true

[Install]
WantedBy=sockets.target
```

`tiny-service-panel.service`：

```ini
[Unit]
Description=Tiny Service Panel (socket activated)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tiny-service-panel
ExecStart=/usr/bin/python3 /opt/tiny-service-panel/server.py --systemd-socket
StandardInput=socket
StandardOutput=journal
StandardError=journal
Environment=TSP_IDLE_TIMEOUT=60
TimeoutStopSec=5
KillMode=process
NoNewPrivileges=false
```

只启用 socket：

```bash
systemctl daemon-reload
systemctl enable --now tiny-service-panel.socket
systemctl restart tiny-service-panel.socket
```

不要执行：

```bash
systemctl enable tiny-service-panel.service
```

## 后端 API

### `GET /api/summary`

返回：

- hostname
- `/proc/loadavg` 的 1/5/15 分钟 load
- `/proc/meminfo` 的总内存、可用内存、已用内存、百分比
- `df -Pk /` 的根分区使用率

### `GET /api/units?sort=memory&dir=desc&type=all`

返回全部 units：

字段至少包含：

```json
{
  "unit": "example.service",
  "display_unit": "example.service（示例服务）",
  "description": "Example Service",
  "load": "loaded",
  "active": "active",
  "sub": "running",
  "rss_kb": 64512,
  "memory_mb": 63.0,
  "cpu_percent": 1.2,
  "process_count": 1,
  "favorite": true,
  "note": "示例服务",
  "noisy": false
}
```

参数：

- `sort=memory|cpu|name|state`
- `dir=desc|asc`
- `type=all|service|socket|timer`

### `POST /api/action`

请求：

```json
{"unit":"example.service","action":"restart"}
```

支持：

- start
- stop
- restart
- reload
- enable
- disable

必须校验 unit 名称，不能 shell 拼接。用参数数组执行 subprocess。

### `GET /api/status?unit=xxx.service`

返回 `systemctl status xxx.service --no-pager -l`。

### `GET /api/logs?unit=xxx.service&lines=160`

返回 `journalctl -u xxx.service --no-pager -n 160`。

### `GET /api/metadata`

返回收藏和备注：

```json
{"favorites":["example.service"],"notes":{"example.service":"示例服务"}}
```

### `POST /api/metadata`

支持：

```json
{"action":"toggle_favorite","unit":"example.service"}
{"action":"note","unit":"example.service","note":"示例服务"}
```

备注文件建议保存到：

```text
/opt/tiny-service-panel/data/metadata.json
```

## 核心解析逻辑

### 列出 systemd units

```bash
systemctl list-units --all --no-legend --no-pager --type=service --type=socket --type=timer
```

### 读取进程资源

```bash
ps -eo unit,pid,comm,rss,%cpu --no-headers
```

按 `unit` 聚合：

- RSS 累加为 `rss_kb`
- `%CPU` 累加为 `cpu_percent`
- 进程数量累加为 `process_count`
- `memory_mb = round(rss_kb / 1024, 1)`

### unit 名称安全正则

```regex
^[A-Za-z0-9_.@:-]+\.(service|socket|timer|target|path|mount|automount|scope|slice)$
```

### 常见噪音项隐藏规则

默认隐藏但不删除，用户可点按钮显示。收藏项即使属于噪音也要显示。

建议隐藏：

- `systemd-*`
- `user@*`
- `session-*`
- `getty@*`
- `serial-getty@*`
- `dev-*`
- `sys-*`
- `run-*`
- `*.mount`
- `*.automount`
- `*.slice`
- `*.scope`
- `dbus.service`
- `dbus.socket`
- 常见 timer：`apt-daily.timer`、`apt-daily-upgrade.timer`、`logrotate.timer`、`man-db.timer`、`fstrim.timer` 等

不要隐藏：

- example.service
- ssh.service
- nginx/apache/caddy
- tunnel daemon
- sing-box
- 用户自己安装的业务服务

## 前端要求

页面结构：

1. 顶部固定仪表盘，但不要随着表格横向滚动。
2. 显示主机、内存、Load、根分区。
3. 控制区：类型筛选、排序方式、升降序、隐藏系统项、收藏列表、搜索框、刷新按钮。
4. 表格列：Unit、状态、内存、CPU、进程、描述、操作。
5. 操作按钮：启动、重启、停止、备注、状态、日志。
6. 状态/日志用 `<dialog>` 或轻量模态框显示。
7. 操作结果用 toast 显示，不要 `alert()`。
8. 操作后 `setTimeout` 延迟约 0.9 秒局部刷新 `/api/units`，不要整页 reload。
9. 用户偏好如隐藏系统项、收藏列表模式、排序方向可用 `localStorage` 保存。

视觉风格：

- 深色背景
- 简洁卡片
- 小圆角
- 状态颜色：active 绿色、failed 红色、activating 黄色、inactive 灰蓝
- 不要引入大型 UI 框架
- 不要动画过多
- 移动端表格允许横向滚动，隐藏次要列

## 测试要求

至少测试：

1. systemctl 输出解析。
2. ps 输出按 unit 聚合内存/CPU。
3. 按内存降序排序。
4. unit 名称安全校验。
5. systemd unit 生成包含 `StandardInput=socket` 和 `ListenStream=127.0.0.1:8765`。
6. 常见系统噪音 unit 能被识别。
7. 收藏/备注 metadata 能应用到 units，生成 `display_unit`。

运行：

```bash
PYTHONPATH=/opt/tiny-service-panel python3 -m unittest discover -s /opt/tiny-service-panel/tests -v
```

## 验证命令

```bash
# 本地
curl http://127.0.0.1:8765/api/summary
curl 'http://127.0.0.1:8765/api/units?sort=memory&dir=desc&type=all'

# socket 激活状态
systemctl status tiny-service-panel.socket tiny-service-panel.service --no-pager -l
systemctl show tiny-service-panel.socket tiny-service-panel.service -p ActiveState -p SubState -p MemoryCurrent -p MainPID

# 空闲退出
sleep 70
systemctl status tiny-service-panel.service --no-pager -l
```

预期：

- 访问前：`.service inactive/dead`，`.socket active/listening`
- 访问中：`.service active/running`
- 空闲约 60 秒：`.service inactive/dead`
- `.socket` 常驻占用通常只有几 KB

## 迁移方式

```bash
scp -r /opt/tiny-service-panel root@目标机器:/opt/tiny-service-panel
ssh root@目标机器
cd /opt/tiny-service-panel
chmod +x install.sh server.py
./install.sh
```

换端口：

```bash
PORT=9876 ./install.sh
```

如果通过 Cloudflare Tunnel 暴露：

```yaml
ingress:
  - hostname: panel.example.com
    service: http://127.0.0.1:8765
  - service: http_status:404
```

## 重要理念

这个项目不是追求运行时极致性能，而是追求：

```text
不用时根本不运行。
```

管理面板是低频人工工具，不应该 24 小时常驻吃内存。用 systemd socket activation，把内存花在真正业务服务上。
## 移动端布局补充要求

复刻时请按当前移动端布局处理：

- 表格列顺序固定为：`Unit / 内存 / 状态 / CPU / 进程 / 描述 / 操作`。
- 在手机上，Unit 单元格内部要同时放：可换行服务名、快捷启动/停止按钮。
- 快捷按钮逻辑：`active` 时显示“停止”，其它状态显示“启动”。
- 内存列紧跟 Unit，方便手机首屏同时看到服务名、开关按钮、内存占用。
- 收藏星标放到最右侧操作区，不要放在最左边，避免挤占服务名。
- 右侧操作区保留收藏、启动、重启、停止、备注、状态、日志。
- 手机端可隐藏 CPU、进程、描述列，但保留 Unit、内存、状态、操作。
- 服务名必须允许换行：使用 `word-break: break-word` / `overflow-wrap: anywhere`。
- 表格分隔线必须是一整条连续横线：用 `border-collapse: collapse`，所有 `td/th` 使用统一 `border-bottom`，不要让 Unit 单元格内部元素单独画横线。
