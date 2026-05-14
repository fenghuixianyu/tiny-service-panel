#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tiny-service-panel}"
PORT="${PORT:-8765}"
USER_NAME="${USER_NAME:-root}"
BIND_HOST="${BIND_HOST:-127.0.0.1}"
AUTH_PASSWORD="${AUTH_PASSWORD:-}"
AUTH_DISABLE="${AUTH_DISABLE:-0}"
AUTH_RANDOM="${AUTH_RANDOM:-0}"
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

generate_password() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(18))
PY
}

has_tty() {
  [[ -r /dev/tty && -w /dev/tty ]]
}

prompt_auth_password() {
  local first=""
  local second=""
  while true; do
    {
      printf '\n首次公网安装需要设置 Tiny Service Panel 登录密码。\n'
      printf '请输入密码；输入 r 后回车可生成随机强密码；直接回车无效。\n'
      printf 'Password: '
    } > /dev/tty
    IFS= read -r -s first < /dev/tty || return 1
    printf '\n' > /dev/tty

    case "${first,,}" in
      r|rand|random|generate|g|随机)
        AUTH_PASSWORD="$(generate_password)"
        GENERATED_PASSWORD="1"
        printf '已生成随机强密码，安装完成后会打印一次，请及时保存。\n' > /dev/tty
        return 0
        ;;
    esac

    if [[ -z "$first" ]]; then
      printf '密码不能为空，请重新输入；或输入 r 生成随机强密码。\n' > /dev/tty
      continue
    fi

    printf 'Confirm password: ' > /dev/tty
    IFS= read -r -s second < /dev/tty || return 1
    printf '\n' > /dev/tty
    if [[ "$first" != "$second" ]]; then
      printf '两次输入不一致，请重新输入。\n' > /dev/tty
      continue
    fi

    AUTH_PASSWORD="$first"
    PROMPTED_PASSWORD="1"
    return 0
  done
}

GENERATED_PASSWORD="0"
PROMPTED_PASSWORD="0"
if [[ "$AUTH_DISABLE" == "1" ]]; then
  rm -f "$AUTH_ENV_FILE"
  echo "WARNING: password auth disabled by AUTH_DISABLE=1"
elif [[ -f "$AUTH_ENV_FILE" && -z "$AUTH_PASSWORD" && "$AUTH_RANDOM" != "1" ]]; then
  echo "Keeping existing auth config: $AUTH_ENV_FILE"
elif [[ -z "$AUTH_PASSWORD" && "$AUTH_RANDOM" != "1" ]] && is_loopback_bind; then
  echo "Password auth is disabled because BIND_HOST=$BIND_HOST is loopback-only."
else
  if [[ -z "$AUTH_PASSWORD" ]]; then
    if [[ "$AUTH_RANDOM" == "1" ]]; then
      AUTH_PASSWORD="$(generate_password)"
      GENERATED_PASSWORD="1"
    elif has_tty; then
      prompt_auth_password
    else
      echo "No TTY available for password prompt; generated a random login password."
      AUTH_PASSWORD="$(generate_password)"
      GENERATED_PASSWORD="1"
    fi
  elif [[ "$AUTH_RANDOM" == "1" ]]; then
    echo "WARNING: AUTH_RANDOM=1 ignored because AUTH_PASSWORD is already set." >&2
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
systemctl disable tiny-service-panel.service 2>/dev/null || true
systemctl enable tiny-service-panel.socket
systemctl restart tiny-service-panel.socket
systemctl stop tiny-service-panel.service 2>/dev/null || true
systemctl status tiny-service-panel.socket --no-pager -l
printf 'Autostart: tiny-service-panel.socket is %s; service stays socket-activated.\n' "$(systemctl is-enabled tiny-service-panel.socket 2>/dev/null || echo unknown)"

if [[ "$BIND_HOST" == "0.0.0.0" || "$BIND_HOST" == "::" ]]; then
  DISPLAY_HOST="<server-ip>"
else
  DISPLAY_HOST="$BIND_HOST"
fi

printf '\nTiny Service Panel installed at http://%s:%s\n' "$DISPLAY_HOST" "$PORT"
if [[ "$GENERATED_PASSWORD" == "1" ]]; then
  printf 'Generated login password: %s\n' "$AUTH_PASSWORD"
  printf 'Save this password now. It is not printed again.\n'
  printf 'Password config file: %s\n' "$AUTH_ENV_FILE"
  printf "Change later: sudo env BIND_HOST='%s' PORT='%s' AUTH_PASSWORD='new-password' %s/install.sh\n" "$BIND_HOST" "$PORT" "$APP_DIR"
elif [[ "$PROMPTED_PASSWORD" == "1" ]]; then
  printf 'Login password: configured from interactive prompt\n'
  printf 'Password config file: %s\n' "$AUTH_ENV_FILE"
  printf "Change later: sudo env BIND_HOST='%s' PORT='%s' AUTH_PASSWORD='new-password' %s/install.sh\n" "$BIND_HOST" "$PORT" "$APP_DIR"
elif [[ -n "$AUTH_PASSWORD" ]]; then
  printf 'Login password: configured from AUTH_PASSWORD\n'
  printf 'Password config file: %s\n' "$AUTH_ENV_FILE"
  printf "Change later: sudo env BIND_HOST='%s' PORT='%s' AUTH_PASSWORD='new-password' %s/install.sh\n" "$BIND_HOST" "$PORT" "$APP_DIR"
elif [[ -f "$AUTH_ENV_FILE" ]]; then
  printf 'Login password: existing auth config kept from %s\n' "$AUTH_ENV_FILE"
  printf "Change later: sudo env BIND_HOST='%s' PORT='%s' AUTH_PASSWORD='new-password' %s/install.sh\n" "$BIND_HOST" "$PORT" "$APP_DIR"
else
  printf 'Login password: disabled\n'
fi
