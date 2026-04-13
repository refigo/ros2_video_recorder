# Google Drive Upload Milestones

Last updated: 2026-04-13

## References
- `docs/spec/upload_spec.md` (인증 전략, 폴더 구조, 설정 키)
- `docs/spec/recording_strategy.md` (upload policy, retention)
- `docs/spec/system_overview.md` (시스템 개요)

## Current Status

### Implemented
- Video recording with 10-min segmented output
- **FFmpeg H.264 녹화** (`--ffmpeg`, libx264 + yuv420p) — Drive 브라우저 재생 호환
- Per-segment timestamp sidecars (`*_timestamps.csv`, `*_timestamps.srt`)
- **업로드 시 SRT 자막 임베딩** (mov_text, `-c:v copy` 무손상) — Drive CC 자막 지원
- `uploader.py`: OAuth + Service Account 인증, 세션 업로드, 파일 업로드, MD5 검증, 중복 skip, 로컬 삭제
- **폴더 구조**: `recording_datas/product/branch_id/YYYY/MM/DD/HH-mm/` (10분 정각 정렬)
- `scripts/generate_oauth_token.py`: OAuth 토큰 생성 스크립트

### Not Yet Done
- 1시간 정각 정렬 녹화 (wall-clock aligned 1-hour segments)
- `--video-label` 설정 (default: `topview_video`, 추후 gripper 등 확장)
- 업로드 디렉토리 구조 변경 (`barisbrew-recorded-datas/{BRANCH_ID}({BRANCH_NAME})/{YYYY-MM}/{YYYYMMDD}/`)
- 파일 네이밍 컨벤션 확립 및 적용
- Shared Drive 업로드 테스트 (구현 완료, 검증 필요)
- 업로드 데몬: polling 방식으로 완료된 세그먼트 자동 업로드 + 검증 후 로컬 삭제
- systemd daemon 세팅 (녹화 + 업로드, 독립 서비스)
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

### M2: 파일 네이밍 컨벤션 + 1시간 정각 정렬 세그먼트
**Goal:** 파일 네이밍 확립, 녹화 세그먼트가 wall-clock 1시간 정각 경계에 맞춰 분할
**Deadline:** 2026-04-15 (화)

**Tasks:**
- [ ] 파일 네이밍 컨벤션 확립:
  - `{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.mp4`
  - `{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}_timestamps.csv`
  - `{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}_timestamps.srt`
  - `BRANCH_ID`, `BRANCH_NAME` 환경변수/CLI 인자 추가
- [ ] `--video-label` CLI 인자 추가 (default: `topview_video`)
  - RealSense RGB → `topview_video`, 추후 gripper → `gripper_video` 등
  - 다중 카메라 시 각각 다른 label로 recorder 인스턴스 실행
- [ ] `camera_recorder.py`에 wall-clock aligned 1시간 segmentation 구현
  - 현재: 시작 시점 기준 duration
  - 변경: 정각 기준 매시 `:00`에 세그먼트 전환
  - 첫 세그먼트는 짧을 수 있음 (e.g. 14:23 시작 → 15:00에 첫 분할)
- [ ] 녹화 중 파일은 `.recording_` prefix로 작성, 세그먼트 완료 시 최종 이름으로 rename

**Acceptance:** 파일명이 `BB003_20260413T140000+0900_topview_video.mp4` 패턴, 1시간 정각 경계 분할 확인

---

### M3: 업로드 디렉토리 구조 변경 + Shared Drive 검증
**Goal:** Google Drive 폴더 구조를 운영 요구사항에 맞게 변경, Shared Drive 업로드 검증
**Deadline:** 2026-04-16 (수)

**Tasks:**
- [ ] `uploader.py` 폴더 구조 변경:
  - 기존: `recording_datas/{product}/{branch_id}/{YYYY}/{MM}/{DD}/{HH-mm}/`
  - 변경: `barisbrew-recorded-datas/{BRANCH_ID}({BRANCH_NAME})/{YYYY-MM}/{YYYYMMDD}/`
- [ ] `BRANCH_ID` + `BRANCH_NAME` 환경변수/CLI 인자 추가 (기존 `branch_id` 대체)
- [ ] 파일명에서 날짜 파싱하여 자동으로 올바른 폴더에 업로드
- [ ] SRT 별도 업로드 제거 — MP4 내 임베딩만 유지
- [ ] **Shared Drive 업로드 테스트** (기존 `--shared-drive-id` 구현 검증)
  - 폴더 생성 권한, 괄호 포함 폴더명 특수문자 처리 확인

**Acceptance:** Shared Drive의 `barisbrew-recorded-datas/BB003(성수본점)/2026-04/20260413/` 구조로 업로드 확인

---

### M4: 업로드 데몬 (자동 업로드 + 검증 후 삭제)
**Goal:** 완료된 세그먼트를 자동 감지, 업로드, 검증 후 로컬 삭제
**Deadline:** 2026-04-17 (목)

**Tasks:**
- [ ] `upload_daemon.py` 신규 작성 — 독립 프로세스로 동작
- [ ] Polling 방식: 5분 간격으로 녹화 디렉토리 스캔
  - 완료 판별: `.recording_` prefix 없는 `.mp4` 파일 = 완료된 세그먼트
  - 미업로드 파일 전부 업로드 (이전 시간대 파일 포함 — 중간 시작 대응)
- [ ] 업로드 → MD5 검증 → 검증 성공 시 로컬 파일 삭제
  - 검증 실패 시 다음 polling 주기에 재시도
- [ ] Exponential backoff retry (네트워크 오류 시)
- [ ] 업로드 상태 로깅 (업로드 완료/실패/삭제 이력)

**Acceptance:** recorder 실행 중 segment 완료 → 자동 업로드 → Drive 확인 → 로컬 삭제, 녹화 무중단

---

### M5: systemd Daemon 세팅
**Goal:** 로봇에 배포 가능한 systemd service 파일 작성
**Deadline:** 2026-04-18 (금)

**Tasks:**
- [ ] `ros2-camera-recorder.service`: 녹화 데몬
- [ ] `ros2-upload-daemon.service`: 업로드 데몬
- [ ] 환경변수 설정 파일 (`/etc/ros2-recorder/config.env`)
  - `BRANCH_ID`, `BRANCH_NAME`, `GOOGLE_APPLICATION_CREDENTIALS` 등
- [ ] 설치/배포 스크립트 작성
- [ ] 로그 출력 → journald 연동

**Acceptance:** `systemctl start ros2-camera-recorder` + `systemctl start ros2-upload-daemon` 으로 전체 파이프라인 작동

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

## Execution Order

```
M0 ✅ → M1 ✅ → M2 (네이밍+정각정렬) → M3 (업로드구조+SharedDrive) → M4 (업로드데몬+삭제) → M5 (systemd) → M6 (E2E 검증)
                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                                       이번 주 목표 (2026-04-13 ~ 2026-04-19)
                                                                              → M7 (SA 전환)
                                                                              → M8 (모니터링)
```

**Immediate Next Step:** M2 — 파일 네이밍 컨벤션 확립 + `--video-label` + 1시간 정각 정렬 세그먼트 구현.

## Risks / Open Questions
- Google Drive API 일일 할당량: 기본 10억 쿼리/일이지만 업로드 대역폭 제한 확인 필요
- 1시간 세그먼트 × 24h = 일 24개 파일 + sidecars → API 호출량 적절
- 네트워크 단절 시 큐 backpressure + 디스크 사용량 모니터링
- robot arm joints 데이터 포맷 최종 결정 (Parquet vs ROS bag)
- 괄호 포함 폴더명 `BB003(성수본점)` — Drive API 특수문자 처리 검증 필요
