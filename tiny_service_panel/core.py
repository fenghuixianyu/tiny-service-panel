import re
from typing import Dict, List, Any

UNIT_NAME_RE = re.compile(r"^[A-Za-z0-9_.@:-]+\.(service|socket|timer|target|path|mount|automount|scope|slice)$")

NOISY_UNIT_PREFIXES = (
    "systemd-",
    "user@",
    "session-",
    "getty@",
    "serial-getty@",
    "dev-",
    "sys-",
    "run-",
)
NOISY_UNIT_NAMES = {
    "dbus.service",
    "dbus.socket",
    "cron.service",
    "rsyslog.service",
    "logrotate.timer",
    "man-db.timer",
    "apt-daily.timer",
    "apt-daily-upgrade.timer",
    "e2scrub_all.timer",
    "fstrim.timer",
    "motd-news.timer",
    "ua-timer.timer",
    "dpkg-db-backup.timer",
    "phpsessionclean.timer",
    "anacron.timer",
}
NOISY_DESC_PATTERNS = (
    "slice",
    "user manager for uid",
    "session ",
    "device",
    "mount",
    "automount",
)


def is_allowed_unit_name(name: str) -> bool:
    return bool(name and UNIT_NAME_RE.match(name))


def is_common_noisy_unit(unit: str, description: str = "") -> bool:
    if unit in NOISY_UNIT_NAMES:
        return True
    if unit.startswith(NOISY_UNIT_PREFIXES):
        return True
    if unit.endswith((".mount", ".automount", ".slice", ".scope")):
        return True
    desc = (description or "").lower()
    return any(pat in desc for pat in NOISY_DESC_PATTERNS)


def apply_user_metadata(units: List[Dict[str, Any]], metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    favorites = set(metadata.get("favorites", []) or [])
    notes = metadata.get("notes", {}) or {}
    out = []
    for unit in units:
        row = dict(unit)
        name = row.get("unit", "")
        note = str(notes.get(name, "") or "").strip()
        row["favorite"] = name in favorites
        row["note"] = note
        row["noisy"] = is_common_noisy_unit(name, row.get("description", ""))
        row["display_unit"] = f"{name}（{note}）" if note else name
        out.append(row)
    return out


def parse_systemctl_list(raw: str) -> List[Dict[str, Any]]:
    units = []
    for line in raw.splitlines():
        line = line.rstrip()
        if not line or line.startswith("UNIT ") or line.startswith("LOAD "):
            continue
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        unit, load, active, sub = parts[:4]
        if not is_allowed_unit_name(unit):
            continue
        desc = parts[4] if len(parts) > 4 else ""
        units.append({"unit": unit, "load": load, "active": active, "sub": sub, "description": desc})
    return units


def parse_ps(raw: str) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("UNIT "):
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        unit, _pid, _comm, rss, cpu = parts
        if unit == "-" or not is_allowed_unit_name(unit):
            continue
        try:
            rss_kb = int(float(rss))
            cpu_percent = float(cpu)
        except ValueError:
            continue
        item = grouped.setdefault(unit, {"rss_kb": 0, "cpu_percent": 0.0, "process_count": 0})
        item["rss_kb"] += rss_kb
        item["cpu_percent"] += cpu_percent
        item["process_count"] += 1
    for item in grouped.values():
        item["cpu_percent"] = round(item["cpu_percent"], 2)
    return grouped


def merge_units_with_processes(units: List[Dict[str, Any]], proc: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = []
    for unit in units:
        row = dict(unit)
        metrics = proc.get(row["unit"], {"rss_kb": 0, "cpu_percent": 0.0, "process_count": 0})
        row.update(metrics)
        row["memory_mb"] = round(row["rss_kb"] / 1024, 1)
        merged.append(row)
    return merged


def sort_units(units: List[Dict[str, Any]], key: str = "memory", direction: str = "desc") -> List[Dict[str, Any]]:
    reverse = direction != "asc"
    key_map = {
        "memory": lambda u: (u.get("rss_kb", 0), u.get("unit", "")),
        "cpu": lambda u: (u.get("cpu_percent", 0.0), u.get("unit", "")),
        "name": lambda u: u.get("unit", ""),
        "state": lambda u: (u.get("active", ""), u.get("sub", ""), u.get("unit", "")),
    }
    return sorted(units, key=key_map.get(key, key_map["memory"]), reverse=reverse)


def render_systemd_units(port: int, user: str, app_dir: str) -> Dict[str, str]:
    socket_unit = f"""[Unit]
Description=Tiny Service Panel Socket

[Socket]
ListenStream=127.0.0.1:{port}
Accept=no
NoDelay=true

[Install]
WantedBy=sockets.target
"""
    service_unit = f"""[Unit]
Description=Tiny Service Panel (socket activated)
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={app_dir}
ExecStart=/usr/bin/python3 {app_dir}/server.py --systemd-socket
StandardInput=socket
StandardOutput=journal
StandardError=journal
Environment=TSP_IDLE_TIMEOUT=60
TimeoutStopSec=5
KillMode=process
NoNewPrivileges=false

[Install]
WantedBy=multi-user.target
"""
    return {"tiny-service-panel.socket": socket_unit, "tiny-service-panel.service": service_unit}
