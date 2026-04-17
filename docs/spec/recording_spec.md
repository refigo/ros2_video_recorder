# Recording Implementation Spec

Last updated: 2026-04-14

## Scope
- Provide a 24/7 continuous rolling recorder producing MP4 segments plus synchronized metadata for operations monitoring.
- Guarantee downstream readiness for lerobot/VLA by storing timestamps, joint data links, and manifest files alongside each video.

## Core Behavior
1. **Continuous Segments (Wall-clock aligned)** — *M2 implemented*
   - Default cadence: **1-hour segments aligned to wall-clock `:00`**. Use `--segment N` to override with fixed duration (testing only).
   - First segment after startup may be shorter than 1 hour (start at 14:23 → first split at 15:00 = 37 min).
   - Naming: `${BRANCH_ID}_<YYYYMMDD>T<HHMMSS>+0900_<video_label>.{mp4,srt}` (KST, UTC+9).
     - `${BRANCH_ID}`: 지점 식별자, `--branch-id` CLI 필수 인자 (e.g., `BB003`)
     - `<video_label>`: 카메라 역할, `--video-label` (default: `topview_video`; e.g., `gripper_video`)
   - Recorder ensures chronological ordering by simply sorting filenames.
2. **File-based State Machine** — *M2 implemented*
   - During recording: `.recording_{basename}.mp4` + `.recording_{basename}.srt`
   - On segment completion: atomic rename drops the `.recording_` prefix → final `{basename}.mp4` + `{basename}.srt`
   - This lets downstream pipeline stages (M4 cron) detect completion by file presence without IPC/DB.
3. **Metadata Artifacts** — *M2 simplified*
   - `{basename}.srt`: human-readable wall-clock timestamps (one entry per second), **written in real-time** (per-frame append + flush) for crash safety.
   - `{basename}.mp4`: H.264 video (ffmpeg backend, libx264 + yuv420p).
   - *Removed in M2:* CSV timestamps file (subsumed by SRT).
   - *Future (M3+):* `_metadata.json` for upload ledger, `_joints.parquet` for lerobot training — not yet implemented.
4. **Upload Pipeline** — *M3 완료 (uploader + Drive routing), M4 완료 (embed + cron orchestrator)*
   - `scripts/deliver.sh` (M5에서 crontab 등록): `.mp4`+`.srt` 쌍 감지 → `scripts/embed_srt.py`로 subtitle embed → `scripts/deliver.py`가 업로드 + MD5 검증 + 로컬 삭제
   - `min-age-seconds=30` + cron at `:01` = 60s buffer after segment switch. No file-collision risk with recorder.
   - Upload target folder: `{UPLOAD_ROOT_ID}/{PRODUCT}/{BRANCH_ID}({BRANCH_NAME})/{YYYY-MM}/{YYYYMMDD}/` (Shared Drive).
5. **QoS Compatibility**
   - Subscriber uses `BEST_EFFORT` reliability to match typical camera publishers (e.g., wireless gripper cameras).
   - `BEST_EFFORT` subscriber is also compatible with `RELIABLE` publishers, so no regression for wired cameras.
6. **Irregular Frame Rate Correction**
   - When incoming frame rate is lower than the configured output FPS (e.g., ~15fps input vs 30fps output), the recorder duplicates the previous frame to fill the gap.
   - For each received frame, elapsed time since the last frame is measured and `expected_frames = max(1, round(elapsed * fps))` determines how many output frames to write.
   - This ensures playback duration matches real-world wall-clock time regardless of input frame rate fluctuations.
   - Segment boundaries reset the frame timing state to prevent drift accumulation.
7. **Event-triggered Windows** — *future scope, not implemented*
   - Trigger sources: robot diagnostics, operator button, analytics.
   - When triggered, generate derived clips spanning configurable pre/post buffers (default ±5 min) from the continuous archive.

## Future lerobot Export
- Nightly job scans Drive folders, reads `metadata.json`, and constructs session manifests pointing to video + joints.
- Conversion tooling maps manifests to lerobot dataset format (video file, robot_state parquet, meta) ready for fine-tuning pipelines.

## Operational Tooling
- Monitoring UI lists current ISO-coded segments, upload status, and provides Drive hyperlinks.
- Event viewer lets ops select an incident and instantly download the derived clip + logs.
- Health checks verify ROS bag capture, SRT completeness, and Drive quota.

## Open Questions
- Final decision on joints logging format (Parquet vs ROS bag reference).
- Exact retention duration for local cache (6h vs 12h) per robot class.
- Drive API quotas when pushing many hourly segments simultaneously.
