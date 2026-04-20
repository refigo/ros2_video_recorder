#!/bin/bash
# Wrapper for camera_recorder.py — sources ROS2 environment and maps
# env vars to CLI arguments.
#
# Used by systemd (ros2-camera-recorder.service) or manual invocation.
# Env file is auto-loaded from RECORDER_ENV_FILE, .env, or /etc/ros2-recorder/recorder.env.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Load env file if not already loaded by systemd
if [ -n "${RECORDER_ENV_FILE:-}" ] && [ -f "$RECORDER_ENV_FILE" ]; then
    set -a && source "$RECORDER_ENV_FILE" && set +a
elif [ -f "$REPO_ROOT/.env" ]; then
    set -a && source "$REPO_ROOT/.env" && set +a
elif [ -f "/etc/ros2-recorder/recorder.env" ]; then
    set -a && source "/etc/ros2-recorder/recorder.env" && set +a
fi

# Source ROS2 Humble (disable nounset — setup.bash uses unset vars internally)
set +u
source /opt/ros/humble/setup.bash
set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-22}"

PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3.10}"

ARGS=(
    --branch-id "${BRANCH_ID:?BRANCH_ID not set}"
    --video-label "${VIDEO_LABEL:-topview_video}"
    --ffmpeg
    --crf "${CRF:-28}"
    --segment "${SEGMENT:-3600}"
    --topic "${TOPIC:-/camera/color/image_raw}"
    --fps "${FPS:-30}"
)

[ -n "${MAXRATE:-}" ] && ARGS+=(--maxrate "$MAXRATE")
[ -n "${VIDEOS_DIR:-}" ] && ARGS+=(--output-dir "$VIDEOS_DIR")

exec "$PYTHON_BIN" "$REPO_ROOT/camera_recorder.py" "${ARGS[@]}"
