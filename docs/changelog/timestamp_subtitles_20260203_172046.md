# Timestamp Sidecar & Session Recorder Enhancements

Last updated: 2026-02-03

## Summary
- Added per-frame metadata tracking with KST wall-clock capture and CSV export.
- Added per-session directories under `videos/session_<timestamp>` so each run stores MP4/SRT/CSV artifacts together.
- Generated SRT subtitles now group entries per second, display continuous timestamps, and show the KST timezone suffix without ROS-specific noise.
- Base filenames are timezone-aware and output directories are created automatically when custom paths are provided.

## Testing
- `python3 -m py_compile camera_recorder.py`
- Manual: run `test_recorder.py` + `camera_recorder.py --segment 10`, verify MP4/SRT/CSV files land under `videos/session_*/` and SRT displays continuous `YYYY-MM-DDTHH:MM:SS+0900 KST` captions in the player.
