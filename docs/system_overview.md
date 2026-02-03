# ROS2 Video Recorder System Overview

Last updated: 2026-02-03

## Purpose
- Collect continuous camera footage from ROS2 image topics for operations triage and incident playback.
- Capture synchronized metadata (timestamps, joint data references) to enable lerobot/VLA datasets.

## Key Components
- `camera_recorder.py`: ROS2 node subscribing to `/camera/color/image_raw`, capable of OpenCV or FFmpeg encoding, segmentation, and timestamp sidecars (CSV/SRT).
- `test_recorder.py`: mock publisher producing synthetic frames for local verification.
- Shell helpers (`record_camera.sh`, `test_segmentation.sh`, `setup_env.sh`) for ops-friendly execution and environment validation.
- Documentation set (`docs/recording_strategy.md`, `docs/recording_spec.md`, changelog entries) describing policies and implementation details.

## Recording Workflow
1. Recorder starts, generating a session folder (`videos/session_<YYYYMMDDHHMMSS>/`).
2. First frame establishes resolution/fps; writer spins up in OpenCV or FFmpeg mode.
3. Each frame writes to the video file while recording metadata (frame index, KST wall-clock, ROS stamp).
4. Segment timer (if enabled) rotates files every `segment_duration` seconds, emitting matching CSV/SRT sidecars.
5. On shutdown, the last segment is flushed and metadata saved.

## Time & Metadata Handling
- All internal timestamps use KST (`UTC+9`).
- SRT subtitles show `YYYY-MM-DDTHH:MM:SS+0900 KST` per elapsed second for operators.
- CSV files log `frame_idx, ros stamp sec/nsec, wall_time_iso` for ML/analysis.
- Future-proofing: session folders and metadata files align with lerobot export plans described in the spec.

## Operational Considerations
- Segment presets: 10s (debug), 10min, 1h.
- Upload policy (see `docs/recording_strategy.md`): after each hour, ship artifacts to cloud storage, verify, then delete local copies beyond retention window.
- Event-triggered extracts (future work) will slice around incidents while referencing continuous session files.

## Testing
- Local syntax check: `python3 -m py_compile camera_recorder.py`.
- Functional: run `python3 test_recorder.py` (publisher) + `python3 camera_recorder.py --segment 10`, then inspect `videos/session_<timestamp>/` for video + sidecar files.
- ROS bag capture and lerobot exporters remain on the roadmap; integration tests should cover both when implemented.
