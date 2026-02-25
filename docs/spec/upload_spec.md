# Google Drive Upload Spec

Last updated: 2026-02-25

## Objective

Upload recorded data (video segments, sidecars, and future joint logs) to Google Drive
on a **10-minute aligned schedule**, organized by product/branch/time hierarchy.

## Target Folder Structure

```
recording_datas/
  └── <product>/                  # e.g. baris_brew
        └── <branch_id>/          # e.g. gangnam_01
              └── <YYYY>/
                    └── <MM>/
                          └── <DD>/
                                └── <HH>-<mm>/   # 10-min window, e.g. 14-30
                                      ├── seg_20260225_143000.mp4
                                      ├── seg_20260225_143000_timestamps.csv
                                      ├── seg_20260225_143000_timestamps.srt
                                      └── seg_20260225_143500.mp4 ...
```

- `<product>`: 제품/서비스 이름 (env: `PRODUCT_NAME`, default `baris_brew`)
- `<branch_id>`: 지점 식별자 (env: `BRANCH_ID`, default `test_branch`)
- 시계열: `YYYY/MM/DD/HH-mm` — 10분 정각 기준 (00, 10, 20, 30, 40, 50)

## Upload Cadence

- Recording: 10-minute segments aligned to wall-clock boundaries (`:00`, `:10`, `:20`, …)
- Upload trigger: segment가 완료(close)되면 즉시 업로드 큐에 추가
- Upload window: 이전 segment가 close된 후 `MIN_AGE_SECONDS` (default 30s) 이후 업로드 시작
- Retry: 실패 시 exponential backoff (max 3 retries per segment)

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
   python3 uploader.py --auth-mode oauth \
     --oauth-client keys/client_secrets.json \
     --token-path keys/gdrive_token.json \
     --session videos/session_20260225_120000
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
   export UPLOAD_ROOT_ID=<회사Drive_폴더_id>
   export UPLOAD_SHARED_DRIVE_ID=<shared_drive_id>  # Shared Drive 사용 시
   python3 uploader.py --auth-mode service \
     --session videos/session_20260225_120000
   ```

## Configuration Keys

| Key | Env Var | Default | Description |
|-----|---------|---------|-------------|
| product | `PRODUCT_NAME` | `baris_brew` | 제품/서비스명 |
| branch_id | `BRANCH_ID` | `test_branch` | 지점 식별자 |
| root_folder_id | `UPLOAD_ROOT_ID` | — (required) | Drive 최상위 폴더 ID |
| shared_drive_id | `UPLOAD_SHARED_DRIVE_ID` | — (optional) | Shared Drive ID |
| auth_mode | — | `service` | `service` or `oauth` |
| segment_duration | — | `600` (10 min) | 세그먼트 길이(초) |
| min_age_seconds | — | `30` | 업로드 전 대기 시간 |
| delete_local | — | `false` | 업로드 후 로컬 삭제 여부 |
| verify_md5 | — | `false` | MD5 검증 여부 |

## Data Types (Current & Planned)

| Type | Format | Status |
|------|--------|--------|
| Video segments | `.mp4` | Implemented |
| Timestamp CSV | `_timestamps.csv` | Implemented |
| Timestamp SRT | `_timestamps.srt` | Implemented |
| Robot arm joints | `_joints.parquet` | Planned |
| Session metadata | `_metadata.json` | Planned |

## Security Notes

- `keys/` 디렉토리는 `.gitignore`에 포함 — 절대 커밋하지 않음
- Service Account key는 robot별 개별 발급 권장
- OAuth token 파일도 `.gitignore` 대상
