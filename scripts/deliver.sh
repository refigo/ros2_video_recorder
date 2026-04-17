#!/bin/bash
# Cron wrapper: loads env file, invokes deliver.py via system python3.10.
#
# Deliver: embed SRT → upload to Drive → MD5 verify → delete local
#
# Cron entry example (M5):
#   1 * * * * /opt/ros2-recorder/scripts/deliver.sh >> /var/log/ros2-recorder/deliver.log 2>&1
#
# Env file path can be overridden: UPLOADER_ENV_FILE=/path/to/uploader.env

set -euo pipefail

ENV_FILE="${UPLOADER_ENV_FILE:-/etc/ros2-recorder/uploader.env}"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
else
    echo "WARN: env file not found at $ENV_FILE — relying on inherited env" >&2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3.10}"
exec "$PYTHON_BIN" "$SCRIPT_DIR/deliver.py" "$@"
