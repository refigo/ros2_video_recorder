#!/bin/bash
# Stop ros2-camera-recorder service + disable deliver cron.
#
# Usage:
#   deploy/stop.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="ros2-camera-recorder"

# --- 1. Stop recorder service ---
if systemctl --user is-active "$SERVICE_NAME" &>/dev/null; then
    systemctl --user stop "$SERVICE_NAME"
    echo "[OK] recorder stopped"
else
    echo "[SKIP] recorder not running"
fi

# --- 2. Disable deliver cron ---
EXISTING_CRON=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING_CRON" | grep -qF "ros2-recorder-deliver"; then
    echo "$EXISTING_CRON" | grep -v "ros2-recorder-deliver" | crontab -
    echo "[OK] deliver cron disabled"
else
    echo "[SKIP] deliver cron not active"
fi
