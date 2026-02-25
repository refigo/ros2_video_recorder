# Google Drive Upload Milestones

Last updated: 2026-02-25

## References
- `docs/spec/upload_spec.md` (인증 전략, 폴더 구조, 설정 키)
- `docs/spec/recording_strategy.md` (upload policy, retention)
- `docs/spec/system_overview.md` (시스템 개요)

## Current Status

### Implemented
- Video recording with 10-min segmented output
- Per-segment timestamp sidecars (`*_timestamps.csv`, `*_timestamps.srt`)
- `uploader.py`: OAuth + Service Account 인증, 세션 업로드, 파일 업로드, MD5 검증, 중복 skip, 로컬 삭제
- `scripts/generate_oauth_token.py`: OAuth 토큰 생성 스크립트

### Not Yet Done
- 폴더 구조 변경: `product/branch_id/YYYY/MM/DD/HH-mm/` 형식
- 10분 정각 정렬 (wall-clock aligned segments)
- 자동 업로드 스케줄링 (segment 완료 시 자동 trigger)

---

## Milestone Plan

### M0: OAuth 테스트 환경 구축 ✅ → 실행 대기
**Goal:** 개인 Google Drive에 업로드 테스트 성공

**Tasks:**
- [ ] Google Cloud Console에서 OAuth 2.0 Client ID 생성 (Desktop app)
- [ ] Google Drive API 활성화
- [ ] `client_secrets.json` → `keys/` 에 저장
- [ ] `generate_oauth_token.py`로 토큰 생성
- [ ] 테스트 세션으로 업로드 실행 확인

**Acceptance:** `uploader.py --auth-mode oauth`로 개인 Drive에 파일 업로드 성공

---

### M1: 폴더 구조 변경
**Goal:** `recording_datas/product/branch_id/YYYY/MM/DD/HH-mm/` 경로로 업로드

**Tasks:**
- [ ] `uploader.py`의 `upload_session()` path 구성을 새 구조로 변경
  - 기존: `robot_<id>/YYYY/MM/DD/shift_operator_HHMMSS/`
  - 변경: `recording_datas/product/branch_id/YYYY/MM/DD/HH-mm/`
- [ ] `PRODUCT_NAME`, `BRANCH_ID` 환경변수/CLI 인자 추가
- [ ] 10분 단위 폴더명 생성 로직 (분을 0/10/20/30/40/50으로 내림)

**Acceptance:** 업로드 시 Drive에 올바른 계층 폴더 자동 생성 확인

---

### M2: 10분 정각 정렬 세그먼트
**Goal:** 녹화 세그먼트가 wall-clock 10분 경계에 맞춰 분할

**Tasks:**
- [ ] `camera_recorder.py`에 wall-clock aligned segmentation 옵션 추가
  - 현재: 시작 시점 기준 10분
  - 변경: 정각 기준 `:00`, `:10`, `:20`, `:30`, `:40`, `:50`에 세그먼트 전환
- [ ] 첫 세그먼트는 짧을 수 있음 (e.g. 13:07 시작 → 13:10에 첫 분할)

**Acceptance:** 세그먼트 파일명의 시간이 10분 정각 경계와 일치

---

### M3: 자동 업로드 Daemon
**Goal:** 세그먼트 완료 시 자동으로 업로드 큐에 추가 → 업로드 실행

**Tasks:**
- [ ] Watchdog 또는 inotify 기반 파일 감시, 또는 recorder 콜백 방식 결정
- [ ] 업로드 큐 (in-memory or SQLite) 구현
- [ ] Exponential backoff retry (max 3회)
- [ ] 업로드 성공 후 로컬 파일 정책 적용 (보존 or 삭제)

**Acceptance:** recorder 실행 중 segment 완료 → 자동 업로드 → Drive에서 파일 확인

---

### M4: 검증 + 정리 + Retention
**Goal:** 업로드 무결성 검증 후 로컬 정리

**Tasks:**
- [ ] MD5 검증 활성화 (기존 구현 활용)
- [ ] Retention policy: 로컬에 최근 6시간분 유지
- [ ] 검증 실패 파일 재시도 로직
- [ ] `upload_ledger.json` 기반 상태 추적

**Acceptance:** 검증된 파일만 삭제, 미검증 파일 유지 및 재시도

---

### M5: Service Account 전환 (프로덕션)
**Goal:** 회사 시스템에 Service Account 기반 무인 업로드 적용

**Tasks:**
- [ ] Service Account 생성 + 회사 Drive 폴더 권한 설정
- [ ] `--auth-mode service` 로 전환
- [ ] Shared Drive 지원 검증
- [ ] Robot별 SA key 배포 전략 문서화

**Acceptance:** headless robot에서 Service Account로 회사 Drive에 자동 업로드 성공

---

### M6: Monitoring + 운영 가시성
**Goal:** 업로드 상태를 빠르게 확인

**Tasks:**
- [ ] CLI 상태 출력: 마지막 업로드 시각, 대기 중 세그먼트 수, 마지막 에러
- [ ] 일일 요약 로그 (optional)

**Acceptance:** 운영자가 로그 없이 상태 확인 가능

---

## Execution Order

```
M0 (OAuth 테스트) → M1 (폴더 구조) → M2 (정각 정렬) → M3 (자동 업로드)
                                                         → M4 (검증/정리)
                                                         → M5 (SA 전환)
                                                         → M6 (모니터링)
```

**Immediate Next Step:** M0 실행 — Google Cloud Console에서 OAuth 설정 후 개인 Drive 업로드 테스트.

## Risks / Open Questions
- Google Drive API 일일 할당량: 기본 10억 쿼리/일이지만 업로드 대역폭 제한 확인 필요
- 10분 세그먼트 × 24h = 일 144개 파일 + sidecars → API 호출량 관리
- 네트워크 단절 시 큐 backpressure + 디스크 사용량 모니터링
- robot arm joints 데이터 포맷 최종 결정 (Parquet vs ROS bag)
