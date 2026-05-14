import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from .core import (
    parse_systemctl_list,
    parse_unit_file_states,
    parse_ps,
    merge_units_with_processes,
    sort_units,
    is_allowed_unit_name,
    apply_user_metadata,
    apply_boot_metadata,
)

SYSTEMCTL = "/bin/systemctl" if os.path.exists("/bin/systemctl") else "systemctl"
APP_DIR = Path(os.environ.get("TSP_APP_DIR", "/opt/tiny-service-panel"))
DATA_DIR = Path(os.environ.get("TSP_DATA_DIR", str(APP_DIR / "data")))
META_FILE = DATA_DIR / "metadata.json"

DEFAULT_META = {"favorites": [], "notes": {}}


def run_cmd(args: List[str], timeout: int = 8) -> subprocess.CompletedProcess:
    return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def load_metadata() -> Dict[str, Any]:
    try:
        if META_FILE.exists():
            data = json.loads(META_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {"favorites": list(data.get("favorites", []) or []), "notes": dict(data.get("notes", {}) or {})}
    except Exception:
        pass
    return dict(DEFAULT_META)


def save_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    favorites = []
    seen = set()
    for unit in data.get("favorites", []) or []:
        if is_allowed_unit_name(unit) and unit not in seen:
            favorites.append(unit)
            seen.add(unit)
    notes = {}
    for unit, note in (data.get("notes", {}) or {}).items():
        if is_allowed_unit_name(unit):
            text = str(note or "").strip()[:80]
            if text:
                notes[unit] = text
    clean = {"favorites": favorites, "notes": notes}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = META_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(META_FILE)
    return clean


def update_metadata(action: str, unit: str = "", note: str = "") -> Dict[str, Any]:
    meta = load_metadata()
    favs = list(meta.get("favorites", []) or [])
    notes = dict(meta.get("notes", {}) or {})
    if action in {"favorite", "unfavorite", "toggle_favorite", "note", "clear_note"} and not is_allowed_unit_name(unit):
        return {"ok": False, "error": "invalid unit name", "metadata": meta}
    if action == "favorite" and unit not in favs:
        favs.append(unit)
    elif action == "unfavorite":
        favs = [x for x in favs if x != unit]
    elif action == "toggle_favorite":
        favs = [x for x in favs if x != unit] if unit in favs else favs + [unit]
    elif action == "note":
        text = str(note or "").strip()[:80]
        if text:
            notes[unit] = text
        else:
            notes.pop(unit, None)
    elif action == "clear_note":
        notes.pop(unit, None)
    elif action == "replace":
        pass
    else:
        return {"ok": False, "error": "invalid metadata action", "metadata": meta}
    clean = save_metadata({"favorites": favs, "notes": notes})
    return {"ok": True, "metadata": clean}


def collect_units(sort: str = "memory", direction: str = "desc", unit_type: str = "all") -> Dict[str, Any]:
    types = ["service", "socket", "timer"] if unit_type == "all" else [unit_type]
    cmd = [SYSTEMCTL, "list-units", "--all", "--no-legend", "--no-pager"]
    for t in types:
        cmd.append(f"--type={t}")
    units_raw = run_cmd(cmd, timeout=12).stdout
    unit_files_cmd = [SYSTEMCTL, "list-unit-files", "--no-legend", "--no-pager"]
    for t in types:
        unit_files_cmd.append(f"--type={t}")
    unit_files_raw = run_cmd(unit_files_cmd, timeout=12).stdout
    ps_raw = run_cmd(["ps", "-eo", "unit,pid,comm,rss,%cpu", "--no-headers"], timeout=8).stdout
    units = merge_units_with_processes(parse_systemctl_list(units_raw), parse_ps("UNIT PID COMM RSS %CPU\n" + ps_raw))
    units = apply_boot_metadata(units, parse_unit_file_states(unit_files_raw))
    units = apply_user_metadata(units, load_metadata())
    units = sort_units(units, sort, direction)
    return {"units": units, "count": len(units), "metadata": load_metadata()}


def system_summary() -> Dict[str, Any]:
    meminfo = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as f:
        for line in f:
            key, rest = line.split(":", 1)
            meminfo[key] = int(rest.strip().split()[0])
    load = open("/proc/loadavg", encoding="utf-8").read().split()[:3]
    root = run_cmd(["df", "-Pk", "/"], timeout=5).stdout.splitlines()
    disk = {}
    if len(root) >= 2:
        parts = root[1].split()
        if len(parts) >= 6:
            disk = {"size_kb": int(parts[1]), "used_kb": int(parts[2]), "avail_kb": int(parts[3]), "use_percent": parts[4]}
    total = meminfo.get("MemTotal", 0)
    avail = meminfo.get("MemAvailable", 0)
    swap_total = meminfo.get("SwapTotal", 0)
    swap_free = meminfo.get("SwapFree", 0)
    swap_used = max(0, swap_total - swap_free)
    return {
        "hostname": os.uname().nodename,
        "load": load,
        "memory": {
            "total_mb": round(total / 1024, 1),
            "available_mb": round(avail / 1024, 1),
            "used_mb": round((total - avail) / 1024, 1),
            "used_percent": round((total - avail) * 100 / total, 1) if total else 0,
        },
        "swap": {
            "total_mb": round(swap_total / 1024, 1),
            "free_mb": round(swap_free / 1024, 1),
            "used_mb": round(swap_used / 1024, 1),
            "used_percent": round(swap_used * 100 / swap_total, 1) if swap_total else 0,
        },
        "disk_root": disk,
    }


def unit_action(unit: str, action: str) -> Dict[str, Any]:
    if not is_allowed_unit_name(unit):
        return {"ok": False, "error": "invalid unit name"}
    if action not in {"start", "stop", "restart", "reload"}:
        return {"ok": False, "error": "invalid action"}
    cp = run_cmd([SYSTEMCTL, action, unit], timeout=30)
    return {"ok": cp.returncode == 0, "returncode": cp.returncode, "stdout": cp.stdout[-4000:], "stderr": cp.stderr[-4000:]}


def unit_boot_action(unit: str, action: str) -> Dict[str, Any]:
    if not is_allowed_unit_name(unit):
        return {"ok": False, "error": "invalid unit name"}
    if action not in {"enable", "disable"}:
        return {"ok": False, "error": "invalid boot action"}
    unit_type = unit.rsplit(".", 1)[-1]
    if unit_type not in {"service", "socket", "timer"}:
        return {"ok": False, "error": "boot management is limited to service/socket/timer units"}

    states_raw = run_cmd([SYSTEMCTL, "list-unit-files", f"--type={unit_type}", "--no-legend", "--no-pager"], timeout=12).stdout
    states = parse_unit_file_states(states_raw)
    current = states.get(unit, "unknown")
    if action == "enable" and current != "disabled":
        return {"ok": False, "error": f"unit is not enable-able from current state: {current}", "unit_file_state": current}
    if action == "disable" and current not in {"enabled", "enabled-runtime"}:
        return {"ok": False, "error": f"unit is not disable-able from current state: {current}", "unit_file_state": current}

    cp = run_cmd([SYSTEMCTL, action, unit], timeout=30)
    new_raw = run_cmd([SYSTEMCTL, "list-unit-files", f"--type={unit_type}", "--no-legend", "--no-pager"], timeout=12).stdout if cp.returncode == 0 else ""
    new_state = parse_unit_file_states(new_raw).get(unit, current) if new_raw else current
    return {
        "ok": cp.returncode == 0,
        "returncode": cp.returncode,
        "stdout": cp.stdout[-4000:],
        "stderr": cp.stderr[-4000:],
        "unit_file_state": new_state,
    }


def unit_logs(unit: str, lines: int = 120) -> Dict[str, Any]:
    if not is_allowed_unit_name(unit):
        return {"ok": False, "error": "invalid unit name"}
    lines = max(10, min(lines, 500))
    cp = run_cmd(["journalctl", "-u", unit, "--no-pager", "-n", str(lines)], timeout=12)
    return {"ok": cp.returncode == 0, "text": cp.stdout[-20000:] if cp.stdout else cp.stderr[-20000:]}


def unit_status(unit: str) -> Dict[str, Any]:
    if not is_allowed_unit_name(unit):
        return {"ok": False, "error": "invalid unit name"}
    cp = run_cmd([SYSTEMCTL, "status", unit, "--no-pager", "-l"], timeout=12)
    return {"ok": cp.returncode in (0, 3), "returncode": cp.returncode, "text": (cp.stdout + cp.stderr)[-20000:]}
