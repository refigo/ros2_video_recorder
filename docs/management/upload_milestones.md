# Google Drive Upload Milestones

Last updated: 2026-04-14 (M3 offline 완료)

## References
- `docs/spec/upload_spec.md` (인증 전략, 폴더 구조, 설정 키)
- `docs/spec/recording_strategy.md` (upload policy, retention)
- `docs/spec/system_overview.md` (시스템 개요)

## Current Status

### Implemented
- Video recording with segmented output
- **FFmpeg H.264 녹화** (`--ffmpeg`, libx264 + yuv420p) — Drive 브라우저 재생 호환
- **업로드 시 SRT 자막 임베딩** (mov_text, `-c:v copy` 무손상) — Drive CC 자막 지원
- `uploader.py`: OAuth + Service Account 인증, 세션 업로드, 파일 업로드, MD5 검증, 중복 skip, 로컬 삭제
- **폴더 구조 (M3 완료 — offline)**: `barisbrew-recorded-datas/{BRANCH_ID}({BRANCH_NAME})/{YYYY-MM}/{YYYYMMDD}/` — 파일명 기반 per-file 라우팅, folder-id 캐싱
- `scripts/generate_oauth_token.py`: OAuth 토큰 생성 스크립트
- **파일 네이밍 컨벤션 (M2 완료)**: `{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.{mp4,srt}`
- **Wall-clock 1시간 정각 정렬 세그먼트 (M2 완료)**: 매시 `:00`에 세그먼트 전환
- **`.recording_` prefix + rename (M2 완료)**: 녹화 중 파일은 `.recording_` prefix, 세그먼트 완료 시 최종 이름으로 rename (M4 cron 파이프라인 준비)
- **SRT 실시간 append (M2 완료)**: 프레임별 SRT 엔트리 파일 직접 기록 — crash safety 확보
- **CSV timestamps 제거 (M2 완료)**: SRT로 일원화

### Not Yet Done
- Shared Drive 라이브 업로드 테스트 (M3 offline 검증 완료; live 검증은 creds 확보 후 M4와 함께 수행)
- SRT 임베딩 워커 (세그먼트 완료 후 별도 프로세스로 remux)
- Cron 기반 자동 업로드 (매시 :01) + MD5 검증 후 로컬 삭제
- systemd (녹화) + crontab (업로드) 배포 세팅
- LeRobot 호환 인코딩 옵션 (GOP=2) → `docs/management/backlog.md` 참조

---

## Milestone Plan

### M0: OAuth 테스트 환경 구축 ✅ 완료 (2026-02-25)
**Goal:** 개인 Google Drive에 업로드 테스트 성공

**Tasks:**
- [x] Google Cloud Console에서 OAuth 2.0 Client ID 생성 (Desktop app)
- [x] Google Drive API 활성화
- [x] `client_secrets.json` → `keys/` 에 저장
- [x] `generate_oauth_token.py`로 토큰 생성
- [x] 테스트 세션으로 업로드 실행 확인
- [x] H.264 녹화 + 자막 임베딩 + Drive 재생/CC 검증

**Acceptance:** ✅ Drive에서 H.264 영상 재생 + CC 자막 활성화 확인

---

### M1: 폴더 구조 변경 ✅ 완료 (2026-02-25)
**Goal:** `recording_datas/product/branch_id/YYYY/MM/DD/HH-mm/` 경로로 업로드

**Tasks:**
- [x] `uploader.py`의 `upload_session()` path 구성을 새 구조로 변경
- [x] `PRODUCT_NAME`, `BRANCH_ID` 환경변수/CLI 인자 추가
- [x] 10분 단위 폴더명 생성 로직 (분을 0/10/20/30/40/50으로 내림)

**Acceptance:** ✅ `recording_datas/baris_brew/test_branch/2026/02/25/19-20/` 구조 확인

---

### M2: 파일 네이밍 컨벤션 + 1시간 정각 정렬 세그먼트 ✅ 완료 (2026-04-14)
**Goal:** 파일 네이밍 확립, 녹화 세그먼트가 wall-clock 1시간 정각 경계에 맞춰 분할

**Reference:** `docs/history/07_m2_naming_wall_clock_srt_20260414_*/`

**Tasks:**
- [x] 파일 네이밍 컨벤션 확립:
  - `{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.mp4`
  - `{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.srt`
  - `--branch-id` CLI 인자 추가 (required)
- [x] `--video-label` CLI 인자 추가 (default: `topview_video`)
- [x] `camera_recorder.py`에 wall-clock aligned 1시간 segmentation 구현
  - 매시 `:00`에 세그먼트 전환 (seconds until next hour 계산)
- [x] 녹화 중 파일은 `.recording_` prefix로 작성, 세그먼트 완료 시 최종 이름으로 rename
- [x] SRT 파일을 녹화 중 실시간 append 방식으로 기록 (crash safety)
- [x] CSV timestamps 파일 제거 (SRT로 일원화)

**Acceptance:** ✅ E2E 24h 녹화 테스트로 검증 — `videos/MGOTEST_20260413T200000+0900_topview_video.{mp4,srt}` 등 정각 정렬 확인, `.recording_` → 최종 rename 확인, SRT 실시간 기록 확인

**Deferred to M3:**
- `BRANCH_NAME` CLI 인자 (M3 업로드 폴더 구조에서 함께 처리)

---

### M3: 업로드 디렉토리 구조 변경 + Shared Drive 검증 ✅ offline 완료 (2026-04-14)
**Goal:** Google Drive 폴더 구조를 운영 요구사항에 맞게 변경, Shared Drive 업로드 검증
**Deadline:** 2026-04-16 (수)

**Reference:** `docs/history/08_m3_upload_restructure_20260414_*/`

**Tasks:**
- [x] `uploader.py` 폴더 구조 변경:
  - 기존: `recording_datas/{product}/{branch_id}/{YYYY}/{MM}/{DD}/{HH-mm}/`
  - 변경: `barisbrew-recorded-datas/{BRANCH_ID}({BRANCH_NAME})/{YYYY-MM}/{YYYYMMDD}/`
- [x] `BRANCH_ID` + `BRANCH_NAME` 환경변수/CLI 인자 추가 (`PRODUCT_NAME` 제거)
- [x] 파일명에서 날짜 파싱하여 per-file 폴더 라우팅 (일 경계 세그먼트 안전 처리)
- [x] Folder-id 캐싱 (같은 run 내 중복 `ensure_drive_path` 호출 제거)
- [x] SRT 별도 업로드 제거 — MP4 내 임베딩만 유지 (`collect_session_files`에서 `.srt` 전부 skip)
- [x] `.recording_` prefix 파일 skip (녹화 중인 세그먼트 보호)
- [x] Offline 검증 완료 — unit tests + dry-run against `videos/` 16 files (day boundary 분할, 캐시 동작, legacy 파일 skip 경고 확인)
- [ ] **Shared Drive 라이브 업로드 테스트** (creds 확보 후 M4 통합 중 수행)
  - 폴더 생성 권한, 괄호 + 한글 폴더명 `BB003(성수본점)` 특수문자 live 검증

**Acceptance (offline):** ✅ dry-run으로 `barisbrew-recorded-datas/MGOTEST(테스트지점)/2026-04/20260413/` + `.../20260414/` 올바른 분할 확인
**Acceptance (live):** 미완료 — M4 통합 중 수행

---

### M4: Cron 통합 (SRT 임베딩 + 업로드 + 검증 후 삭제)
**Goal:** 매시 :01 cron 단일 스크립트에서 임베딩 → 업로드 → 삭제 순차 실행
**Deadline:** 2026-04-17 (목)

**설계: File-based State Machine**
```
녹화 중:     .recording_XXX.mp4 + .recording_XXX.srt
녹화 완료:   XXX.mp4 + XXX.srt           ← 임베딩 대상
임베딩 완료: XXX.mp4 (srt 삭제됨)         ← 업로드 대상
업로드 완료: (파일 삭제됨)
```
파일 존재/부재가 파이프라인 단계를 결정. cron 중간 실패 시 다음 실행에서 남은 작업부터 재개.

**Tasks:**
- [ ] `upload_cron.sh` (또는 `upload_cron.py`) 작성 — one-shot 스크립트, 2단계 순차 실행:
  - **Step 1 — SRT 임베딩**: `.mp4` + `.srt` 쌍 감지 (`min-age-seconds=30`)
    → `ffmpeg -c:v copy -c:s mov_text` remux → 원본 교체 → `.srt` 삭제
  - **Step 2 — 업로드**: `.srt` 없는 `.mp4` 감지 (= 임베딩 완료)
    → 업로드 → MD5 검증 → 검증 성공 시 로컬 삭제
    → 검증 실패 시 로컬 유지, 다음 cron 주기에 재시도
- [ ] 미업로드 파일 전부 처리 (이전 시간대 포함 — 중간 시작/이전 실패 대응)
- [ ] crontab 등록: `1 * * * *` (매시 :01 실행)
  - 세그먼트 전환(:00) 후 60초 여유 → 파일 충돌 위험 제거
- [ ] 업로드 상태 로깅 (stdout → cron mail 또는 로그 파일)

**Acceptance:** 매시 :01 → 임베딩 → 업로드 → Drive CC 자막 확인 → 로컬 삭제. cron 실패 후 재실행 시 정상 복구.

---

### M5: systemd + cron 배포 세팅
**Goal:** 로봇에 배포 가능한 systemd service (녹화) + crontab (업로드) 작성
**Deadline:** 2026-04-18 (금)

**Tasks:**
- [ ] `ros2-camera-recorder.service`: 녹화 데몬 (systemd)
- [ ] crontab 등록 스크립트: `upload_cron` 매시 :01 실행
- [ ] 환경변수 설정 파일 (`/etc/ros2-recorder/config.env`)
  - `BRANCH_ID`, `BRANCH_NAME`, `GOOGLE_APPLICATION_CREDENTIALS` 등
- [ ] 설치/배포 스크립트 작성 (systemd + crontab 한번에 세팅)
- [ ] 로그: recorder → journald, uploader → 로그 파일 또는 journald

**Acceptance:** `systemctl start ros2-camera-recorder` + cron 매시 :01 업로드 자동 실행

---

### M6: End-to-End 검증 + 안정화
**Goal:** 전체 파이프라인 (녹화 → 세그먼트 완료 → 업로드 → Drive 확인) 통합 테스트
**Deadline:** 2026-04-19 (토)

**Tasks:**
- [ ] RealSense RGB topview 토픽으로 24시간 연속 녹화 테스트
- [ ] 1시간 정각 세그먼트 분할 검증
- [ ] 프레임 복제 동작 확인 (irregular FPS 대응)
- [ ] 자동 업로드 → Drive 폴더 구조 확인
- [ ] SRT 임베딩 → Drive CC 자막 재생 확인
- [ ] 네트워크 단절/복구 시 업로드 재시도 확인
- [ ] systemd restart 후 정상 복구 확인

**Acceptance:** 24시간 무중단 녹화+업로드 성공, Drive에서 영상 재생 + CC 자막 확인

---

### M7: Service Account 전환 (프로덕션)
**Goal:** 회사 시스템에 Service Account 기반 무인 업로드 적용

**Tasks:**
- [ ] Service Account 생성 + 회사 Drive 폴더 권한 설정
- [ ] `--auth-mode service` 로 전환
- [ ] Shared Drive 지원 검증
- [ ] Robot별 SA key 배포 전략 문서화

**Acceptance:** headless robot에서 Service Account로 회사 Drive에 자동 업로드 성공

---

### M8: Monitoring + 운영 가시성
**Goal:** 업로드 상태를 빠르게 확인

**Tasks:**
- [ ] CLI 상태 출력: 마지막 업로드 시각, 대기 중 세그먼트 수, 마지막 에러
- [ ] 일일 요약 로그 (optional)

**Acceptance:** 운영자가 로그 없이 상태 확인 가능

---

### M9: 녹화 최적화 (Post-stabilization)
**Goal:** Python 기반 녹화 파이프라인의 CPU/메모리 부하 경감

**Reference:** `docs/study/recording_optimization.md`

**Tasks:**
- [ ] FFmpeg preset 변경 (`medium` → `ultrafast` 또는 `fast`) — CPU 부하 절감
- [ ] `tobytes()` 제거 → `memoryview(frame)` zero-copy 적용
- [ ] passthrough encoding: RealSense rgb8 → ffmpeg rgb24 직접 전달 (BGR 변환 생략)
- [ ] 부하 측정 (before/after 비교)

**주의사항:** 각 최적화를 하나씩 적용하고 기능 검증 후 다음 적용. 한번에 여러 개 변경 금지.

**선행 조건:** M6 (E2E 검증) 완료 후 진행. 추후 rclcpp 포팅 시 별도 계획.

**Acceptance:** 녹화+업로드 기능 정상 유지 상태에서 CPU 사용률 감소 확인

---

## Execution Order

```
M0 ✅ → M1 ✅ → M2 ✅ → M3 ✅(offline) → M4 (임베딩+cron+삭제) → M5 (systemd+cron) → M6 (E2E 검증)
                                        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                                                     이번 주 목표 (2026-04-13 ~ 2026-04-19)
                                                                              → M7 (SA 전환)
                                                                              → M8 (모니터링)
                                                                              → M9 (녹화 최적화)
```

**Immediate Next Step:** M4 — SRT 임베딩 + 업로드 + MD5 검증 + 로컬 삭제를 하나의 cron 스크립트로 통합. M3의 live 검증은 M4 통합 시 실제 Shared Drive 업로드로 함께 수행.

## Risks / Open Questions
- Google Drive API 일일 할당량: 기본 10억 쿼리/일이지만 업로드 대역폭 제한 확인 필요
- 1시간 세그먼트 × 24h = 일 24개 파일 + sidecars → API 호출량 적절
- 네트워크 단절 시 큐 backpressure + 디스크 사용량 모니터링
- robot arm joints 데이터 포맷 최종 결정 (Parquet vs ROS bag)
- 괄호 포함 폴더명 `BB003(성수본점)` — Drive API 특수문자 처리 검증 필요
