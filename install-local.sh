#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="tiny-service-panel"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
PORT="${PORT:-8765}"
USER_NAME="${USER_NAME:-root}"
ARCHIVE="${1:-}"

usage() {
  cat <<USAGE
Usage:
  bash install-local.sh tiny-service-panel.tar.gz

Options by env:
  PORT=9876                 change listen port, default: 8765
  APP_DIR=/opt/name          change install dir, default: /opt/tiny-service-panel
  USER_NAME=root             systemd service user, default: root

Example:
  PORT=9876 bash install-local.sh tiny-service-panel.tar.gz
USAGE
}

if [[ "${ARCHIVE}" == "-h" || "${ARCHIVE}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -z "${ARCHIVE}" ]]; then
  if [[ -f "./${APP_NAME}.tar.gz" ]]; then
    ARCHIVE="./${APP_NAME}.tar.gz"
  else
    usage >&2
    exit 2
  fi
fi

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "ERROR: archive not found: ${ARCHIVE}" >&2
  exit 2
fi

if command -v readlink >/dev/null 2>&1; then
  ARCHIVE_ABS="$(readlink -f "${ARCHIVE}")"
else
  ARCHIVE_ABS="$(cd "$(dirname "${ARCHIVE}")" && pwd)/$(basename "${ARCHIVE}")"
fi

if [[ "$(id -u)" -ne 0 ]]; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "ERROR: this installer needs root. Please install sudo or run as root." >&2
    exit 1
  fi
  exec sudo env APP_DIR="${APP_DIR}" PORT="${PORT}" USER_NAME="${USER_NAME}" bash "$0" "${ARCHIVE_ABS}"
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $1" >&2
    exit 1
  }
}

need_cmd tar
need_cmd python3
need_cmd systemctl

if [[ ! -f "${ARCHIVE_ABS}" ]]; then
  echo "ERROR: archive not readable after sudo: ${ARCHIVE_ABS}" >&2
  exit 2
fi

TMP_DIR="$(mktemp -d)"
NEW_DIR="${APP_DIR}.new.$$"
BACKUP_DIR="${APP_DIR}.bak.$(date +%Y%m%d-%H%M%S)"
META_BACKUP=""
cleanup() {
  rm -rf "${TMP_DIR}" "${NEW_DIR}" 2>/dev/null || true
  [[ -n "${META_BACKUP}" && -f "${META_BACKUP}" ]] && rm -f "${META_BACKUP}" 2>/dev/null || true
}
trap cleanup EXIT

echo "[1/5] Extracting ${ARCHIVE_ABS} ..."
tar -xzf "${ARCHIVE_ABS}" -C "${TMP_DIR}"

SRC_DIR="${TMP_DIR}/${APP_NAME}"
if [[ ! -d "${SRC_DIR}" ]]; then
  SRC_DIR="$(find "${TMP_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n 1 || true)"
fi

if [[ -z "${SRC_DIR}" || ! -f "${SRC_DIR}/server.py" || ! -d "${SRC_DIR}/tiny_service_panel" ]]; then
  echo "ERROR: invalid package. Expected server.py and tiny_service_panel/ inside archive." >&2
  exit 1
fi

echo "[2/5] Installing files to ${APP_DIR} ..."
mkdir -p "$(dirname "${APP_DIR}")"
rm -rf "${NEW_DIR}"
cp -a "${SRC_DIR}" "${NEW_DIR}"

# Preserve user notes/favorites on upgrade.
if [[ -f "${APP_DIR}/data/metadata.json" ]]; then
  META_BACKUP="$(mktemp)"
  cp -a "${APP_DIR}/data/metadata.json" "${META_BACKUP}"
  mkdir -p "${NEW_DIR}/data"
  cp -a "${META_BACKUP}" "${NEW_DIR}/data/metadata.json"
fi

if systemctl list-unit-files "${APP_NAME}.socket" >/dev/null 2>&1; then
  systemctl stop "${APP_NAME}.socket" "${APP_NAME}.service" 2>/dev/null || true
fi

if [[ -e "${APP_DIR}" ]]; then
  rm -rf "${BACKUP_DIR}"
  mv "${APP_DIR}" "${BACKUP_DIR}"
  echo "      previous install moved to ${BACKUP_DIR}"
fi
mv "${NEW_DIR}" "${APP_DIR}"
chmod +x "${APP_DIR}/install.sh" "${APP_DIR}/server.py"
if [[ -f "${APP_DIR}/uninstall.sh" ]]; then
  chmod +x "${APP_DIR}/uninstall.sh"
fi
if [[ -f "${APP_DIR}/install-online.sh" ]]; then
  chmod +x "${APP_DIR}/install-online.sh"
fi

echo "[3/5] Installing systemd units on port ${PORT} ..."
APP_DIR="${APP_DIR}" PORT="${PORT}" USER_NAME="${USER_NAME}" "${APP_DIR}/install.sh"

echo "[4/5] Verifying socket ..."
systemctl is-active --quiet "${APP_NAME}.socket"
echo "      ${APP_NAME}.socket is active"

echo "[5/5] Done."
echo ""
echo "Local URL: http://127.0.0.1:${PORT}"
echo "Check:     curl http://127.0.0.1:${PORT}/api/summary"
echo "Logs:      journalctl -u ${APP_NAME}.service -n 100 --no-pager"
