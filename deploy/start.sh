#!/bin/bash
# Start ros2-camera-recorder service + enable deliver cron.
#
# Usage:
#   deploy/start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="ros2-camera-recorder"
LOG_DIR="$HOME/.local/log/ros2-recorder"

# --- Resolve env file (same logic as install.sh) ---
if [ -n "${RECORDER_ENV_FILE:-}" ] && [ -f "$RECORDER_ENV_FILE" ]; then
    ENV_FILE="$RECORDER_ENV_FILE"
elif [ -f "$REPO_ROOT/.env" ]; then
    ENV_FILE="$REPO_ROOT/.env"
elif [ -f "/etc/ros2-recorder/recorder.env" ]; then
    ENV_FILE="/etc/ros2-recorder/recorder.env"
else
    echo "ERROR: no env file found. Run: cp config/recorder.env.example .env" >&2
    exit 1
fi

# --- 1. Start recorder service ---
if ! systemctl --user is-enabled "$SERVICE_NAME" &>/dev/null; then
    systemctl --user enable "$SERVICE_NAME"
fi
systemctl --user start "$SERVICE_NAME"
echo "[OK] recorder started: systemctl --user status $SERVICE_NAME"

# --- 2. Enable deliver cron ---
CRON_MARKER="# ros2-recorder-deliver"
CRON_CMD="1 * * * * RECORDER_ENV_FILE=${ENV_FILE} ${REPO_ROOT}/scripts/deliver.sh >> ${LOG_DIR}/deliver.log 2>&1 ${CRON_MARKER}"
EXISTING_CRON=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING_CRON" | grep -qF "ros2-recorder-deliver"; then
    echo "[SKIP] deliver cron already active"
else
    (echo "$EXISTING_CRON"; echo "$CRON_CMD") | crontab -
    echo "[OK] deliver cron enabled (hourly at :01)"
fi

echo ""
echo "Recorder: journalctl --user -u $SERVICE_NAME -f"
echo "Deliver log: tail -f $LOG_DIR/deliver.log"
