# Recording Implementation Spec

Last updated: 2026-03-03

## Scope
- Provide a 24/7 continuous rolling recorder producing MP4 segments plus synchronized metadata for operations monitoring.
- Guarantee downstream readiness for lerobot/VLA by storing timestamps, joint data links, and manifest files alongside each video.

## Core Behavior
1. **Continuous Segments**
   - Default cadence: 10 min or 1 h segments depending on deployment profile; add a 10 s preset for QA/diagnostics so engineers can spin up short trials without consuming disk.
- Naming: `${ROBOT_ID}_<YYYYMMDD>T<HHMMSS>+0900_<artifact>.ext` (KST, UTC+9) where `${ROBOT_ID}` is injected via environment/provisioning on each robot (e.g., `ROBOT_ID=robotA07`). Artifacts: `video`, `timestamps`, `events`, `metadata`, `joints`.
   - Recorder ensures chronological ordering by simply sorting filenames.
2. **Metadata Artifacts**
   - `..._timestamps.csv`: `frame_idx,ros_stamp_sec,ros_stamp_nsec,wall_clock_iso`.
   - `..._events.srt`: optional human-readable annotations for Drive playback.
   - `..._metadata.json`: duration, hashes, bag references, upload ledger.
   - `..._joints.parquet` (or ROS bag link) for lerobot training.
3. **Upload Pipeline**
   - After each hour completes, enqueue the past hour of segments for Google Drive upload.
   - Upload daemon retries with exponential backoff and records status in `upload_status.db`.
   - Local cache retains latest 6–12 hours; files are removed only when checksum + Drive listing confirm success.
4. **QoS Compatibility**
   - Subscriber uses `BEST_EFFORT` reliability to match typical camera publishers (e.g., wireless gripper cameras).
   - `BEST_EFFORT` subscriber is also compatible with `RELIABLE` publishers, so no regression for wired cameras.
5. **Irregular Frame Rate Correction**
   - When incoming frame rate is lower than the configured output FPS (e.g., ~15fps input vs 30fps output), the recorder duplicates the previous frame to fill the gap.
   - For each received frame, elapsed time since the last frame is measured and `expected_frames = max(1, round(elapsed * fps))` determines how many output frames to write.
   - This ensures playback duration matches real-world wall-clock time regardless of input frame rate fluctuations.
   - Segment boundaries reset the frame timing state to prevent drift accumulation.
6. **Event-triggered Windows**
   - Trigger sources: robot diagnostics, operator button, analytics.
   - When triggered, generate derived clips spanning configurable pre/post buffers (default ±5 min) from the continuous archive.
   - Derived clip naming: `<base_iso>_event-<slug>_<artifact>.ext` so both CCTV archive and event bundle share the same manifest lineage.

## Future lerobot Export
- Nightly job scans Drive folders, reads `metadata.json`, and constructs session manifests pointing to video + joints.
- Conversion tooling maps manifests to lerobot dataset format (video file, robot_state parquet, meta) ready for fine-tuning pipelines.

## Operational Tooling
- Monitoring UI lists current ISO-coded segments, upload status, and provides Drive hyperlinks.
- Event viewer lets ops select an incident and instantly download the derived clip + logs.
- Health checks verify ROS bag capture, timestamp CSV completeness, and Drive quota.

## Open Questions
- Final decision on joints logging format (Parquet vs ROS bag reference).
- Exact retention duration for local cache (6h vs 12h) per robot class.
- Drive API quotas when pushing many hourly segments simultaneously.
