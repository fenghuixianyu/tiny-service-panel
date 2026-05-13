#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tiny-service-panel}"
PORT="${PORT:-8765}"
USER_NAME="${USER_NAME:-root}"
BIND_HOST="${BIND_HOST:-127.0.0.1}"
AUTH_PASSWORD="${AUTH_PASSWORD:-}"
AUTH_DISABLE="${AUTH_DISABLE:-0}"
AUTH_ENV_FILE="${AUTH_ENV_FILE:-/etc/tiny-service-panel/auth.env}"
AUTH_COOKIE_DAYS="${AUTH_COOKIE_DAYS:-30}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: install.sh needs root because it writes /etc/systemd/system and runs systemctl." >&2
  echo "Tip: run: sudo env APP_DIR=${APP_DIR} PORT=${PORT} BIND_HOST=${BIND_HOST} USER_NAME=${USER_NAME} ./install.sh" >&2
  exit 1
fi

is_loopback_bind() {
  case "$BIND_HOST" in
    127.*|localhost|::1) return 0 ;;
    *) return 1 ;;
  esac
}

GENERATED_PASSWORD="0"
if [[ "$AUTH_DISABLE" == "1" ]]; then
  rm -f "$AUTH_ENV_FILE"
  echo "WARNING: password auth disabled by AUTH_DISABLE=1"
elif [[ -f "$AUTH_ENV_FILE" && -z "$AUTH_PASSWORD" ]]; then
  echo "Keeping existing auth config: $AUTH_ENV_FILE"
elif [[ -z "$AUTH_PASSWORD" ]] && is_loopback_bind; then
  echo "Password auth is disabled because BIND_HOST=$BIND_HOST is loopback-only."
else
  if [[ -z "$AUTH_PASSWORD" ]]; then
    AUTH_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
)"
    GENERATED_PASSWORD="1"
  fi
  mkdir -p "$(dirname "$AUTH_ENV_FILE")"
  AUTH_PASSWORD="$AUTH_PASSWORD" AUTH_ENV_FILE="$AUTH_ENV_FILE" AUTH_COOKIE_DAYS="$AUTH_COOKIE_DAYS" python3 - <<'PY'
import hashlib
import os
import secrets
from pathlib import Path

password = os.environ["AUTH_PASSWORD"]
env_file = Path(os.environ["AUTH_ENV_FILE"])
cookie_days = int(os.environ.get("AUTH_COOKIE_DAYS", "30") or "30")
iterations = 260000
salt = secrets.token_bytes(16)
digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()
secret = secrets.token_urlsafe(32)
content = "\n".join([
    f"TSP_AUTH_HASH=pbkdf2_sha256${iterations}${salt.hex()}${digest}",
    f"TSP_SECRET={secret}",
    f"TSP_AUTH_COOKIE_DAYS={cookie_days}",
    "TSP_COOKIE_SECURE=0",
    "",
])
env_file.write_text(content)
os.chmod(env_file, 0o600)
print(env_file)
PY
fi

PYTHONPATH="$APP_DIR" PORT="$PORT" USER_NAME="$USER_NAME" APP_DIR="$APP_DIR" BIND_HOST="$BIND_HOST" AUTH_ENV_FILE="$AUTH_ENV_FILE" python3 - <<'PY'
import os
from pathlib import Path
from tiny_service_panel.core import render_systemd_units

files = render_systemd_units(
    port=int(os.environ["PORT"]),
    user=os.environ["USER_NAME"],
    app_dir=os.environ["APP_DIR"],
    bind_host=os.environ["BIND_HOST"],
    auth_env_file=os.environ["AUTH_ENV_FILE"],
)
for name, content in files.items():
    path = Path("/etc/systemd/system") / name
    path.write_text(content)
    print(path)
PY

chmod +x "$APP_DIR/server.py"
[[ -f "$APP_DIR/uninstall.sh" ]] && chmod +x "$APP_DIR/uninstall.sh"
systemctl daemon-reload
systemctl enable tiny-service-panel.socket
systemctl restart tiny-service-panel.socket
systemctl stop tiny-service-panel.service 2>/dev/null || true
systemctl status tiny-service-panel.socket --no-pager -l

if [[ "$BIND_HOST" == "0.0.0.0" || "$BIND_HOST" == "::" ]]; then
  DISPLAY_HOST="<server-ip>"
else
  DISPLAY_HOST="$BIND_HOST"
fi

printf '\nTiny Service Panel installed at http://%s:%s\n' "$DISPLAY_HOST" "$PORT"
if [[ "$GENERATED_PASSWORD" == "1" ]]; then
  printf 'Generated login password: %s\n' "$AUTH_PASSWORD"
  printf 'Save this password now. It is not printed again.\n'
elif [[ -n "$AUTH_PASSWORD" ]]; then
  printf 'Login password: configured from AUTH_PASSWORD\n'
elif [[ -f "$AUTH_ENV_FILE" ]]; then
  printf 'Login password: existing auth config kept from %s\n' "$AUTH_ENV_FILE"
else
  printf 'Login password: disabled\n'
fi
