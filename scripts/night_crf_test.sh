#!/bin/bash
# Night CRF comparison test — run 3 recordings with different CRF settings.
#
# Usage (via cron — see bottom of file for crontab entries):
#   night_crf_test.sh <label> [extra ffmpeg args...]
#
# Examples:
#   night_crf_test.sh crf28
#   night_crf_test.sh crf30 --crf 30
#   night_crf_test.sh crf28_maxrate2M --crf 28 --maxrate 2M
#
# Each run records for 1 hour then kills the recorder.
# Output goes to videos/ with branch-id "NIGHTTEST".

set -euo pipefail

LABEL="${1:?Usage: $0 <label> [extra args...]}"
shift

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3.10}"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/night_test_${LABEL}_$(date +%Y%m%d_%H%M%S).log"

echo "=== Night CRF test: $LABEL ===" | tee "$LOG_FILE"
echo "Start: $(date --iso-8601=seconds)" | tee -a "$LOG_FILE"
echo "Args: $*" | tee -a "$LOG_FILE"

# Source ROS2 environment
source /opt/ros/humble/setup.bash

# Start recorder in background
$PYTHON_BIN "$REPO_ROOT/camera_recorder.py" \
    --branch-id NIGHTTEST \
    --video-label "${LABEL}" \
    --ffmpeg \
    "$@" \
    >> "$LOG_FILE" 2>&1 &

RECORDER_PID=$!
echo "Recorder PID: $RECORDER_PID" | tee -a "$LOG_FILE"

# Let it record for 1 hour (3600 seconds), then gracefully stop
sleep 3600

echo "Stopping recorder (SIGINT)..." | tee -a "$LOG_FILE"
kill -INT "$RECORDER_PID" 2>/dev/null || true
wait "$RECORDER_PID" 2>/dev/null || true

echo "End: $(date --iso-8601=seconds)" | tee -a "$LOG_FILE"
echo "=== Done: $LABEL ===" | tee -a "$LOG_FILE"

# Crontab entries (paste with: crontab -e)
# ---
# # Night CRF test 2026-04-18
# 0 1 18 4 * /home/refi/git_repo_mine/ros2_video_recorder/scripts/night_crf_test.sh crf28 --crf 28
# 0 2 18 4 * /home/refi/git_repo_mine/ros2_video_recorder/scripts/night_crf_test.sh crf30 --crf 30
# 0 3 18 4 * /home/refi/git_repo_mine/ros2_video_recorder/scripts/night_crf_test.sh crf28_maxrate2M --crf 28 --maxrate 2M
# # Cleanup: remove all night_crf_test entries after last test finishes (~4:05)
# 5 4 18 4 * crontab -l | grep -v 'night_crf_test\|Night CRF test' | crontab -
# ---
