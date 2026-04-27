# Progress

## Current Status (2026-04-27)

### Completed
- **M2**: Wall-clock aligned segmented recording with SRT subtitle generation
- **M3**: Google Drive upload with product-based folder structure, dev/prod split
- **M4**: Cron integration — `scripts/embed_srt.py` + `scripts/deliver.py` + `scripts/deliver.sh`
  - File-based state machine: `.recording_` → `.mp4+.srt` → embedded `.mp4` → uploaded+deleted
  - Verified on dev Shared Drive (`robot-data-archive-dev/`)
- **M4.5 (partial)**: `--crf` / `--maxrate` CLI arguments added to `camera_recorder.py`
  - Code committed; doubled FFmpeg `-bufsize` relative to `--maxrate` for steadier VBR
- **M5**: User-level systemd + cron deployment setup
  - `deploy/install.sh`, `start.sh`, `stop.sh`, `restart.sh`, `uninstall.sh` (user systemd via `loginctl enable-linger`)
  - `scripts/start_recorder.sh` wrapper sources ROS2 env and maps env → CLI
  - Unified env: `config/recorder.env.example` (recorder + uploader in one file)
  - Single venv `.venv_xrdc` (system Python 3.10 + `numpy<2` + Google libs; rclpy via ROS2 PYTHONPATH)
  - **Live verified end-to-end on this workstation**: recorder → wall-clock segment split at `:00`
    → deliver cron at `:01` → embed SRT → upload to dev Drive → MD5 verify → delete local
  - Design notes: `.env` chosen over YAML (systemd/shell native, flat config, no parser dependency)

### Known Issues / Operational
- **RealSense USB autosuspend** (incident 2026-04-21): D435 stopped producing frames after ~9.75h; recorder kept
  running and produced empty SRT/MP4 segments overnight. Root cause + udev-rule fix documented in
  `docs/study/realsense_usb_stability.md`. Fix not yet applied to this workstation.
- **M4.5 night CRF comparison test** still pending camera recovery before re-scheduling
  (`scripts/night_crf_test.sh` is fixed and ready).

### In Progress
- **BL-08**: Migration to company repo `xyz-robot-data-collector`
  (https://github.com/xyzcorpsoftware/xyz-robot-data-collector.git)
  - Approach 1b: fresh squashed "initial import" commit (no history transfer)
  - User-service paths to migrate to XDG layout (`~/.config/xrdc/`, `~/.local/share/xrdc/`, etc.)
  - Encrypted secrets bundle (Approach A) for SA-key distribution to robots
  - Full E2E verification required in new repo before this repo is sealed off

### Next (in new repo)
- **M6**: 24h end-to-end verification (post-migration, post-USB-fix)
- **M7**: Service Account production deployment (Shared Drive prod folder)
- **BL-13** (planned): Encrypted-secrets install flow + interactive env prompt

## Repo Status
- **This repo** (`ros2_video_recorder`, personal): being archived in place; not yet flagged as archived on
  GitHub — that happens only after the new repo's E2E verification passes.
- **New repo** (`xyz-robot-data-collector`, xyzcorpsoftware org): empty, awaiting migration.

## Key Files (current repo, frozen state)
| File | Purpose |
|------|---------|
| `camera_recorder.py` | ROS2 camera recording node (segmented, SRT, ffmpeg H.264) |
| `uploader.py` | Google Drive upload with MD5 verification |
| `scripts/embed_srt.py` | Standalone SRT → mov_text embedding (atomic replace) |
| `scripts/deliver.py` | Cron orchestrator: embed → upload → verify → delete |
| `scripts/deliver.sh` | Shell wrapper for deliver.py (loads env, invokes venv python) |
| `scripts/start_recorder.sh` | Wrapper: sources ROS2 env, maps env vars to CLI args |
| `deploy/install.sh` | User-systemd installer + cron registration |
| `deploy/{start,stop,restart,uninstall}.sh` | User-systemd lifecycle scripts |
| `systemd/ros2-camera-recorder.service` | systemd user unit for recording daemon |
| `config/recorder.env.example` | Unified env template (recorder + uploader config) |
| `scripts/night_crf_test.sh` | Night CRF comparison test runner |
| `docs/study/realsense_usb_stability.md` | USB autosuspend incident analysis + udev fix |
