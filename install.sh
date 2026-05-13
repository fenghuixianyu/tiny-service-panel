#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/tiny-service-panel}"
PORT="${PORT:-8765}"
USER_NAME="${USER_NAME:-root}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: install.sh needs root because it writes /etc/systemd/system and runs systemctl." >&2
  echo "Tip: run: sudo APP_DIR=${APP_DIR} PORT=${PORT} USER_NAME=${USER_NAME} ./install.sh" >&2
  exit 1
fi

PYTHONPATH="$APP_DIR" python3 - <<PY
from tiny_service_panel.core import render_systemd_units
from pathlib import Path
files=render_systemd_units(port=int('$PORT'), user='$USER_NAME', app_dir='$APP_DIR')
for name, content in files.items():
    Path('/etc/systemd/system/'+name).write_text(content)
    print('/etc/systemd/system/'+name)
PY
chmod +x "$APP_DIR/server.py"
systemctl daemon-reload
systemctl enable --now tiny-service-panel.socket
systemctl stop tiny-service-panel.service 2>/dev/null || true
systemctl status tiny-service-panel.socket --no-pager -l
printf '\nTiny Service Panel installed at http://127.0.0.1:%s\n' "$PORT"
