#!/usr/bin/env bash
#
# Small local developer smoke test script.
#
# Read this header first: this script performs quick compile/startup checks
# against the packaging workspace and the installed launcher. It is useful for
# a future Codex session that wants the shortest sanity check after edits
# without manually reconstructing the commands. It is related to
# `install-local.sh` and the packaged sources under `src/snipcom_app`.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$ROOT_DIR/src/snipcom_app"
INSTALL_SCRIPT="$ROOT_DIR/scripts/install-local.sh"
LAUNCHER="$HOME/.local/bin/snipcom"

echo "[dev-smoke] compiling core modules"
python3 -m py_compile \
  "$SRC_DIR/app.py" \
  "$SRC_DIR/cli.py" \
  "$SRC_DIR/entrypoint.py" \
  "$SRC_DIR/app_state.py" \
  "$SRC_DIR/ai.py" \
  "$SRC_DIR/command_store.py" \
  "$SRC_DIR/controllers.py" \
  "$SRC_DIR/desktop_integration.py" \
  "$SRC_DIR/helpers.py" \
  "$SRC_DIR/importers.py" \
  "$SRC_DIR/linked_terminal.py" \
  "$SRC_DIR/main_window.py" \
  "$SRC_DIR/profiles.py" \
  "$SRC_DIR/repository.py" \
  "$SRC_DIR/safety.py" \
  "$SRC_DIR/source_sync.py" \
  "$SRC_DIR/store_window.py" \
  "$SRC_DIR/widgets.py"

echo "[dev-smoke] reinstalling local launcher"
bash "$INSTALL_SCRIPT"

echo "[dev-smoke] starting offscreen launcher smoke test"
set +e
timeout 8s env QT_QPA_PLATFORM=offscreen "$LAUNCHER"
status=$?
set -e

if [[ "$status" -ne 0 && "$status" -ne 124 ]]; then
  echo "[dev-smoke] launcher exited unexpectedly with status $status" >&2
  exit "$status"
fi

echo "[dev-smoke] smoke test completed"
