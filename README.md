# ROS2 Camera Topic Recorder

A Python utility to record ROS2 camera topics to video files using either OpenCV or FFmpeg.

## Features

- Record ROS2 Image topics to MP4 video files
- Support for both OpenCV and FFmpeg backends
- Configurable FPS and video codecs
- **Wall-clock aligned 1-hour segments** (split at every `:00` by default)
- **File-based state machine** — `.recording_*.mp4/.srt` during recording, renamed to final on completion
- **Real-time SRT timestamps** — crash-safe, entries flushed to disk per second
- Multi-camera support via `--video-label` (e.g. `topview_video`, `gripper_video`)
- Branch-aware naming: `{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.mp4`

## Requirements

- ROS2 Humble (primary target; see `docs/study/ros2_humble_env_setup.md` for env setup)
- **Python 3.10** (system interpreter bound to ROS2 Humble)
- **NumPy 1.x** (2.x is incompatible with ROS2 Humble's `cv_bridge`)
- OpenCV
- FFmpeg (required for `--ffmpeg` mode, recommended for H.264 output)

## Installation

### Prerequisites
- ROS2 Humble installed at `/opt/ros/humble/`
- The following ROS2 packages available:
  - `ros-humble-rclpy`
  - `ros-humble-sensor-msgs`
  - `ros-humble-cv-bridge`
- System `/usr/bin/python3.10` (do NOT use uv/conda/pyenv Python for ROS2 — see env setup doc)

### Setup

1. **Source ROS2 environment** (required for each terminal session):
```bash
source /opt/ros/humble/setup.bash
```

2. **Pin NumPy to 1.x** (required — NumPy 2.x segfaults with `cv_bridge`):
```bash
/usr/bin/python3.10 -m pip install --user 'numpy<2'
```

3. **Install FFmpeg**:
```bash
sudo apt update
sudo apt install ffmpeg
```

4. **Verify the environment**:
```bash
python3.10 -c "import rclpy; from cv_bridge import CvBridge; import numpy as np; print('numpy:', np.__version__)"
# expected: numpy: 1.26.x
```

> **Important:** If you use uv/conda/pyenv for other projects, invoke this recorder with `python3.10` explicitly (absolute path: `/usr/bin/python3.10`) to avoid Python version conflicts. See `docs/study/ros2_humble_env_setup.md` for full guidance including venv-based isolation.

## Usage

### Basic Usage

Record with a branch ID (required):
```bash
python3.10 camera_recorder.py --branch-id BB003 --ffmpeg
```

Default behavior:
- Topic: `/camera/color/image_raw`
- Output directory: `videos/`
- Video label: `topview_video`
- Segmentation: wall-clock aligned, splits at every `:00`
- File naming: `BB003_20260414T140000+0900_topview_video.mp4` + `.srt`

### Advanced Usage

```bash
# Custom topic and output directory
python3.10 camera_recorder.py --branch-id BB003 --topic /my_camera/image_raw --output-dir /data/recordings --ffmpeg

# Gripper camera with different label (second recorder instance)
python3.10 camera_recorder.py --branch-id BB003 --video-label gripper_video --topic /gripper/camera/image_raw --ffmpeg

# Production: cap night-time bitrate spikes (recommended for 24h recording)
python3.10 camera_recorder.py --branch-id BB003 --ffmpeg --crf 28 --maxrate 2M

# Testing with short segments (overrides wall-clock alignment)
python3.10 camera_recorder.py --branch-id TEST --segment 10 --ffmpeg

# OpenCV backend (no ffmpeg)
python3.10 camera_recorder.py --branch-id BB003 --codec h264
```

### File Outputs

During recording:
```
videos/.recording_BB003_20260414T140000+0900_topview_video.mp4
videos/.recording_BB003_20260414T140000+0900_topview_video.srt
```

After segment completion (rename happens automatically):
```
videos/BB003_20260414T140000+0900_topview_video.mp4
videos/BB003_20260414T140000+0900_topview_video.srt
```

The `.recording_` prefix lets downstream tools (cron uploader, M4) identify completed vs. in-progress segments.

### Google Drive Upload (M3)

The uploader ships completed segment files to Google Drive. Routing is derived per-file from the M2 filename, so the local source directory can be a flat `videos/` that accumulates hourly segments across days.

**Target folder structure (M3):**
```
[Shared Drive]/robot-data-archive/       # prod (top-level) OR
[Shared Drive]/로봇지능화팀/robot-data-archive-dev/   # dev
  └── {PRODUCT}/                         # barisbrew / storagy / deux
        └── {BRANCH_ID}({BRANCH_NAME})/  # e.g. BB003(성수본점)
              └── {YYYY-MM}/             # e.g. 2026-04
                    └── {YYYYMMDD}/      # e.g. 20260414
                          └── BB003_20260414T140000+0900_topview_video.mp4
```

SRT is embedded into the MP4 (`mov_text`) during upload — no separate `.srt` files are uploaded.

**Prerequisites**
- A Google service account JSON key *or* OAuth client for personal Drive testing
- `UPLOAD_ROOT_ID` — ID of the `robot-data-archive` (prod) or `robot-data-archive-dev` (dev) folder
- `UPLOAD_SHARED_DRIVE_ID` — optional but recommended for service accounts
- `PRODUCT` + `BRANCH_ID` + `BRANCH_NAME` (all required for session uploads)

Install uploader dependencies:
```bash
pip install -r requirements.txt
```

**Dry-run (offline, no creds needed):**
```bash
python3.10 uploader.py --dry-run \
  --product barisbrew --branch-id BB003 --branch-name "성수본점" \
  --root-folder FAKE --session videos/ --min-age-seconds 0
```

**OAuth test mode (local user login):**
```bash
python3.10 uploader.py --auth-mode oauth \
  --oauth-client keys/client_secrets.json --token-path keys/gdrive_token.json \
  --product barisbrew --branch-id BB003 --branch-name "성수본점" \
  --session videos/
```

Generate an OAuth token first with `scripts/generate_oauth_token.py` (see `docs/spec/upload_spec.md`).

**Service account (production):**
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service_account.json
export UPLOAD_ROOT_ID=<robot-data-archive_folder_id>
export UPLOAD_SHARED_DRIVE_ID=<shared_drive_id>
export PRODUCT=barisbrew
export BRANCH_ID=BB003
export BRANCH_NAME=성수본점

python3.10 uploader.py --auth-mode service --session videos/ --delete-local --verify-md5
```

**Hourly cron (M4):**
```bash
# One-shot: embed SRT into MP4 then upload
set -a; source /etc/ros2-recorder/uploader.env; set +a
scripts/deliver.sh --min-age-seconds 30
```
`scripts/deliver.sh` chains `scripts/embed_srt.py` (SRT → mov_text remux, atomic replace) and `scripts/deliver.py` (upload + MD5 verify + local delete). Designed for crontab `1 * * * *`.

**Single-file manual upload:**
```bash
python3.10 uploader.py --file videos/BB003_20260414T140000+0900_topview_video.mp4 \
  --folder <drive_folder_id>
```

**Notes**
- Files not matching the M2 naming convention are skipped with a warning (legacy filenames are not auto-routed).
- `.recording_` prefixed files (in-progress segments) are always skipped.
- `--delete-local` only removes files after MD5 verification succeeds.

### Command Line Arguments

- `--branch-id` **(required)**: Branch identifier (e.g., `BB003`)
- `--video-label`: Video label for filename (default: `topview_video`)
- `--topic, -t`: Camera topic name (default: `/camera/color/image_raw`)
- `--output-dir, -o`: Output directory (default: `videos/`)
- `--fps, -f`: Output video FPS (default: 30)
- `--ffmpeg`: Use FFmpeg (libx264) instead of OpenCV for encoding (recommended)
- `--codec, -c`: Video codec - mp4v, xvid, h264 (OpenCV only, default: mp4v)
- `--crf`: CRF value for libx264 quality (default: 23; recommend 28-30 for ops to reduce night-time file sizes)
- `--maxrate`: Max bitrate cap (e.g., `2M`). Suppresses night-time sensor-noise bitrate spikes
- `--segment, -s`: Fixed segment duration in seconds (overrides wall-clock alignment; use for testing)

## Backends

### OpenCV Backend (Default)
- Faster startup time
- Good for real-time recording
- Limited codec options
- May have compatibility issues with some players

### FFmpeg Backend
- Better compression and quality
- More codec options
- Wider compatibility
- Slightly higher CPU usage
- Requires FFmpeg installation

## Segmented Recording

The recorder splits recordings into multiple video files. Default behavior is **wall-clock aligned**: segments switch at every `:00` (hourly boundary). Each segment is a self-contained MP4 + SRT pair.

Use `--segment N` to override with fixed-duration segments (useful for testing).

### Segment File Naming

```
{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.mp4
{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.srt
```

Example (24-hour recording starting at 14:23):
```
BB003_20260414T142305+0900_topview_video.mp4   ← first segment (short, ~37 min)
BB003_20260414T150000+0900_topview_video.mp4   ← :00 aligned
BB003_20260414T160000+0900_topview_video.mp4
...
```

### Segment Switching

- Seamless transition — each segment is properly closed before starting the next
- During recording: `.recording_*.mp4` + `.recording_*.srt` (in-progress marker)
- On segment completion: rename removes `.recording_` prefix
- Recording can be stopped at any time with Ctrl+C

## Example Output

```
Camera recorder initialized
Topic: /camera/color/image_raw
Output: videos/BB003_20260414T142305+0900_topview_video.mp4
FPS: 30
Using FFmpeg: True
Starting camera recorder...
Branch ID: BB003
Video label: topview_video
Recording started - Resolution: 640x480
Segmentation: wall-clock aligned (split at every :00)
Next segment switch in 2215s
Recorded 30 frames
Recorded 60 frames
...
Switching to segment 2...
Segment completed: videos/BB003_20260414T142305+0900_topview_video.mp4 (2215.0s)
Started recording: videos/BB003_20260414T150000+0900_topview_video.mp4
^C
Recording completed - 2 segment(s) saved to videos/
```

## Troubleshooting

1. **`ModuleNotFoundError: No module named 'rclpy._rclpy_pybind11'`**: Python version mismatch.
   - Cause: `python3` points to 3.11/3.12 (e.g., uv-managed) but ROS2 Humble needs 3.10.
   - Fix: Call `python3.10 camera_recorder.py ...` explicitly. See `docs/study/ros2_humble_env_setup.md`.

2. **`AttributeError: _ARRAY_API not found` / segfault in `imgmsg_to_cv2`**: NumPy version mismatch.
   - Cause: NumPy 2.x installed; ROS2 Humble `cv_bridge` requires NumPy 1.x.
   - Fix: `/usr/bin/python3.10 -m pip install --user 'numpy<2'`

3. **No frames received**: Verify the camera topic is publishing
   ```bash
   ros2 topic list
   ros2 topic echo /camera/color/image_raw --once
   ```

4. **Video writer failed**: Try FFmpeg backend (`--ffmpeg`) instead of default OpenCV.

5. **FFmpeg not found**: Install with `sudo apt install ffmpeg`.

## Notes

- The recorder automatically detects image dimensions from the first frame
- Recording stops gracefully with Ctrl+C — final segment is renamed and SRT closed
- Frame rate in output video is corrected via frame duplication when input FPS < output FPS
- See `docs/history/` for implementation history, `docs/management/upload_milestones.md` for roadmap
- **`docs/study/operational_gotchas.md` — 배포/디버깅 시 반드시 먼저 훑어보세요** (권한 모델, FFmpeg 특성, 저조도 용량 폭증, file state machine 불변식 등)
