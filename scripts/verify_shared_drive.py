#!/usr/bin/env python3
"""Live Shared Drive smoke test — validates SA auth, folder creation with Korean+paren
names, upload, MD5 verify, idempotent re-upload, and cleanup.

Reuses functions from uploader.py so this exercises the real production code path.

Required env:
  GOOGLE_APPLICATION_CREDENTIALS — path to SA JSON key
  UPLOAD_ROOT_ID                  — Drive folder ID inside the Shared Drive to write under
  UPLOAD_SHARED_DRIVE_ID          — Shared Drive ID

Run:
  .venv/bin/python scripts/verify_shared_drive.py
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import tempfile
from datetime import datetime

# Make uploader importable when run from repo root or scripts/
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import uploader  # noqa: E402

SMOKE_TEST_ROOT_SEGMENT = "_smoketest(테스트지점)"  # parens + Korean — the live thing we're testing


class StepError(Exception):
    """Raised when a verification step fails."""


def _print_step(step: int, total: int, title: str, status: str, detail: str = "") -> None:
    pad = max(0, 40 - len(title))
    suffix = f" — {detail}" if detail else ""
    print(f"[{step}/{total}] {title}{' ' * pad}... {status}{suffix}")


def _hint(step: int, msg: str) -> None:
    print(f"    hint: {msg}", file=sys.stderr)


def _require_env() -> dict:
    keys = ["GOOGLE_APPLICATION_CREDENTIALS", "UPLOAD_ROOT_ID", "UPLOAD_SHARED_DRIVE_ID"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        print("Missing required environment variables:", ", ".join(missing), file=sys.stderr)
        print("\nSet them like this:\n", file=sys.stderr)
        print(
            "  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/company-sa.json\n"
            "  export UPLOAD_ROOT_ID=<folder_id_inside_shared_drive>\n"
            "  export UPLOAD_SHARED_DRIVE_ID=<shared_drive_id>\n",
            file=sys.stderr,
        )
        sys.exit(2)
    sa_path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    if not os.path.isfile(sa_path):
        print(f"SA key not found at: {sa_path}", file=sys.stderr)
        sys.exit(2)
    return {
        "sa_path": sa_path,
        "root_id": os.environ["UPLOAD_ROOT_ID"],
        "shared_drive_id": os.environ["UPLOAD_SHARED_DRIVE_ID"],
    }


def step_1_auth(env: dict):
    try:
        service = uploader.build_drive_service(env["sa_path"])
        _print_step(1, 6, "Auth + Drive service build", "PASS")
        return service
    except Exception as exc:
        _print_step(1, 6, "Auth + Drive service build", "FAIL", str(exc))
        _hint(1, "SA JSON 경로/형식 확인. `jq . <path>` 로 파일 읽기 시도.")
        raise StepError from exc


def step_2_shared_drive_meta(service, env: dict) -> str:
    try:
        meta = service.drives().get(
            driveId=env["shared_drive_id"],
            fields="id,name",
        ).execute()
        name = meta.get("name", "?")
        _print_step(2, 6, "Shared Drive metadata", "PASS", f"name='{name}'")
        return name
    except Exception as exc:
        _print_step(2, 6, "Shared Drive metadata", "FAIL", str(exc))
        _hint(2, "SA가 Shared Drive 멤버(Content manager 이상)인지 확인. Drive 설정 → 멤버 관리.")
        raise StepError from exc


def step_3_create_folder_tree(service, env: dict) -> tuple[str, list[str]]:
    now = datetime.now(tz=uploader.KST)
    parts = [
        "barisbrew-recorded-datas",
        SMOKE_TEST_ROOT_SEGMENT,
        now.strftime("%Y-%m"),
        now.strftime("%Y%m%d"),
    ]
    try:
        folder_id = uploader.ensure_drive_path(
            service, env["root_id"], parts, shared_drive_id=env["shared_drive_id"]
        )
        _print_step(3, 6, "Create test folder tree", "PASS", f"id={folder_id}")
        return folder_id, parts
    except Exception as exc:
        _print_step(3, 6, "Create test folder tree", "FAIL", str(exc))
        _hint(3, "한글/괄호 실패 의심. build_drive_path_parts 폴백 논의 필요.")
        raise StepError from exc


def _make_dummy_file() -> str:
    fd, path = tempfile.mkstemp(prefix="smoketest_", suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write("shared-drive-smoketest\n" * 40)  # ~880 bytes
    return path


def step_4_upload(service, env: dict, parent_id: str, local_path: str) -> str:
    try:
        file_id, verified = uploader.upload_file_to_folder(
            service, local_path, parent_id,
            verify_md5=True, dry_run=False,
            shared_drive_id=env["shared_drive_id"],
        )
        if not file_id:
            raise RuntimeError("no file id returned")
        if not verified:
            raise RuntimeError("MD5 verification failed")
        # Confirm MD5 matches locally
        local_md5 = hashlib.md5(open(local_path, "rb").read()).hexdigest()
        remote = service.files().get(
            fileId=file_id, fields="md5Checksum,size", supportsAllDrives=True,
        ).execute()
        if remote.get("md5Checksum") != local_md5:
            raise RuntimeError(f"remote md5 mismatch: {remote.get('md5Checksum')} vs {local_md5}")
        _print_step(4, 6, "Upload 1KB dummy file", "PASS", f"id={file_id} md5={local_md5[:8]}…")
        return file_id
    except Exception as exc:
        _print_step(4, 6, "Upload 1KB dummy file", "FAIL", str(exc))
        _hint(4, "SA 권한이 Content manager 이상인지 확인. Viewer만으론 업로드 불가.")
        raise StepError from exc


def step_5_reupload_skip(service, env: dict, parent_id: str, local_path: str, expected_id: str) -> None:
    try:
        file_id, verified = uploader.upload_file_to_folder(
            service, local_path, parent_id,
            verify_md5=True, dry_run=False,
            shared_drive_id=env["shared_drive_id"],
        )
        if file_id != expected_id:
            raise RuntimeError(f"expected skip (same id) but got different id {file_id} vs {expected_id}")
        if not verified:
            raise RuntimeError("MD5 verification failed on skip path")
        _print_step(5, 6, "Re-upload should skip", "PASS", "same id returned (idempotent)")
    except Exception as exc:
        _print_step(5, 6, "Re-upload should skip", "FAIL", str(exc))
        _hint(5, "dedup 로직 동작 실패. uploader.find_existing_file 반환값 확인.")
        raise StepError from exc


def _delete_tree(service, env: dict, root_parts: list[str]) -> None:
    """Delete the smoke test folder tree (just the top-level _smoketest folder).
    Deleting a folder in Drive recursively removes its children.
    """
    # find the top-level _smoketest folder under root_id
    parent = env["root_id"]
    # walk first two levels: barisbrew-recorded-datas → _smoketest(...)
    first = root_parts[0]  # barisbrew-recorded-datas
    smoke = root_parts[1]  # _smoketest(...)
    escaped_first = uploader.escape_drive_query(first)
    q1 = (
        f"mimeType='application/vnd.google-apps.folder' "
        f"and name='{escaped_first}' and '{parent}' in parents and trashed=false"
    )
    matches = uploader.list_drive_files(service, q1, shared_drive_id=env["shared_drive_id"])
    if not matches:
        return
    first_id = matches[0]["id"]
    escaped_smoke = uploader.escape_drive_query(smoke)
    q2 = (
        f"mimeType='application/vnd.google-apps.folder' "
        f"and name='{escaped_smoke}' and '{first_id}' in parents and trashed=false"
    )
    smoke_matches = uploader.list_drive_files(service, q2, shared_drive_id=env["shared_drive_id"])
    for m in smoke_matches:
        # Content managers on Shared Drives can trash but cannot permanently delete.
        # Trashed folders are auto-purged after 30 days.
        service.files().update(
            fileId=m["id"],
            body={"trashed": True},
            supportsAllDrives=True,
        ).execute()


def step_6_cleanup(service, env: dict, root_parts: list[str]) -> None:
    try:
        _delete_tree(service, env, root_parts)
        _print_step(6, 6, "Cleanup test folder + file", "PASS")
    except Exception as exc:
        _print_step(6, 6, "Cleanup test folder + file", "FAIL", str(exc))
        _hint(6, f"수동 정리 필요: Shared Drive 내 '{root_parts[0]}/{root_parts[1]}/' 폴더 삭제.")
        raise StepError from exc


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    env = _require_env()
    print(f"Using SA key:       {env['sa_path']}")
    print(f"Shared Drive ID:    {env['shared_drive_id']}")
    print(f"Upload root folder: {env['root_id']}")
    print()

    local_path = _make_dummy_file()
    try:
        service = step_1_auth(env)
        step_2_shared_drive_meta(service, env)
        folder_id, parts = step_3_create_folder_tree(service, env)
        file_id = step_4_upload(service, env, folder_id, local_path)
        step_5_reupload_skip(service, env, folder_id, local_path, file_id)
        step_6_cleanup(service, env, parts)
        print("\nAll Shared Drive checks passed.")
        return 0
    except StepError:
        # Attempt cleanup even on failure so we don't leave orphan folders
        try:
            step_6_cleanup(service, env, ["barisbrew-recorded-datas", SMOKE_TEST_ROOT_SEGMENT])
        except Exception:
            pass
        print("\nShared Drive checks FAILED. See hints above.", file=sys.stderr)
        return 1
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
