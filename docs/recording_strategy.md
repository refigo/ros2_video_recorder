# Camera Recording Strategy and Requirements

Last updated: 2026-02-03

## Objectives
- Provide operations teams with reliable video evidence for incident triage and reporting.
- Preserve synchronized sensory/context data (video, joint states, events) so future lerobot/VLA training pipelines can ingest the recordings without manual rework.

## Operational Requirements
- **Video Segmentation & Upload**: keep local files in manageable segments (e.g., 10 min or 1 h). After each hour of recording completes, automatically upload all segments for that window to a managed Google Drive (or similar) location. Only delete the local copies once the upload (checksum or remote listing) confirms success.
- **Continuous Rolling Archive**: operate the recorder like a 24-hour security DVR—segments roll continuously using ISO-like filenames (e.g., `${ROBOT_ID}_20260203T130000+0900_video.mp4`) so chronological sorting matches real time (timezone fixed to KST, UTC+9). `${ROBOT_ID}` comes from each robot's environment variables or provisioning metadata.
- **Discoverability**: standardize the directory schema so anyone can locate a clip by answering three questions (Which robot? Which day? Which run?).
  - Root: `gs://<fleet-bucket>/recordings/`
  - Robot: `robot_<id>/` (e.g., `robot_A07/`)
  - Date: `<YYYY>/<MM>/<DD>/` to keep listings short (`2026/02/03/`)
  - Session: `<shift>_<operator>_<start_time>/` (e.g., `night_op2_130000/`)
  - Files: `${ROBOT_ID}_2026/02/03T130000+0900_video.mp4`, `..._timestamps.csv`, `..._events.srt`, `..._metadata.json`.
  - Provide a weekly-generated index (CSV or HTML) summarizing available sessions per robot so operations can jump via hyperlink rather than browsing raw folders.
- **Event-focused Windows**: in addition to the continuous CCTV archive, add tooling that, when an incident/event trigger occurs, automatically extracts and labels a window (e.g., ±5 minutes) around the trigger. These derived clips inherit the ISO naming base plus an event tag (`robotA07_20260203T130000Z_event-brakefail_video.mp4`) and link back to the continuous source for traceability.
- **Time Reference**: avoid permanent on-frame text overlays; instead, generate per-segment metadata (`timestamps.csv` or JSON) mapping `frame_index`, `ros_stamp`, and `wall_clock_iso`. Optionally export an FFmpeg timecode track or sidecar subtitle for easy viewing.
- **Event Logging**: alongside each video segment, persist an operator-friendly log (CSV/JSON) noting key events/alerts, so the operations team can correlate alarms with exact video timestamps.

## Data for lerobot/VLA
- **Synchronized Modalities**: record robot joint positions/velocities, gripper states, commands, and any environment signals in lockstep with the video. The simplest path is to always capture a ROS 2 bag covering `/camera/color/image_raw`, `/joint_states`, and relevant topics for the full session.
- **Export Format**: for each session, create a manifest that points to (a) video segments, (b) synchronized state logs, (c) metadata. This manifest will later be transformed into the lerobot dataset structure (e.g., `video.mp4`, `robot_state.parquet`, `metadata.json`).
- **Quality Checks**: ensure recorded frequency, dropped frames, and missing joint samples are tracked so downstream training code can filter corrupted windows.

## Tooling Roadmap
1. Extend `camera_recorder.py` (or wrapper service) to emit metadata/timestamp files and initiate uploads when a segment batch closes.
2. Provide a small monitoring CLI/GUI for operators showing latest upload status and giving quick links to the remote Google Drive folders.
3. Automate ROS bag capture in parallel with the MP4 recorder, or integrate a lerobot-ready exporter once available.
4. Document recovery workflow so operations know how to retrieve footage, interpret metadata, and supply archives to engineering.

## Housekeeping Policy
- Retain a rolling cache of the most recent segments on the robot (e.g., last 6–12 hours) in case connectivity is lost.
- Periodically verify remote storage quotas and integrity (weekly checksum audit) to guarantee historical data remains accessible for root-cause analysis and future ML training.
