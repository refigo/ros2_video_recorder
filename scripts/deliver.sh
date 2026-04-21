#!/bin/bash
# Cron wrapper: loads env file, invokes deliver.py via system python3.10.
#
# Deliver: embed SRT → upload to Drive → MD5 verify → delete local
#
# Cron entry example (M5):
#   1 * * * * /opt/ros2-recorder/scripts/deliver.sh >> /var/log/ros2-recorder/deliver.log 2>&1
#
# Env file path can be overridden: RECORDER_ENV_FILE=/path/to/recorder.env

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Resolve env file: RECORDER_ENV_FILE > .env in repo > /etc/ros2-recorder/recorder.env
if [ -n "${RECORDER_ENV_FILE:-}" ] && [ -f "$RECORDER_ENV_FILE" ]; then
    ENV_FILE="$RECORDER_ENV_FILE"
elif [ -f "$REPO_ROOT/.env" ]; then
    ENV_FILE="$REPO_ROOT/.env"
else
    ENV_FILE="/etc/ros2-recorder/recorder.env"
fi

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
else
    echo "WARN: env file not found at $ENV_FILE — relying on inherited env" >&2
fi

cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv_xrdc/bin/python}"
exec "$PYTHON_BIN" "$SCRIPT_DIR/deliver.py" "$@"
