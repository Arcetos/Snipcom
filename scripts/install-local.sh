#!/usr/bin/env bash
#
# Local installer for the current packaging workspace.
#
# Read this header first: this script installs the launcher, Python package,
# desktop file, icon, and metainfo into the user's local directories under
# `~/.local`. If a future Codex session only needs to know how the app is
# locally installed or reinstalled, this header is enough and it can decide
# whether to keep reading. It is related to `src/snipcom` and the
# packaged Python sources under `src/snipcom_app`.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
METAINFO_DIR="${HOME}/.local/share/metainfo"

install -d "${BIN_DIR}" "${APP_DIR}" "${ICON_DIR}" "${METAINFO_DIR}"
rm -rf "${BIN_DIR}/snipcom_app"
install -m755 "${ROOT_DIR}/src/snipcom" "${BIN_DIR}/snipcom"
install -m755 "${ROOT_DIR}/src/scm" "${BIN_DIR}/scm"
cp -a "${ROOT_DIR}/src/snipcom_app" "${BIN_DIR}/snipcom_app"
install -m644 "${ROOT_DIR}/flatpak/io.github.arcetos.Snipcom.desktop" "${APP_DIR}/io.github.arcetos.Snipcom.desktop"
install -m644 "${ROOT_DIR}/assets/io.github.arcetos.Snipcom.svg" "${ICON_DIR}/io.github.arcetos.Snipcom.svg"
install -m644 "${ROOT_DIR}/flatpak/io.github.arcetos.Snipcom.metainfo.xml" "${METAINFO_DIR}/io.github.arcetos.Snipcom.metainfo.xml"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APP_DIR}" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Installed Snipcom launchers (snipcom, scm) to ${BIN_DIR} and ${APP_DIR}."
