#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="${APP_NAME:-tiny-service-panel}"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
REMOVE_BACKUPS="${REMOVE_BACKUPS:-1}"

usage() {
  cat <<USAGE
Usage:
  sudo bash uninstall.sh

Options by env:
  APP_DIR=/opt/tiny-service-panel   installed directory, default: /opt/tiny-service-panel
  APP_NAME=tiny-service-panel       systemd unit prefix, default: tiny-service-panel
  REMOVE_BACKUPS=1                  remove APP_DIR.bak.* backups, default: 1

Examples:
  sudo bash /opt/tiny-service-panel/uninstall.sh
  sudo REMOVE_BACKUPS=0 bash /opt/tiny-service-panel/uninstall.sh
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "ERROR: uninstall needs root. Please run as root or install sudo." >&2
    exit 1
  fi
  exec sudo env APP_NAME="${APP_NAME}" APP_DIR="${APP_DIR}" REMOVE_BACKUPS="${REMOVE_BACKUPS}" bash "$0" "$@"
fi

# Safety guard: never allow broad system directories to be removed.
case "${APP_DIR}" in
  ""|"/"|"/opt"|"/etc"|"/usr"|"/var"|"/home"|"/root"|"/tmp")
    echo "ERROR: refusing unsafe APP_DIR: ${APP_DIR}" >&2
    exit 2
    ;;
esac

APP_PARENT="$(dirname "${APP_DIR}")"
APP_BASE="$(basename "${APP_DIR}")"
if [[ -d "${APP_PARENT}" ]]; then
  APP_PARENT_ABS="$(cd "${APP_PARENT}" && pwd -P)"
else
  APP_PARENT_ABS="${APP_PARENT}"
fi
APP_DIR_ABS="${APP_PARENT_ABS}/${APP_BASE}"

if [[ "${APP_BASE}" == "." || "${APP_BASE}" == ".." || -z "${APP_BASE}" ]]; then
  echo "ERROR: invalid APP_DIR basename: ${APP_DIR}" >&2
  exit 2
fi

SOCKET_UNIT="${APP_NAME}.socket"
SERVICE_UNIT="${APP_NAME}.service"

echo "[1/5] Stopping and disabling systemd units ..."
if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now "${SOCKET_UNIT}" 2>/dev/null || true
  systemctl stop "${SERVICE_UNIT}" 2>/dev/null || true
  systemctl disable "${SERVICE_UNIT}" 2>/dev/null || true
else
  echo "      systemctl not found, skipping service stop/disable"
fi

echo "[2/5] Removing systemd unit files and symlinks ..."
rm -f \
  "/etc/systemd/system/${SOCKET_UNIT}" \
  "/etc/systemd/system/${SERVICE_UNIT}" \
  "/etc/systemd/system/sockets.target.wants/${SOCKET_UNIT}" \
  "/etc/systemd/system/multi-user.target.wants/${SERVICE_UNIT}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload || true
  systemctl reset-failed "${SOCKET_UNIT}" "${SERVICE_UNIT}" 2>/dev/null || true
fi

echo "[3/5] Removing installed files: ${APP_DIR_ABS} ..."
rm -rf --one-file-system "${APP_DIR_ABS}"

if [[ "${REMOVE_BACKUPS}" == "1" ]]; then
  echo "[4/5] Removing installer backup directories: ${APP_PARENT_ABS}/${APP_BASE}.bak.* ..."
  if [[ -d "${APP_PARENT_ABS}" ]]; then
    find "${APP_PARENT_ABS}" -maxdepth 1 -type d -name "${APP_BASE}.bak.*" -exec rm -rf --one-file-system {} +
  fi
else
  echo "[4/5] Keeping backup directories because REMOVE_BACKUPS=${REMOVE_BACKUPS}"
fi

echo "[5/5] Verifying cleanup ..."
if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-unit-files "${SOCKET_UNIT}" "${SERVICE_UNIT}" --no-legend 2>/dev/null | grep -q .; then
    echo "WARNING: systemd still reports matching units; check manually:" >&2
    echo "  systemctl status ${SOCKET_UNIT} ${SERVICE_UNIT} --no-pager -l" >&2
  else
    echo "      systemd unit files removed"
  fi
fi

if [[ -e "${APP_DIR_ABS}" ]]; then
  echo "WARNING: install dir still exists: ${APP_DIR_ABS}" >&2
else
  echo "      install dir removed"
fi

echo ""
echo "Tiny Service Panel has been uninstalled."
echo "If you also want to remove uploaded files in your home directory, run manually:"
echo "  rm -f ~/tiny-service-panel.tar.gz ~/install-local.sh ~/uninstall.sh"
