# Backlog

Last updated: 2026-04-17

이 문서는 즉시 실행하지 않지만 추후 필요한 작업을 관리한다.
우선순위와 의존성이 확정되면 `upload_milestones.md`의 마일스톤으로 승격한다.

---

## LeRobot 호환성

> Reference: `docs/spec/lerobot_compatibility.md`

### BL-01: FFmpeg GOP size 옵션 추가 (우선순위: 높음)

**배경:** LeRobot은 ML 학습 시 임의 프레임 랜덤 접근을 위해 GOP=2를 사용한다.
현재 레코더는 ffmpeg 기본값(~250)을 사용하여 랜덤 접근 성능이 낮다.

**작업 내용:**
- [ ] `camera_recorder.py` ffmpeg 명령에 `-g` 옵션 추가
- [ ] CLI 인자 `--gop` (default: 2 for `--ffmpeg` 모드)
- [ ] 운영 모니터링용 녹화(`--gop 30`)와 학습용 녹화(`--gop 2`) 프리셋 분리 고려

**영향:** 파일 크기 ~30% 증가 (키프레임 빈도 증가), 랜덤 접근 속도 대폭 향상.

**선행 조건:** 없음 (단독 적용 가능)

---

### BL-02: 야간 용량 폭증 해결 + CRF/bitrate 제어 (우선순위: ⭐ 최우선)

**배경:** CRF 23(고정 품질) + 저조도 센서 노이즈 → bitrate 27배 편차 (50 kbps ~ 1.35 Mbps). 야간 1시간 세그먼트가 600 MB에 달해 Drive 업로드 시간 + 용량 비효율. 게다가 Drive 웹 플레이어가 400 MB+ 파일 재생 실패하는 경우 발생. **어두울 때 녹화의 중요도가 낮아 용량 대비 효용이 극히 낮음.**

**측정 데이터 (MGOTEST 24h 녹화):**
| 시간대 | Bitrate | 크기/h | 원인 |
|--------|---------|--------|------|
| 저녁 (조명 안정) | ~50 kbps | ~22 MB | 정적, 압축 효율 최고 |
| 자정~새벽 | ~1 Mbps | ~420 MB | 센서 noise grain → inter-frame 예측 실패 |
| 일출 | ~1.35 Mbps | ~580 MB | noise + 조명 전환 |
| 오전 (밝음) | ~55 kbps | ~24 MB | 압축 효율 회복 |

**작업 내용 (후보 — 조합 가능):**
- [x] `--crf` CLI 인자 추가 (default: 23 → 운영은 28~30 권장)
- [x] `--maxrate` CLI 인자 추가 (예: `2M`) — VBR 상한 cap → 야간 피크 억제
- [ ] (리서치) ffmpeg pre-denoise 필터 (`-vf hqdn3d`) — noise 선제거 → 압축 효율 회복, CPU 부하 측정 필요
- [ ] (리서치) 야간 FPS 감소 (예: 15fps) — 어두운 환경에서 프레임 수 절반 → 용량 절반, 품질 손실 미미
- [ ] (리서치) RealSense 센서 gain 상한 설정 → 근본 noise 억제

**M5 (24h E2E 테스트) 전에 최소 CRF + maxrate 적용 필요** — 600 MB 세그먼트가 있으면 E2E 검증 비실용적.

**영향:** CRF 28 + maxrate 2M 조합 시 야간 세그먼트 ~100-150 MB 예상 (현재 대비 75% 절감).

**선행 조건:** 없음 (단독 적용 가능). M6(24h E2E) 전 적용 필수.

---

### BL-03: AV1 인코딩 옵션 추가 (우선순위: 낮음)

**배경:** LeRobot 기본 코덱은 AV1(`libsvtav1`). H.264보다 ~50% 높은 압축률.
단, 인코딩 속도가 느려 실시간 녹화에는 부적합할 수 있다.

**작업 내용:**
- [ ] `libsvtav1` 인코더 설치 확인 (Ubuntu 22.04 ffmpeg 4.4에는 미포함)
- [ ] 오프라인 변환 스크립트 작성: H.264 → AV1 배치 변환
- [ ] 실시간 인코딩 벤치마크 (CPU 부하, 지연시간)

**영향:** 저장/전송 비용 절감. 실시간 녹화에는 H.264 유지, 업로드/아카이브 시 AV1 변환 권장.

**선행 조건:** BL-01 (GOP 설정이 AV1에서도 필요)

---

### BL-04: LeRobot 데이터셋 변환 파이프라인 (우선순위: 중간)

**배경:** 녹화된 MP4 + CSV를 LeRobot v3.0 데이터셋 구조로 변환하는 도구가 필요하다.

**작업 내용:**
- [ ] 에피소드 분할 로직 (연속 녹화 → 태스크 단위 에피소드)
- [ ] `info.json` 생성기 (피처 스키마, 코덱 정보, 통계)
- [ ] `timestamps.csv` → Parquet 변환 (frame_idx, timestamp 매핑)
- [ ] 비디오 파일 chunking (LeRobot의 `chunk-{idx}/file-{idx}.mp4` 구조)
- [ ] HuggingFace Hub 업로드 지원 (optional)

**선행 조건:** BL-01 (GOP=2), robot arm joints 데이터 수집 (BL-05)

---

### BL-05: Robot Arm Joints 데이터 동기 녹화 (우선순위: 중간)

**배경:** LeRobot 학습에는 비디오와 동기화된 로봇 상태/액션 데이터가 필수.
현재는 비디오와 타임스탬프만 녹화하고 있다.

**작업 내용:**
- [ ] `/joint_states` 토픽 구독 + Parquet 저장
- [ ] 비디오 프레임과 joint state의 타임스탬프 동기화
- [ ] 또는 ROS2 bag 병렬 캡처 후 오프라인 추출

**선행 조건:** 로봇 하드웨어 연동 (joint_states 토픽 발행)

---

## 업로드 파이프라인

### BL-06: ffmpeg preset CLI 옵션 (우선순위: 낮음)

**배경:** 현재 `-preset medium` 하드코딩. 로봇 CPU에 따라 `fast` 또는 `ultrafast`가
필요할 수 있다.

**작업 내용:**
- [ ] `--ffmpeg-preset` CLI 인자 추가

**선행 조건:** 없음

---

### BL-07: 업로드 시 faststart 적용 검증 (우선순위: 낮음)

**배경:** `uploader.py`의 트랜스코딩 단계에서 `-movflags +faststart`를 적용하지만,
H.264 원본에 자막만 임베딩하는 경우(`-c:v copy`)에도 faststart가 적용되는지 확인 필요.

**작업 내용:**
- [ ] `-c:v copy + faststart` 조합에서 moov atom 위치 검증
- [ ] Drive 스트리밍 시작 시간 측정

**선행 조건:** 없음

---

## 인프라 / 마이그레이션

### BL-08: GitHub 리포지토리 마이그레이션 (우선순위: 중간)

**배경:** 현재 `ros2_video_recorder`는 개인 리포지토리. xyzcorp 조직에 `xyz-data-collector`로 새 리포 생성하여
비디오 외 다양한 데이터(joints, audio 등) 수집까지 확장 가능한 구조로 마이그레이션 필요.
"collector" = recorder + uploader 를 포괄하는 네이밍.

**작업 내용:**
- [ ] xyzcorp GitHub org에 `xyz-data-collector` 리포 생성
- [ ] 기존 코드 + history 마이그레이션
- [ ] 패키지 구조 정리 (recorder, uploader 모듈 분리)
- [ ] README, CI 세팅

**선행 조건:** 이번 주 안정화 마일스톤 (M2~M6) 완료 후 진행

---

### BL-09: Depth 토픽 녹화 히스토리 문서화 (우선순위: 낮음)

**배경:** RealSense depth 토픽 (`/camera/aligned_depth_to_color/image_raw`) 녹화를 위해
`_convert_to_bgr()` 메서드가 구현되었으나, 아직 history 문서가 작성되지 않음.

**작업 내용:**
- [ ] `docs/history/07_depth_topic_recording_*/` 히스토리 문서 작성
- [ ] 16UC1/32FC1 인코딩 처리, 99th percentile 정규화 기법 문서화

**선행 조건:** 없음

---

## 녹화 안정성

### BL-10: `.recording_` 크래시 복구 로직 (우선순위: 높음)

**배경:** recorder 프로세스가 비정상 종료되면 `.recording_XXX.mp4` + `.recording_XXX.srt` 파일이 남는다. 현재 recorder 시작 시 이 파일들을 복구하는 로직이 없음. 결과: 영원히 "녹화 중" 상태로 남아 embed/upload 파이프라인에서 무시됨.

**작업 내용:**
- [ ] recorder 시작 시 `videos/`에서 `.recording_*` 파일 검색
- [ ] 발견 시: `.recording_` prefix 제거하여 "녹화 완료" 상태로 전환 (ffmpeg moov atom 정상 여부 확인 포함)
- [ ] moov atom 없는 (ffmpeg가 정상 종료 못 한) mp4 → 경고 로그 + `.corrupted_` prefix로 이동 (파이프라인에서 배제)
- [ ] SIGTERM handler 등록 — systemd stop 시 graceful shutdown (현재 KeyboardInterrupt만 처리)

**선행 조건:** 없음. M5 (systemd) 배포 전 적용 권장.

---

### BL-11: 멀티 카메라 + joints 데이터 수집 아키텍처 리서치 (우선순위: 중간)

**배경:** 추후 gripper view, joint states, 디버깅 토픽 등 multi-source recording 필요. rosbag은 용량이 크므로 경량화 방안 리서치 필요.

**작업 내용:**
- [ ] 아키텍처 리서치: camera_recorder.py 멀티 인스턴스(각 카메라별) vs 단일 프로세스 멀티 토픽
- [ ] Joint states: `/joint_states` → Parquet 직접 기록 vs rosbag 필터링 후 변환
- [ ] rosbag 경량 대안: 선택적 토픽만 bag → 오프라인 추출 vs 실시간 Parquet 기록
- [ ] 디버깅 토픽: 항상 녹화 vs 이벤트 트리거 녹화
- [ ] Drive 폴더 구조 확장: `{product}/{branch}/{date}/` 아래 `topview_video.mp4`, `gripper_video.mp4`, `joints.parquet` 등 sidecar 배치

**선행 조건:** 현재 M2-M6 안정화 완료 + BL-05 (joint states 토픽 확보)

---

### BL-12: Drive 웹 플레이어 재생 제한 문서화 (우선순위: 낮음)

**배경:** Google Drive 웹 플레이어는 대용량(400 MB+) H.264 파일 재생 실패 케이스 있음 (야간 저조도 파일에서 관측). Drive 자체 서버사이드 트랜스코딩 한계.

**작업 내용:**
- [ ] 재생 가능 상한 파일 크기/bitrate 문서화
- [ ] 대안: VLC/mpv 로컬 스트리밍, Drive API 직접 다운로드

**선행 조건:** BL-02 해결 시 대부분 파일이 재생 가능 크기로 줄어들 것으로 예상.

---

## 범례

| 우선순위 | 의미 |
|---------|------|
| 높음 | 다음 스프린트에 포함 권장 |
| 중간 | 핵심 기능 완성 후 진행 |
| 낮음 | 필요 시 진행, 당장 급하지 않음 |
