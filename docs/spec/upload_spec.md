# Google Drive Upload Spec

Last updated: 2026-04-14

## Objective

Upload recorded data (video segments, sidecars, and future joint logs) to Google Drive on an **hourly cron-driven** schedule, organized by **branch / month / day** hierarchy. Paths are derived per-file from the M2 filename convention, enabling a flat local `videos/` directory and day-boundary-safe routing.

## Target Folder Structure (M3 revised)

```
[Shared Drive root] / robot-data-archive /        # prod (top-level)
[Shared Drive root] / 로봇지능화팀 / robot-data-archive-dev /   # dev
  └── <PRODUCT>/                        # barisbrew / storagy / deux
        └── <BRANCH_ID>(<BRANCH_NAME>)/ # e.g. BB003(성수본점)
              └── <YYYY-MM>/            # e.g. 2026-04
                    └── <YYYYMMDD>/     # e.g. 20260414
                          ├── BB003_20260414T140000+0900_topview_video.mp4
                          └── ...
```

- `robot-data-archive` / `robot-data-archive-dev`: 사용자가 Drive에서 수동 생성한 루트 폴더. 업로더는 이 폴더 ID(`UPLOAD_ROOT_ID`)만 받고, 내부에 `{PRODUCT}/...` 부터 자동 생성.
- `<PRODUCT>`: 로봇 제품 코드네임 (env: `PRODUCT`, CLI: `--product`, required). 예: `barisbrew`, `storagy`, `deux`
- `<BRANCH_ID>`: 지점 코드 (env: `BRANCH_ID`, CLI: `--branch-id`, required)
- `<BRANCH_NAME>`: 지점 표시명 (env: `BRANCH_NAME`, CLI: `--branch-name`, required)
- 월/일: 파일명에서 파싱 (`{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{label}.mp4`)
- SRT는 업로드 시 `transcode_for_drive`로 MP4에 임베딩 (`mov_text`) → 별도 업로드 없음
- Dev/Prod 분리: 동일 SA 키 + 동일 Shared Drive, `UPLOAD_ROOT_ID`만 다르게 설정

## Upload Cadence (M4 완료)

- Recording: 1-hour segments aligned to wall-clock `:00` (M2 완료)
- Upload trigger: cron `1 * * * *` (매시 :01) — 세그먼트 전환 후 60초 버퍼
- Upload window: `min-age-seconds` (default 30s) — 파일 완료 확정 후
- 중복 방지: MD5 기반 dedup. 검증 성공 시 로컬 삭제.

**Cron 스크립트 2단계 (M4):**
1. `scripts/embed_srt.py` — `.mp4`+`.srt` 쌍 → `ffmpeg -c:v copy -c:s mov_text` 리먹스 → `.embedding.tmp` → atomic replace → `.srt` 삭제
2. `scripts/upload_cron.py` — embed 완료된 `.mp4` 업로드 → MD5 검증 → 로컬 삭제. 이 단계에서 `transcode_for_drive`는 이미 H.264 + subtitle이므로 no-op pass-through.

배포: `scripts/upload_cron.sh` 래퍼가 `/etc/ros2-recorder/uploader.env` 로드 + `/usr/bin/python3.10` 호출.

## Authentication Strategy

### Phase 1 — 개인 계정 테스트 (OAuth Desktop Flow)

**왜 OAuth인가?**
- 개인 Google Drive에 즉시 접근 가능 — Service Account는 개인 Drive에 직접 쓸 수 없음
- 최초 1회 브라우저 인증 → 토큰 파일 저장 → 이후 자동 갱신
- 이미 구현됨 (`uploader.py --auth-mode oauth`)

**Setup:**
1. Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID (Desktop app)
2. Google Drive API 활성화
3. `client_secrets.json` 다운로드 → `keys/` 디렉토리에 저장
4. 토큰 생성:
   ```bash
   python3 scripts/generate_oauth_token.py \
     --client-secrets keys/client_secrets.json \
     --out keys/gdrive_token.json
   ```
5. 업로드 실행:
   ```bash
   export UPLOAD_ROOT_ID=<개인Drive_폴더_id>
   python3.10 uploader.py --auth-mode oauth \
     --oauth-client keys/client_secrets.json \
     --token-path keys/gdrive_token.json \
     --product barisbrew --branch-id BB003 --branch-name "성수본점" \
     --session videos/
   ```

**토큰 수명:** access token 1시간, refresh token으로 자동 갱신. 6개월 미사용 시 만료.

### Phase 2 — 회사 시스템 (Service Account)

**왜 Service Account인가?**
- 완전 무인 운영 — 브라우저 인증 불필요
- JSON key 파일만 있으면 동작 — headless robot에 최적
- Shared Drive에 직접 쓰기 가능 (관리자가 멤버로 추가)
- 토큰 만료/갱신 관리 불필요

**Setup:**
1. Google Cloud Console → Service Account 생성
2. JSON key 다운로드 → robot에 안전 배포
3. 회사 Google Drive에서 대상 폴더 또는 Shared Drive에 Service Account 이메일을 편집자로 추가
4. 업로드 실행:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa_key.json
   export UPLOAD_ROOT_ID=<robot-data-archive[-dev]_폴더_id>
   export UPLOAD_SHARED_DRIVE_ID=<shared_drive_id>
   export PRODUCT=barisbrew
   export BRANCH_ID=BB003
   export BRANCH_NAME=성수본점
   python3.10 uploader.py --auth-mode service --session videos/
   ```

## Configuration Keys

| Key | Env Var | Default | Description |
|-----|---------|---------|-------------|
| product | `PRODUCT` | — (required) | 로봇 제품 코드네임 (e.g. `barisbrew`) |
| branch_id | `BRANCH_ID` | — (required) | 지점 코드 (e.g. `BB003`) |
| branch_name | `BRANCH_NAME` | — (required) | 지점 표시명 (e.g. `성수본점`) |
| root_folder_id | `UPLOAD_ROOT_ID` | — (required) | `robot-data-archive[-dev]` 폴더 ID |
| shared_drive_id | `UPLOAD_SHARED_DRIVE_ID` | — (optional) | Shared Drive ID |
| auth_mode | — | `service` | `service` or `oauth` |
| min_age_seconds | — | `30` | 업로드 전 대기 시간 |
| delete_local | — | `false` | 업로드 후 로컬 삭제 여부 |
| verify_md5 | — | `false` | MD5 검증 여부 |

## Data Types (Current & Planned)

| Type | Format | Status |
|------|--------|--------|
| Video segments | `.mp4` (H.264, yuv420p, +faststart) | Implemented (M2) |
| SRT subtitles | `.srt` (임베딩 전용, Drive 업로드 시 MP4에 삽입) | Implemented (M2/M3) |
| Robot arm joints | `_joints.parquet` | Planned |
| Session metadata | `_metadata.json` | Planned |

## Security Notes

- `keys/` 디렉토리는 `.gitignore`에 포함 — 절대 커밋하지 않음
- Service Account key는 robot별 개별 발급 권장
- OAuth token 파일도 `.gitignore` 대상
