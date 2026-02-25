# Backlog

Last updated: 2026-02-25

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

### BL-02: CRF 옵션 CLI 노출 (우선순위: 낮음)

**배경:** 현재 CRF 23 하드코딩. LeRobot 기본은 CRF 30.
HuggingFace 검증에 따르면 CRF 30에서도 학습 성능 차이 없음.

**작업 내용:**
- [ ] `camera_recorder.py`에 `--crf` CLI 인자 추가 (default: 23)
- [ ] 저장 공간 vs 화질 트레이드오프 문서화

**영향:** CRF 30 적용 시 파일 크기 ~60% 절감.

**선행 조건:** 없음

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

## 범례

| 우선순위 | 의미 |
|---------|------|
| 높음 | 다음 스프린트에 포함 권장 |
| 중간 | 핵심 기능 완성 후 진행 |
| 낮음 | 필요 시 진행, 당장 급하지 않음 |
