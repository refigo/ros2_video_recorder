# M3: 업로드 디렉토리 구조 변경 + Shared Drive 검증 (offline)

**날짜:** 2026-04-14
**범위:** `uploader.py`, `docs/spec/upload_spec.md`, `docs/management/upload_milestones.md`, `README.md`

## 목표

M2가 확립한 새 파일 네이밍 컨벤션 (`{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.mp4/.srt`)과 flat `videos/` 디렉토리 구조에 맞추어, 업로더의 Drive 폴더 구조를 운영 요구사항으로 변경.

- 기존: `recording_datas/{product}/{branch_id}/{YYYY}/{MM}/{DD}/{HH-mm}/` (10분 정각 정렬)
- 변경: `barisbrew-recorded-datas/{BRANCH_ID}({BRANCH_NAME})/{YYYY-MM}/{YYYYMMDD}/` (일 단위)

## 배경

M2 이후 recorder는 `session_YYYYMMDD_HHMMSS/` 디렉토리를 더 이상 생성하지 않고 flat `videos/` 에 세그먼트를 쏟아낸다. 기존 `upload_session()`는 session dir 이름에서 datetime을 파싱했기 때문에, 이 상태로는:

1. `parse_session_datetime()`가 None 반환 → mtime fallback (부정확)
2. 전체 세션을 하나의 타임슬롯(`HH-mm`)으로 묶음 → 일 경계를 넘는 세그먼트가 잘못 라우팅
3. 운영팀은 월/일 단위 탐색을 선호 (10분 슬롯은 과도하게 세분화)

## 설계 결정

1. **Per-file 라우팅.** 각 세그먼트 파일명에서 datetime을 파싱해 자체 폴더에 라우팅. `T000001` 세그먼트는 올바른 `{YYYYMMDD}` 하위로 자동 분류됨.
2. **Folder-id 캐싱.** 같은 날짜에 속한 여러 파일은 `ensure_drive_path`를 1회만 호출. 24 files/day × redundant calls 방지.
3. **SRT 전량 skip (session mode).** `collect_session_files()`에서 `.srt`를 전부 제외. MP4 업로드 시 `transcode_for_drive`가 임베딩을 수행하므로 별도 업로드 불필요. Orphan `.srt`는 경고 로그로 표시.
4. **`.recording_` prefix skip.** 녹화 중인 세그먼트 보호.
5. **파싱 실패 파일은 skip + 경고.** mtime fallback 없음 — 엉뚱한 폴더에 조용히 업로드되는 사고 방지.
6. **`PRODUCT_NAME` 제거.** 새 구조에 product 계층 없음. `BRANCH_ID` + `BRANCH_NAME` required.

## 수정 내용

### `uploader.py`

- `UploadConfig`: `product_name` 제거, `branch_name` 추가.
- `build_config()` + argparse: `--product-name`/`PRODUCT_NAME` → `--branch-name`/`BRANCH_NAME`. Dry-run 시 auth validation skip.
- `parse_segment_filename(name)`: 신규. M2 파일명에서 KST datetime 추출.
- `build_drive_path_parts(branch_id, branch_name, dt)`: 신규. 4-part 리스트 반환.
- `collect_session_files()`: 모든 `.srt` skip, `.recording_` prefix skip, orphan `.srt` 경고.
- `upload_session()`: per-file datetime 파싱 → folder cache → 라우팅 플로우로 재작성. Dry-run 경로는 API 호출 없이 folder ID stub 사용.
- `upload_file_to_folder()`: dry-run short-circuit을 `find_existing_file` 호출 이전으로 이동 (stub folder ID로 API 호출 방지).

### Docs

- `docs/spec/upload_spec.md`: Target Folder Structure + Configuration Keys 섹션 재작성. CLI 예시 갱신 (`python3.10`, `--branch-id`, `--branch-name`).
- `docs/management/upload_milestones.md`: M3 tasks 체크, `Implemented` 섹션 갱신, Execution Order / Next Step 업데이트.
- `README.md`: Google Drive Upload 섹션 전면 재작성 (새 구조, dry-run/oauth/service 예시, SRT 임베딩만 유지 명시).

## 검증

### Offline (완료)

`test_m3_verify.py` (삭제됨 — session-only tool):

1. `parse_segment_filename()` — valid/legacy 케이스 구분, underscore-containing label 처리, `.recording_` prefix 거부, 잘못된 날짜 거부. ✅
2. `build_drive_path_parts()` — 한글 + 괄호 포함 경로 생성. ✅
3. `collect_session_files()` — `.srt` 전부 skip, `.recording_` skip, ledger skip, orphan SRT 경고. ✅
4. `upload_session()` dry-run — 5개 parseable + 1개 legacy 파일로 폴더 캐시 동작 + 일 경계 분할 확인. Legacy 파일 skip 경고 확인. ✅
5. `upload_session()` validation — branch_name 누락 시 `ValueError` 발생. ✅

`videos/` 의 실제 16개 MGOTEST 파일 dry-run:

- `T192003`~`T230000` (5개) → `barisbrew-recorded-datas/MGOTEST(테스트지점)/2026-04/20260413/`
- `T000001`~`T100001` (11개) → `.../20260414/`
- Folder resolve 로그는 2번만 호출됨 (캐시 동작 확인) ✅

### Live (보류)

Shared Drive 자격증명이 확보되는 시점에 M4 통합 중 수행 예정:

- 폴더 생성 (한글 + 괄호 포함 폴더명 `BB003(성수본점)`)
- 실제 MP4 업로드 + MD5 검증 + 재업로드 시 skip (idempotency)
- Drive 브라우저 재생 (H.264 + CC 자막 동작)

괄호/한글이 Drive folder name에서 실패하면 ASCII 폴백 (`{BRANCH_ID}_{BRANCH_NAME_ASCII}`) 적용 예정. `escape_drive_query()`는 parens를 escape하지 않지만, Drive 쿼리 문법상 parens는 literal이므로 이론상 문제 없음.

## 선행 작업

- M2 완료 (file naming, wall-clock alignment, `.recording_` prefix, SRT real-time append)

## 후속 작업

- **M4**: SRT 임베딩 + 업로드 + MD5 검증 + 로컬 삭제를 하나의 cron 스크립트 (`1 * * * *`)로 통합. M3 live 검증도 이 때 함께 수행.
- **M5**: systemd (recorder) + crontab (uploader) 배포 패키징.
- **M6**: E2E 24h 무중단 녹화+업로드 검증.
