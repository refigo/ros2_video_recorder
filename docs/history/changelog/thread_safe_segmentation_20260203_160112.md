# Segmented Recording Stabilization

## Overview
- Added a global writer lock protecting OpenCV and FFmpeg backends so that frame writes, releases, and reinitialization never overlap across threads.
- Introduced `_release_current_writer_locked()` and ensured `switch_segment()`/`stop_recording()` guard all writer state transitions with the lock.
- Converted the FFmpeg helper thread into a long-lived worker that is started once per process, preventing multiple simultaneous encoders.

## Reproduction
1. Start the mock publisher with `python3 test_recorder.py`.
2. Run `python3 camera_recorder.py --segment 10` (OpenCV backend).
3. After the second segment begins, OpenCV closes the first file while the callback still writes, producing `Invalid pts` and a segmentation fault.

## Resolution
- All writer interactions now happen inside the lock, eliminating data races between the segment timer thread and the ROS callback.
- Segment rotation now logs completion and startup after the new writer is active, making debugging easier.
- FFmpeg mode reuses one writer thread; `_release_current_writer_locked()` flushes the queue before closing to keep files consistent.

## Validation
- `python3 -m py_compile camera_recorder.py` (syntax check).
- Manual segmented run (`test_segmentation.sh` or the steps above) now rotates segments cleanly without ffmpeg/OpenCV crashes.
