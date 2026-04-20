#!/bin/bash
# Install ros2-camera-recorder systemd service and deliver cron job.
#
# Usage:
#   sudo scripts/install.sh [REPO_INSTALL_PATH]
#
# REPO_INSTALL_PATH defaults to /opt/ros2-recorder.
# This script is idempotent — safe to re-run.
#
# What it does:
#   1. Copies systemd unit (updates ExecStart path)
#   2. Creates log directory for deliver.sh
#   3. Registers hourly cron entry for deliver.sh (if not already present)
#
# What it does NOT do:
#   - Enable or start the service (do that manually after verification)
#   - Create /etc/ros2-recorder/recorder.env (see config/recorder.env.example)
#   - Copy the SA key (see docs/spec/deployment_checklist.md)

set -euo pipefail

REPO_INSTALL_PATH="${1:-/opt/ros2-recorder}"
SERVICE_NAME="ros2-camera-recorder"
CRON_USER="${SUDO_USER:-refi}"
LOG_DIR="/var/log/ros2-recorder"

echo "=== ros2-camera-recorder installer ==="
echo "Install path: $REPO_INSTALL_PATH"

# --- 1. systemd unit ---
UNIT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/systemd/${SERVICE_NAME}.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"

if [ ! -f "$UNIT_SRC" ]; then
    echo "ERROR: unit file not found at $UNIT_SRC" >&2
    exit 1
fi

# Patch ExecStart to match actual install path
sed "s|/opt/ros2-recorder|${REPO_INSTALL_PATH}|g" "$UNIT_SRC" > "$UNIT_DST"
chmod 644 "$UNIT_DST"
systemctl daemon-reload
echo "[OK] systemd unit installed: $UNIT_DST"

# --- 2. Log directory ---
mkdir -p "$LOG_DIR"
chown "$CRON_USER":"$CRON_USER" "$LOG_DIR"
echo "[OK] log directory: $LOG_DIR"

# --- 3. Cron entry ---
CRON_CMD="1 * * * * ${REPO_INSTALL_PATH}/scripts/deliver.sh >> ${LOG_DIR}/deliver.log 2>&1"
EXISTING_CRON=$(crontab -u "$CRON_USER" -l 2>/dev/null || true)

if echo "$EXISTING_CRON" | grep -qF "deliver.sh"; then
    echo "[SKIP] cron entry already exists for deliver.sh"
else
    (echo "$EXISTING_CRON"; echo "# ros2-camera-recorder: hourly upload pipeline"; echo "$CRON_CMD") | crontab -u "$CRON_USER" -
    echo "[OK] cron entry added for $CRON_USER"
fi

# --- Summary ---
echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Create env file:  sudo cp config/recorder.env.example /etc/ros2-recorder/recorder.env"
echo "     Edit placeholders: sudo nano /etc/ros2-recorder/recorder.env"
echo "  2. Copy SA key:      sudo cp <key>.json /etc/ros2-recorder/keys/company-sa.json"
echo "  3. Test manually:    scripts/start_recorder.sh   (verify recording works)"
echo "  4. Enable + start:   sudo systemctl enable --now ${SERVICE_NAME}"
echo "  5. Check logs:       journalctl -u ${SERVICE_NAME} -f"
