# Progress

## Current Status (2026-04-20)

### Completed
- **M2**: Wall-clock aligned segmented recording with SRT subtitle generation
- **M3**: Google Drive upload with product-based folder structure, dev/prod split
- **M4**: Cron integration — `scripts/embed_srt.py` + `scripts/deliver.py` + `scripts/deliver.sh`
  - File-based state machine: `.recording_` → `.mp4+.srt` → embedded `.mp4` → uploaded+deleted
  - Verified on dev Shared Drive (`robot-data-archive-dev/`)

### In Progress
- **M4.5**: CRF/maxrate CLI arguments for night-time bitrate control
  - Code complete (`--crf`, `--maxrate` in `camera_recorder.py`), committed
  - Night CRF comparison test pending (CRF 28 / CRF 30 / CRF 28+maxrate 2M)
  - `scripts/night_crf_test.sh` needs `ROS_DOMAIN_ID` fix before re-scheduling
- **M5**: systemd + cron deployment setup
  - Scripts created: `start_recorder.sh`, `install.sh`, `ros2-camera-recorder.service`
  - Config unified: `config/recorder.env.example` (recorder + uploader in one .env file)
  - Design: chose .env over YAML — systemd/shell native support, flat config, no extra dependencies
  - Pending: live verification (manual run → systemd start → cron upload)

### Next
- **M6**: 24h end-to-end verification
- **M7**: Service Account production deployment

## Key Files
| File | Purpose |
|------|---------|
| `camera_recorder.py` | ROS2 camera recording node (segmented, SRT, ffmpeg H.264) |
| `uploader.py` | Google Drive upload with MD5 verification |
| `scripts/embed_srt.py` | Standalone SRT → mov_text embedding (atomic replace) |
| `scripts/deliver.py` | Cron orchestrator: embed → upload → verify → delete |
| `scripts/deliver.sh` | Shell wrapper for deliver.py (loads env, invokes python3.10) |
| `scripts/start_recorder.sh` | Wrapper: sources ROS2 env, maps env vars to CLI args |
| `scripts/install.sh` | Installer: copies systemd unit, creates log dir, registers cron |
| `systemd/ros2-camera-recorder.service` | systemd unit for recording daemon |
| `config/recorder.env.example` | Unified env template (recorder + uploader config) |
| `scripts/night_crf_test.sh` | Night CRF comparison test runner |
