#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="tiny-service-panel"
REPO="${REPO:-fenghuixianyu/tiny-service-panel}"
REF="${REF:-main}"
APP_DIR="${APP_DIR:-/opt/${APP_NAME}}"
PORT="${PORT:-8765}"
USER_NAME="${USER_NAME:-root}"
ARCHIVE_URL="${ARCHIVE_URL:-https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz}"

usage() {
  cat <<USAGE
Usage:
  curl -fsSL https://raw.githubusercontent.com/${REPO}/${REF}/install-online.sh | sudo bash

Options by env:
  PORT=9876                 change listen port, default: 8765
  APP_DIR=/opt/name          change install dir, default: /opt/tiny-service-panel
  USER_NAME=root             systemd service user, default: root
  REF=main                   Git ref to install, default: main
  REPO=${REPO}               GitHub repo, default: ${REPO}

Example:
  curl -fsSL https://raw.githubusercontent.com/${REPO}/${REF}/install-online.sh | sudo env PORT=9876 bash
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: this installer needs root." >&2
  echo "Run:" >&2
  echo "  curl -fsSL https://raw.githubusercontent.com/${REPO}/${REF}/install-online.sh | sudo bash" >&2
  exit 1
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

TMP_DIR="$(mktemp -d)"
NEW_DIR="${APP_DIR}.new.$$"
BACKUP_DIR="${APP_DIR}.bak.$(date +%Y%m%d-%H%M%S)"
META_BACKUP=""
cleanup() {
  rm -rf "${TMP_DIR}" "${NEW_DIR}" 2>/dev/null || true
  [[ -n "${META_BACKUP}" && -f "${META_BACKUP}" ]] && rm -f "${META_BACKUP}" 2>/dev/null || true
}
trap cleanup EXIT

ARCHIVE="${TMP_DIR}/${APP_NAME}.tar.gz"
echo "[1/5] Downloading ${ARCHIVE_URL} ..."
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "${ARCHIVE_URL}" -o "${ARCHIVE}"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "${ARCHIVE}" "${ARCHIVE_URL}"
else
  echo "ERROR: missing curl or wget." >&2
  exit 1
fi

echo "[2/5] Extracting package ..."
tar -xzf "${ARCHIVE}" -C "${TMP_DIR}"
SRC_DIR="$(find "${TMP_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n 1 || true)"
if [[ -z "${SRC_DIR}" || ! -f "${SRC_DIR}/server.py" || ! -d "${SRC_DIR}/tiny_service_panel" ]]; then
  echo "ERROR: invalid package downloaded from ${ARCHIVE_URL}" >&2
  exit 1
fi

echo "[3/5] Installing files to ${APP_DIR} ..."
mkdir -p "$(dirname "${APP_DIR}")"
rm -rf "${NEW_DIR}"
cp -a "${SRC_DIR}" "${NEW_DIR}"

# Preserve notes/favorites on upgrade.
if [[ -f "${APP_DIR}/data/metadata.json" ]]; then
  META_BACKUP="$(mktemp)"
  cp -a "${APP_DIR}/data/metadata.json" "${META_BACKUP}"
  mkdir -p "${NEW_DIR}/data"
  cp -a "${META_BACKUP}" "${NEW_DIR}/data/metadata.json"
fi

systemctl stop "${APP_NAME}.socket" "${APP_NAME}.service" 2>/dev/null || true

if [[ -e "${APP_DIR}" ]]; then
  rm -rf "${BACKUP_DIR}"
  mv "${APP_DIR}" "${BACKUP_DIR}"
  echo "      previous install moved to ${BACKUP_DIR}"
fi
mv "${NEW_DIR}" "${APP_DIR}"
chmod +x "${APP_DIR}/install.sh" "${APP_DIR}/server.py" "${APP_DIR}/uninstall.sh" 2>/dev/null || true

if [[ -f "${APP_DIR}/install-online.sh" ]]; then
  chmod +x "${APP_DIR}/install-online.sh"
fi
if [[ -f "${APP_DIR}/install-local.sh" ]]; then
  chmod +x "${APP_DIR}/install-local.sh"
fi

echo "[4/5] Installing systemd units on port ${PORT} ..."
APP_DIR="${APP_DIR}" PORT="${PORT}" USER_NAME="${USER_NAME}" "${APP_DIR}/install.sh"

echo "[5/5] Done."
echo ""
echo "Local URL: http://127.0.0.1:${PORT}"
echo "Check:     curl http://127.0.0.1:${PORT}/api/summary"
echo "Uninstall: sudo bash ${APP_DIR}/uninstall.sh"
echo "Logs:      journalctl -u ${APP_NAME}.service -n 100 --no-pager"
