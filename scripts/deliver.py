#!/usr/bin/env python3
"""Deliver: embed SRT → upload to Drive → MD5 verify → delete local.

Processes completed recording files and delivers them to the central Drive archive.

Runs on a flat videos directory (e.g. cron `1 * * * *`):
  Phase 1 (embed):  .mp4+.srt pair → ffmpeg mov_text remux → .srt deleted
  Phase 2 (upload): embedded .mp4 → Drive upload → MD5 verify → local delete

Reads configuration from environment (expected to be loaded by scripts/deliver.sh
from /etc/ros2-recorder/recorder.env).

Required env:
  GOOGLE_APPLICATION_CREDENTIALS, UPLOAD_ROOT_ID, UPLOAD_SHARED_DRIVE_ID,
  PRODUCT, BRANCH_ID, BRANCH_NAME
Optional env:
  VIDEOS_DIR (default: "videos")

Designed for cron; logs to stdout. Returns 0 on full success, 1 if any embed or
upload failed (so cron mail / systemd will flag the failure).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)     # so `import uploader` works
sys.path.insert(0, _SCRIPT_DIR)   # so `import embed_srt` works

import embed_srt   # noqa: E402
import uploader    # noqa: E402


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _build_upload_config(args: argparse.Namespace) -> uploader.UploadConfig:
    def env_required(key: str) -> str:
        val = os.environ.get(key, "")
        if not val:
            raise SystemExit(f"Missing required env: {key}")
        return val

    sa_path = args.service_account or env_required("GOOGLE_APPLICATION_CREDENTIALS")
    if not os.path.isfile(sa_path):
        raise SystemExit(f"SA key not found: {sa_path}")

    return uploader.UploadConfig(
        auth_mode="service",
        service_account_path=sa_path,
        oauth_client_path=None,
        oauth_token_path=None,
        oauth_console=False,
        root_folder_id=args.root_folder or env_required("UPLOAD_ROOT_ID"),
        shared_drive_id=args.shared_drive_id or env_required("UPLOAD_SHARED_DRIVE_ID"),
        product=args.product or env_required("PRODUCT"),
        branch_id=args.branch_id or env_required("BRANCH_ID"),
        branch_name=args.branch_name or env_required("BRANCH_NAME"),
        # Upload phase uses min_age=0: embed phase already applied the safety
        # filter, and embed changes mtime to now — using the same min_age would
        # cause the just-embedded file to be skipped until the NEXT cron cycle.
        min_age_seconds=0,
        delete_local=not args.keep_local,
        verify_md5=True,
        dry_run=args.dry_run,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Hourly embed + upload cron orchestrator")
    parser.add_argument("--videos-dir", default=os.environ.get("VIDEOS_DIR", "videos"),
                        help="Session directory to scan (env: VIDEOS_DIR, default: videos)")
    parser.add_argument("--min-age-seconds", type=int, default=30,
                        help="Skip files younger than this many seconds (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip embed and run uploader in dry-run mode")
    parser.add_argument("--skip-embed", action="store_true",
                        help="Skip embed phase (e.g. for already-embedded content)")
    parser.add_argument("--keep-local", action="store_true",
                        help="Keep local files after verified upload (default: delete)")
    parser.add_argument("--log-level", default="INFO")
    # Overrides (env is primary source)
    parser.add_argument("--service-account")
    parser.add_argument("--root-folder")
    parser.add_argument("--shared-drive-id")
    parser.add_argument("--product")
    parser.add_argument("--branch-id")
    parser.add_argument("--branch-name")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    videos_dir = args.videos_dir
    if not os.path.isdir(videos_dir):
        logging.error("Videos dir does not exist: %s", videos_dir)
        return 2

    started = time.time()
    logging.info("=" * 64)
    logging.info("deliver start  pid=%d  time=%s  videos_dir=%s",
                 os.getpid(), datetime.now().isoformat(timespec="seconds"), videos_dir)

    # Phase 1: embed
    embed_failed = 0
    if args.dry_run or args.skip_embed:
        logging.info("Skipping embed phase (dry_run=%s, skip_embed=%s)",
                     args.dry_run, args.skip_embed)
    else:
        embed_started = time.time()
        result = embed_srt.run(videos_dir, min_age_seconds=args.min_age_seconds)
        embed_failed = result.failed
        logging.info("Embed phase done in %s: %s",
                     _fmt_duration(time.time() - embed_started), result.as_dict())

    # Phase 2: upload
    upload_error = False
    uploaded = 0
    try:
        config = _build_upload_config(args)
    except SystemExit as e:
        logging.error("Config build failed: %s", e)
        return 2

    try:
        if config.dry_run:
            service = None
        else:
            service = uploader.build_drive_service(config.service_account_path)
        upload_started = time.time()
        uploaded = uploader.upload_session(service, videos_dir, config)
        logging.info("Upload phase done in %s: uploaded=%d",
                     _fmt_duration(time.time() - upload_started), uploaded)
    except Exception as exc:
        upload_error = True
        logging.exception("Upload phase failed: %s", exc)

    total = _fmt_duration(time.time() - started)
    exit_code = 0 if (embed_failed == 0 and not upload_error) else 1
    logging.info("deliver end  exit=%d  total=%s  embed_failed=%d  uploaded=%d",
                 exit_code, total, embed_failed, uploaded)
    logging.info("=" * 64)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
