#!/usr/bin/env python3

import argparse
import json
import logging
import mimetypes
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


KST = timezone(timedelta(hours=9))
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


@dataclass
class UploadConfig:
    auth_mode: str
    service_account_path: str
    oauth_client_path: Optional[str]
    oauth_token_path: Optional[str]
    oauth_console: bool
    root_folder_id: Optional[str]
    shared_drive_id: Optional[str]
    robot_id: str
    shift: str
    operator: str
    min_age_seconds: int
    delete_local: bool
    verify_md5: bool
    dry_run: bool


def build_drive_service(service_account_path: str):
    creds = service_account.Credentials.from_service_account_file(
        service_account_path,
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def build_drive_service_oauth(client_secrets_path: str, token_path: Optional[str], use_console: bool):
    creds = None
    if token_path and os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, DRIVE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, DRIVE_SCOPES)
            if use_console:
                # Some environments cannot launch a local server; use OOB redirect for manual copy/paste.
                # Note: Google may block OOB for newly created OAuth clients.
                flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
                auth_url, _ = flow.authorization_url(prompt="consent")
                print("Open this URL in your browser and authorize access:")
                print(auth_url)
                code = input("Enter the authorization code: ").strip()
                flow.fetch_token(code=code)
                creds = flow.credentials
            else:
                creds = flow.run_local_server(port=0)
        if token_path:
            with open(token_path, "w") as handle:
                handle.write(creds.to_json())

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def escape_drive_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def list_drive_files(service, query: str, shared_drive_id: Optional[str] = None) -> List[Dict]:
    params = {
        "q": query,
        "spaces": "drive",
        "fields": "files(id,name,size,md5Checksum,modifiedTime)",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
        "pageSize": 100,
    }
    if shared_drive_id:
        params["corpora"] = "drive"
        params["driveId"] = shared_drive_id
    results = service.files().list(**params).execute()
    return results.get("files", [])


def get_or_create_folder(service, parent_id: str, name: str, shared_drive_id: Optional[str] = None) -> str:
    escaped_name = escape_drive_query(name)
    query = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{escaped_name}' and '{parent_id}' in parents and trashed=false"
    )
    matches = list_drive_files(service, query, shared_drive_id=shared_drive_id)
    if matches:
        return matches[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(
        body=metadata,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return created["id"]


def ensure_drive_path(service, root_id: str, parts: List[str], shared_drive_id: Optional[str] = None) -> str:
    current_id = root_id
    for part in parts:
        current_id = get_or_create_folder(service, current_id, part, shared_drive_id=shared_drive_id)
    return current_id


def parse_session_datetime(session_name: str) -> Optional[datetime]:
    match = re.match(r"session_(\d{8})_(\d{6})", session_name)
    if not match:
        return None
    date_part, time_part = match.groups()
    try:
        return datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except ValueError:
        return None


def collect_session_files(session_dir: str) -> List[str]:
    files = []
    for entry in os.scandir(session_dir):
        if not entry.is_file():
            continue
        if entry.name == "upload_ledger.json":
            continue
        files.append(entry.path)
    return sorted(files)


def compute_md5(path: str, chunk_size: int = 1024 * 1024) -> str:
    import hashlib

    md5 = hashlib.md5()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def find_existing_file(service, parent_id: str, name: str, shared_drive_id: Optional[str] = None) -> List[Dict]:
    escaped_name = escape_drive_query(name)
    query = f"name='{escaped_name}' and '{parent_id}' in parents and trashed=false"
    return list_drive_files(service, query, shared_drive_id=shared_drive_id)


def execute_resumable(request) -> Dict:
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logging.info("Upload progress: %d%%", int(status.progress() * 100))
    return response


def verify_remote_file(service, file_id: str, local_size: int, local_md5: Optional[str]) -> bool:
    remote = service.files().get(
        fileId=file_id,
        fields="id,size,md5Checksum",
        supportsAllDrives=True,
    ).execute()
    size_ok = "size" in remote and int(remote["size"]) == local_size
    if not size_ok:
        return False
    if local_md5 is None:
        return True
    return remote.get("md5Checksum") == local_md5


def upload_file_to_folder(
    service,
    local_path: str,
    parent_id: str,
    verify_md5: bool = False,
    dry_run: bool = False,
    shared_drive_id: Optional[str] = None,
) -> Tuple[str, bool]:
    name = os.path.basename(local_path)
    local_size = os.path.getsize(local_path)
    local_md5 = compute_md5(local_path) if verify_md5 else None

    existing = find_existing_file(service, parent_id, name, shared_drive_id=shared_drive_id)
    for item in existing:
        if "size" in item and int(item["size"]) == local_size:
            if not verify_md5 or item.get("md5Checksum") == local_md5:
                logging.info("Skip (already exists): %s", name)
                return item["id"], True

    if dry_run:
        logging.info("Dry run: would upload %s", local_path)
        return "", False

    mimetype, _ = mimetypes.guess_type(local_path)
    media = MediaFileUpload(local_path, mimetype=mimetype, resumable=True)

    if existing:
        target_id = existing[0]["id"]
        request = service.files().update(
            fileId=target_id,
            media_body=media,
            fields="id,size,md5Checksum",
            supportsAllDrives=True,
        )
        response = execute_resumable(request)
        file_id = response["id"]
        logging.info("Updated: %s (id=%s)", name, file_id)
    else:
        metadata = {"name": name, "parents": [parent_id]}
        request = service.files().create(
            body=metadata,
            media_body=media,
            fields="id,size,md5Checksum",
            supportsAllDrives=True,
        )
        response = execute_resumable(request)
        file_id = response["id"]
        logging.info("Uploaded: %s (id=%s)", name, file_id)

    verified = verify_remote_file(service, file_id, local_size, local_md5)
    return file_id, verified


def load_ledger(ledger_path: str) -> Dict:
    if not os.path.exists(ledger_path):
        return {"files": {}, "updated_at": None}
    try:
        with open(ledger_path, "r") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"files": {}, "updated_at": None}


def save_ledger(ledger_path: str, ledger: Dict) -> None:
    ledger["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    with open(ledger_path, "w") as handle:
        json.dump(ledger, handle, indent=2)


def upload_session(
    service,
    session_dir: str,
    config: UploadConfig,
) -> int:
    session_name = os.path.basename(os.path.abspath(session_dir))
    session_dt = parse_session_datetime(session_name)
    if session_dt is None:
        mtime = datetime.fromtimestamp(os.path.getmtime(session_dir), tz=KST)
        session_dt = mtime
        logging.warning("Session name not parseable, using mtime: %s", session_dt.isoformat())

    if not config.root_folder_id:
        raise ValueError("root_folder_id is required for session uploads")

    session_time = session_dt.strftime("%H%M%S")
    path_parts = [
        f"robot_{config.robot_id}",
        session_dt.strftime("%Y"),
        session_dt.strftime("%m"),
        session_dt.strftime("%d"),
        f"{config.shift}_{config.operator}_{session_time}",
    ]
    target_folder_id = ensure_drive_path(
        service,
        config.root_folder_id,
        path_parts,
        shared_drive_id=config.shared_drive_id,
    )
    logging.info("Target Drive folder id: %s", target_folder_id)

    ledger_path = os.path.join(session_dir, "upload_ledger.json")
    ledger = load_ledger(ledger_path)
    files = collect_session_files(session_dir)
    if not files:
        logging.info("No files found in session: %s", session_dir)
        return 0

    uploaded = 0
    now = time.time()
    for local_path in files:
        age = now - os.path.getmtime(local_path)
        if config.min_age_seconds and age < config.min_age_seconds:
            logging.info("Skip (too recent): %s", local_path)
            continue

        try:
            file_id, verified = upload_file_to_folder(
                service,
                local_path,
                target_folder_id,
                verify_md5=config.verify_md5,
                dry_run=config.dry_run,
                shared_drive_id=config.shared_drive_id,
            )
            ledger["files"][os.path.basename(local_path)] = {
                "drive_id": file_id,
                "verified": verified,
                "size": os.path.getsize(local_path),
                "uploaded_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            save_ledger(ledger_path, ledger)
            uploaded += 1

            if config.delete_local and verified and not config.dry_run:
                os.remove(local_path)
                logging.info("Deleted local: %s", local_path)
        except HttpError as exc:
            logging.error("Drive API error for %s: %s", local_path, exc)
            ledger["files"][os.path.basename(local_path)] = {
                "error": str(exc),
                "uploaded_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            save_ledger(ledger_path, ledger)
        except Exception as exc:  # noqa: BLE001
            logging.error("Upload failed for %s: %s", local_path, exc)
            ledger["files"][os.path.basename(local_path)] = {
                "error": str(exc),
                "uploaded_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            save_ledger(ledger_path, ledger)

    return uploaded


def upload_single_file(
    service,
    local_path: str,
    folder_id: str,
    config: UploadConfig,
) -> int:
    file_id, verified = upload_file_to_folder(
        service,
        local_path,
        folder_id,
        verify_md5=config.verify_md5,
        dry_run=config.dry_run,
        shared_drive_id=config.shared_drive_id,
    )
    logging.info("Result id=%s verified=%s", file_id, verified)
    if config.delete_local and verified and not config.dry_run:
        os.remove(local_path)
        logging.info("Deleted local: %s", local_path)
    return 1


def build_config(args: argparse.Namespace) -> UploadConfig:
    service_account_path = args.service_account or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    oauth_client_path = args.oauth_client or os.environ.get("GOOGLE_OAUTH_CLIENT")
    oauth_token_path = args.token_path or os.environ.get("GOOGLE_OAUTH_TOKEN")
    auth_mode = args.auth_mode
    if auth_mode == "service" and not service_account_path:
        raise ValueError("Service account JSON path required (use --service-account or GOOGLE_APPLICATION_CREDENTIALS)")
    if auth_mode == "oauth" and not oauth_client_path:
        raise ValueError("OAuth client JSON required (use --oauth-client or GOOGLE_OAUTH_CLIENT)")

    return UploadConfig(
        auth_mode=auth_mode,
        service_account_path=service_account_path,
        oauth_client_path=oauth_client_path,
        oauth_token_path=oauth_token_path,
        oauth_console=args.oauth_console,
        root_folder_id=args.root_folder or os.environ.get("UPLOAD_ROOT_ID"),
        shared_drive_id=args.shared_drive_id or os.environ.get("UPLOAD_SHARED_DRIVE_ID"),
        robot_id=args.robot_id or os.environ.get("ROBOT_ID", "unknown"),
        shift=args.shift or os.environ.get("SHIFT", "unknown"),
        operator=args.operator or os.environ.get("OPERATOR", "unknown"),
        min_age_seconds=args.min_age_seconds,
        delete_local=args.delete_local,
        verify_md5=args.verify_md5,
        dry_run=args.dry_run,
    )


def main():
    parser = argparse.ArgumentParser(description="Upload recorder outputs to Google Drive")
    parser.add_argument("--service-account", help="Path to Google service account JSON key")
    parser.add_argument("--oauth-client", help="Path to OAuth client secrets JSON")
    parser.add_argument("--token-path", help="Path to OAuth token cache file")
    parser.add_argument("--root-folder", help="Drive folder ID for recordings root")
    parser.add_argument("--shared-drive-id", help="Shared Drive ID (optional)")
    parser.add_argument("--robot-id", help="Robot identifier (ROBOT_ID)")
    parser.add_argument("--shift", help="Shift label (SHIFT)")
    parser.add_argument("--operator", help="Operator label (OPERATOR)")
    parser.add_argument("--min-age-seconds", type=int, default=30, help="Skip files newer than this many seconds")
    parser.add_argument("--delete-local", action="store_true", help="Delete local files after verified upload")
    parser.add_argument("--verify-md5", action="store_true", help="Verify MD5 checksum after upload")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without uploading")
    parser.add_argument("--auth-mode", choices=["service", "oauth"], default="service", help="Auth mode")
    parser.add_argument("--oauth-console", action="store_true", help="Use console OAuth flow (no local server)")
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--session", help="Path to session directory (videos/session_*)")
    group.add_argument("--file", help="Path to a single file to upload")

    parser.add_argument("--folder", help="Drive folder ID for single file uploads")

    args = parser.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(message)s")

    config = build_config(args)
    if config.auth_mode == "oauth":
        service = build_drive_service_oauth(
            config.oauth_client_path,
            config.oauth_token_path,
            config.oauth_console,
        )
    else:
        service = build_drive_service(config.service_account_path)

    if args.session:
        uploaded = upload_session(service, args.session, config)
        logging.info("Uploaded %d file(s) from session", uploaded)
    else:
        if not args.folder:
            raise ValueError("--folder is required when using --file")
        uploaded = upload_single_file(service, args.file, args.folder, config)
        logging.info("Uploaded %d file(s)", uploaded)


if __name__ == "__main__":
    main()
