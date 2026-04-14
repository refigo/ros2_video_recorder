# M2: 파일 네이밍 컨벤션 + Wall-clock 1시간 정각 세그먼트 + SRT Crash Safety

Date: 2026-04-14 09:00

## 목표

M2 마일스톤 (`docs/management/upload_milestones.md`) 구현:

1. 파일 네이밍 컨벤션 확립: `{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.{mp4,srt}`
2. `--video-label` CLI 인자 (default: `topview_video`)
3. Wall-clock aligned 1시간 세그먼트 (매시 `:00` 전환)
4. `.recording_` prefix → rename 파이프라인 (M4 cron 준비)
5. SRT 실시간 append (crash safety)
6. CSV timestamps 제거 (SRT로 일원화)

## 배경

기존 녹화기는 "시작 시점 기준 duration"으로 세그먼트를 자르고, SRT/CSV를 메모리 누적 후 세그먼트 종료 시 일괄 작성했다. 이 방식은:

- **크래시 시 데이터 유실**: PC 갑작스런 종료 시 `frame_records` 메모리 내용이 디스크에 쓰여지지 않음
- **후속 파이프라인 신호 없음**: 세그먼트 완료 여부를 파일 시스템만 보고 판별할 수 없음 (M4 cron 도입에 장애)
- **불규칙 시작 시각**: 14:23 시작 → 15:23, 16:23... 같은 분초에 계속 분할되어 후속 업로드 시각 정렬이 어려움

M3~M6 파이프라인(cron 임베딩+업로드, systemd 배포)의 전제 조건으로 M2가 필요.

## 설계 결정

### 1. File-based state machine

```
녹화 중:     .recording_XXX.mp4 + .recording_XXX.srt
녹화 완료:   XXX.mp4 + XXX.srt           ← M4 임베딩 대상
임베딩 완료: XXX.mp4 (srt 삭제됨)         ← M4 업로드 대상
업로드 완료: (파일 삭제됨)
```

파일 prefix/존재 여부가 곧 파이프라인 단계. cron 중간 실패 시 다음 실행에서 자연 복구.

### 2. Wall-clock 정각 정렬

`start_segment_timer`에서 `_seconds_until_next_boundary()` 계산:

- `segment_duration` 명시: 고정 duration (테스트용, `--segment 2`)
- 미명시: `3600 - (minute*60 + second)` = 다음 `:00`까지 초

첫 세그먼트는 짧을 수 있음 (14:23 시작 → 14:23~15:00 = 37분 세그먼트 → 이후 15:00~16:00 정각 정렬).

### 3. SRT 실시간 append

`frame_records` 메모리 누적 제거. 대신 `_update_srt(now)`를 프레임마다 호출:

- 매 초 경계를 넘을 때마다 이전 엔트리를 파일에 flush (`_flush_srt_entry`)
- `self.srt_file.flush()` → 크래시 직전까지의 엔트리는 디스크에 안전
- 세그먼트 종료 시 `_close_srt_file()` → 마지막 pending 엔트리 flush + `.recording_` prefix 제거

### 4. 네이밍 컨벤션

```
{BRANCH_ID}_{YYYYMMDD}T{HHMMSS}+0900_{video_label}.mp4
예: MGOTEST_20260413T200000+0900_topview_video.mp4
```

- `BRANCH_ID`: 지점 식별자 (e.g., `BB003`, `MGOTEST`)
- `YYYYMMDD`: 날짜 (KST)
- `HHMMSS+0900`: 시각 + UTC offset (KST 명시)
- `video_label`: 카메라 역할 — `topview_video`, `gripper_video` 등. 다중 카메라 시 각 인스턴스가 다른 label 사용

## 수정 내용

### 파일: `camera_recorder.py`

#### 1. CLI args 추가/변경

```python
parser.add_argument('--branch-id', required=True)
parser.add_argument('--video-label', default='topview_video')
# 제거: --segment-preset
# 변경: --output → --output-dir (디렉토리만 받음)
```

#### 2. 파일 네이밍 헬퍼

```python
def _generate_paths(self, timestamp):
    name = f"{self.branch_id}_{timestamp.strftime('%Y%m%dT%H%M%S')}+0900_{self.video_label}"
    return (
        os.path.join(self.output_dir, f"{name}.mp4"),
        os.path.join(self.output_dir, f"{name}.srt"),
    )

@staticmethod
def _recording_path(final_path):
    d = os.path.dirname(final_path)
    return os.path.join(d, f".recording_{os.path.basename(final_path)}")
```

`initialize_ffmpeg()` / `initialize_opencv()`가 `self._recording_path(self.output_file)`로 작성.
`switch_segment()` / `stop_recording()`에서 `_rename_recording_to_final()` 호출.

#### 3. Wall-clock 타이머

```python
def _seconds_until_next_boundary(self):
    if self.segment_duration:
        return self.segment_duration
    now = datetime.now(self.timezone)
    return 3600 - (now.minute * 60 + now.second)
```

#### 4. SRT 실시간 기록

- `_open_srt_file()`: 세그먼트 시작 시 `.recording_*.srt` open
- `_update_srt(now)`: `image_callback`에서 프레임마다 호출
- `_flush_srt_entry(end_delta)`: 초 경계 넘을 때마다 디스크 flush
- `_close_srt_file()`: 세그먼트 종료 시 마지막 엔트리 flush + rename

#### 5. 제거 항목

- `import csv`
- `self.frame_records = []` 및 모든 append 호출
- `_write_segment_metadata()` 메서드 전체 (CSV + bulk SRT 로직)

## 검증

### 단위 테스트

구현 중 `test_m2_verify.py` 스크립트로 7개 테스트 수행 (커밋 시 삭제됨):

- 파일 네이밍 (4개)
- `.recording_` prefix 처리 (2개)
- Wall-clock boundary 계산 (4개)
- SRT crash safety (8개): close 전에도 flush된 엔트리 존재 확인
- CSV 제거 (4개)
- ffmpeg 풀 플로우 + ffprobe 확인 (13개)
- 세그먼트 전환 (9개)

**결과: 44/44 통과**

### E2E 실제 녹화 검증

```bash
python3.10 camera_recorder.py --branch-id MGOTEST --ffmpeg
```

RealSense RGB 토픽으로 약 하루 연속 녹화. `videos/` 결과:

```
MGOTEST_20260413T192003+0900_topview_video.mp4  (첫 세그먼트, 짧음)
MGOTEST_20260413T200000+0900_topview_video.mp4  (정각 정렬 시작)
MGOTEST_20260413T210000+0900_topview_video.mp4
MGOTEST_20260413T220000+0900_topview_video.mp4
MGOTEST_20260413T230000+0900_topview_video.mp4
MGOTEST_20260414T000001+0900_topview_video.mp4  (날짜 경계 통과)
MGOTEST_20260414T010000+0900_topview_video.mp4
...
```

확인 사항:
- [x] 파일명이 네이밍 컨벤션 일치
- [x] 정각 (`:00:00`)에 세그먼트 전환 — `00:00:01`은 타이머 미세 지연 (허용 범위)
- [x] `.recording_` 파일이 세그먼트 종료 시 사라짐 (rename 완료)
- [x] SRT 파일이 MP4와 쌍으로 존재
- [x] CSV 파일 없음
- [x] 날짜 변경 경계 (23시 → 00시) 정상 동작

## 환경 이슈 (발견)

실행 환경 검증 중 Python/NumPy 버전 호환성 이슈 발견:

- ROS2 Humble은 Python 3.10 + NumPy 1.x 필수
- uv로 설치된 Python 3.12가 `python3` 기본값이 되면서 `ModuleNotFoundError: No module named 'rclpy._rclpy_pybind11'` 발생
- NumPy 2.x 설치된 상태에서 `cv_bridge` 로드 시 `_ARRAY_API not found` 세그폴트

상세는 `docs/study/ros2_humble_env_setup.md` 참조.

## 선행 작업

- `06_irregular_fps_frame_duplication`: frame duplication 로직. SRT 실시간 기록으로 전환하면서 `frame_records` 메모리 누적 제거, 대신 `_update_srt`가 보간된 시각 대신 실제 수신 시각(`now`)으로 SRT 엔트리 작성.

## 후속 작업 (M3~M6)

- M3: 업로드 디렉토리 `barisbrew-recorded-datas/{BRANCH_ID}({BRANCH_NAME})/{YYYY-MM}/{YYYYMMDD}/` 구조 변경 + Shared Drive 검증
- M4: cron (`:01`)에서 `.srt` 있는 `.mp4` → ffmpeg remux → 업로드 → MD5 verify → 삭제
- M5: systemd 서비스 + crontab 배포
- M6: 24h 무중단 E2E 검증
