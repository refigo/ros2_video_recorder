#!/bin/bash
# Install ros2-camera-recorder as a user systemd service + deliver cron job.
#
# Usage:
#   deploy/install.sh
#
# Idempotent — safe to re-run. Does NOT start the service.
# After install, run: deploy/start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="ros2-camera-recorder"
UNIT_DIR="$HOME/.config/systemd/user"
LOG_DIR="$HOME/.local/log/ros2-recorder"

echo "=== $SERVICE_NAME installer ==="
echo "Repo: $REPO_ROOT"

# --- 1. Resolve env file ---
if [ -n "${RECORDER_ENV_FILE:-}" ] && [ -f "$RECORDER_ENV_FILE" ]; then
    ENV_FILE="$RECORDER_ENV_FILE"
elif [ -f "$REPO_ROOT/.env" ]; then
    ENV_FILE="$REPO_ROOT/.env"
elif [ -f "/etc/ros2-recorder/recorder.env" ]; then
    ENV_FILE="/etc/ros2-recorder/recorder.env"
else
    echo "WARN: no env file found. Create one from config/recorder.env.example before starting." >&2
    ENV_FILE="$REPO_ROOT/.env"
fi
echo "Env file: $ENV_FILE"

# --- 2. Setup venv ---
VENV_DIR="$REPO_ROOT/.venv_xrdc"
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "Creating venv at $VENV_DIR ..."
    uv venv --python /usr/bin/python3.10 "$VENV_DIR"
    uv pip install --python "$VENV_DIR/bin/python" -r "$REPO_ROOT/requirements.txt"
    echo "[OK] venv created + deps installed"
else
    echo "[SKIP] venv already exists: $VENV_DIR"
fi

# --- 3. Install systemd user unit ---
mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=ROS2 Camera Recorder (topview RGB)
After=network.target

[Service]
Type=simple
Environment=RECORDER_ENV_FILE=${ENV_FILE}
ExecStart=${REPO_ROOT}/scripts/start_recorder.sh
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
echo "[OK] systemd user unit installed: $UNIT_DIR/${SERVICE_NAME}.service"

# --- 4. Log directory ---
mkdir -p "$LOG_DIR"
echo "[OK] log directory: $LOG_DIR"

# --- 5. Cron entry (disabled — start.sh enables it) ---
CRON_MARKER="# ros2-recorder-deliver"
CRON_CMD="1 * * * * RECORDER_ENV_FILE=${ENV_FILE} ${REPO_ROOT}/scripts/deliver.sh >> ${LOG_DIR}/deliver.log 2>&1 ${CRON_MARKER}"
EXISTING_CRON=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING_CRON" | grep -qF "ros2-recorder-deliver"; then
    # Update existing entry
    UPDATED_CRON=$(echo "$EXISTING_CRON" | grep -v "ros2-recorder-deliver")
    echo "$UPDATED_CRON" | crontab -
    echo "[OK] cron entry updated (currently disabled — deploy/start.sh enables it)"
else
    echo "[OK] cron entry prepared (currently disabled — deploy/start.sh enables it)"
fi

# --- 6. Enable linger (service runs even when logged out) ---
if command -v loginctl &>/dev/null; then
    loginctl enable-linger "$(whoami)" 2>/dev/null || true
    echo "[OK] linger enabled for $(whoami)"
fi

# --- Summary ---
echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Create env file (if not done):"
echo "       cp config/recorder.env.example .env"
echo "       \${EDITOR:-nano} .env"
echo "  2. Test manually:  scripts/start_recorder.sh  (Ctrl+C to stop)"
echo "  3. Start service:  deploy/start.sh"
echo "  4. Check logs:     journalctl --user -u ${SERVICE_NAME} -f"
