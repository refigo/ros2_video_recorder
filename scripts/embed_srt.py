#!/usr/bin/env python3
"""Embed SRT subtitles into matching MP4 files via ffmpeg remux.

File-based state machine (M4):
  Before: <name>.mp4 + <name>.srt
  After:  <name>.mp4 (with mov_text subtitle track; .srt deleted)

Safe to run repeatedly. Idempotent recovery:
  - Stale <name>.mp4.embedding.tmp from prior crash → removed before scan
  - MP4 already has subtitle track + orphan SRT still present → SRT deleted, no re-embed

Can run standalone: `python3.10 scripts/embed_srt.py --dir videos/`
Or as a library: `from embed_srt import run; run(session_dir, min_age_seconds=30)`
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import uploader  # for find_srt_for_mp4

TMP_SUFFIX = ".embedding.tmp"


@dataclass
class EmbedResult:
    embedded: int = 0
    recovered: int = 0  # srt deleted without remux (already-embedded recovery)
    skipped: int = 0    # no srt, or too recent
    failed: int = 0

    def as_dict(self) -> dict:
        return {"embedded": self.embedded, "recovered": self.recovered,
                "skipped": self.skipped, "failed": self.failed}


def has_subtitle_track(mp4_path: str) -> bool:
    """Return True iff the mp4 already contains at least one subtitle stream."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s",
         "-show_entries", "stream=index", "-of", "csv=p=0", mp4_path],
        capture_output=True, text=True,
    )
    return bool(probe.stdout.strip())


def cleanup_stale_tmp(session_dir: str) -> int:
    """Remove any leftover *.embedding.tmp files (prior-crash artifacts).
    Returns count of files removed.
    """
    removed = 0
    for entry in os.scandir(session_dir):
        if entry.is_file() and entry.name.endswith(TMP_SUFFIX):
            try:
                os.remove(entry.path)
                logging.info("Removed stale tmp: %s", entry.name)
                removed += 1
            except OSError as e:
                logging.warning("Could not remove stale tmp %s: %s", entry.name, e)
    return removed


def embed_one(mp4_path: str, srt_path: str) -> bool:
    """Embed srt into mp4 atomically. Returns True on success.

    On success: mp4 is replaced in-place with subtitle-embedded version; srt is deleted.
    On failure: tmp file removed if present; original mp4 + srt are untouched.
    """
    tmp_path = mp4_path + TMP_SUFFIX
    cmd = [
        "ffmpeg", "-y", "-i", mp4_path, "-i", srt_path,
        "-c:v", "copy", "-c:s", "mov_text",
        "-metadata:s:s:0", "language=kor",
        "-movflags", "+faststart",
        "-f", "mp4",  # required because tmp file extension is .embedding.tmp (not .mp4)
        tmp_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.error("ffmpeg embed failed for %s: %s",
                      os.path.basename(mp4_path),
                      (result.stderr or "")[-500:])
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False

    try:
        os.replace(tmp_path, mp4_path)  # atomic on same fs
    except OSError as e:
        logging.error("Atomic replace failed for %s: %s", mp4_path, e)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False

    try:
        os.remove(srt_path)
    except OSError as e:
        # MP4 now has subtitle embedded; orphan srt will be cleaned on next run's
        # has_subtitle_track recovery path.
        logging.warning("Embedded OK but could not delete srt %s: %s", srt_path, e)

    logging.info("Embedded: %s", os.path.basename(mp4_path))
    return True


def _iter_embed_candidates(session_dir: str, min_age_seconds: int) -> List[str]:
    """Return absolute paths of .mp4 files eligible for embed scan.

    Excludes:
      - .recording_* (recorder still owns)
      - *.embedding.tmp (handled by cleanup_stale_tmp)
      - Files younger than min_age_seconds
    """
    now = time.time()
    out: List[str] = []
    for entry in os.scandir(session_dir):
        if not entry.is_file():
            continue
        name = entry.name
        if name.startswith(".recording_"):
            continue
        if name.endswith(TMP_SUFFIX):
            continue
        if not name.endswith(".mp4"):
            continue
        age = now - entry.stat().st_mtime
        if min_age_seconds and age < min_age_seconds:
            logging.info("Skip embed (too recent): %s", name)
            continue
        out.append(entry.path)
    return sorted(out)


def run(session_dir: str, min_age_seconds: int = 30) -> EmbedResult:
    """Scan session_dir and embed all pending mp4+srt pairs."""
    result = EmbedResult()
    cleanup_stale_tmp(session_dir)

    for mp4_path in _iter_embed_candidates(session_dir, min_age_seconds):
        srt_path = uploader.find_srt_for_mp4(mp4_path)
        if srt_path is None:
            result.skipped += 1
            continue

        # Recovery path: if mp4 already has subtitle (partial-crash between replace
        # and srt-delete), skip remux and just delete orphan srt.
        try:
            if has_subtitle_track(mp4_path):
                try:
                    os.remove(srt_path)
                    logging.info("Recovered (already embedded, removed orphan srt): %s",
                                 os.path.basename(mp4_path))
                    result.recovered += 1
                except OSError as e:
                    logging.warning("Could not delete orphan srt %s: %s", srt_path, e)
                    result.failed += 1
                continue
        except Exception as e:
            logging.warning("ffprobe failed on %s: %s — will attempt embed anyway",
                            os.path.basename(mp4_path), e)

        if embed_one(mp4_path, srt_path):
            result.embedded += 1
        else:
            result.failed += 1

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed SRT subtitles into matching MP4 files.")
    parser.add_argument("--dir", required=True, help="Session directory to scan")
    parser.add_argument("--min-age-seconds", type=int, default=30,
                        help="Skip files younger than this many seconds (default: 30)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not os.path.isdir(args.dir):
        print(f"Not a directory: {args.dir}", file=sys.stderr)
        return 2

    result = run(args.dir, min_age_seconds=args.min_age_seconds)
    logging.info("Embed summary: %s", result.as_dict())
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
