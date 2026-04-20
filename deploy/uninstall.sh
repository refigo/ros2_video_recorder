#!/bin/bash
# Uninstall ros2-camera-recorder service + deliver cron.
#
# Usage:
#   deploy/uninstall.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="ros2-camera-recorder"
UNIT_DIR="$HOME/.config/systemd/user"

# --- 1. Stop if running ---
"$SCRIPT_DIR/stop.sh"

# --- 2. Disable + remove service ---
if [ -f "$UNIT_DIR/${SERVICE_NAME}.service" ]; then
    systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$UNIT_DIR/${SERVICE_NAME}.service"
    systemctl --user daemon-reload
    echo "[OK] systemd unit removed"
else
    echo "[SKIP] systemd unit not found"
fi

echo ""
echo "=== Uninstall complete ==="
echo "Note: log directory (~/.local/log/ros2-recorder/) and env files are preserved."
