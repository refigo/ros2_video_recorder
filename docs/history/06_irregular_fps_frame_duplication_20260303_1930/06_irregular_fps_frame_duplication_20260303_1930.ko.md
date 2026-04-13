# 불규칙 프레임 수신 시 재생 속도 보정 (프레임 복제)

Date: 2026-03-03 19:30

## 목표

무선 환경에서 불규칙하게 도착하는 카메라 프레임(~15fps)을 녹화할 때,
출력 영상의 재생 속도가 실시간과 일치하도록 보정한다.

## 배경

그리퍼 카메라 토픽(`/gripper/camera/image_raw`)은 무선 네트워크 환경에서 약 15fps로 프레임이 도착한다.

### 문제: 2배속 재생 현상

기존 코드는 수신된 프레임을 그대로 기록하면서 출력 FPS를 30으로 고정했다.
실제 10초 동안 ~150프레임만 수신되어도 영상 파일은 이를 5초 분량(150/30)으로 재생했다.

```
실시간: |----10초----|
수신:   150프레임 @ ~15fps
영상:   150프레임 / 30fps = 5초 → 2배속
```

## 해결 방법: 타임스탬프 기반 프레임 복제

`image_callback`에서 프레임을 기록할 때, 이전 프레임과의 **실제 경과 시간**을 계산하고,
출력 FPS 기준으로 빠진 프레임 수만큼 **이전 프레임을 반복 기록**하여 재생 속도를 실시간과 일치시킨다.

### 동작 예시

출력 FPS=30, 프레임 간 간격 0.1초인 경우:
- expected_frames = round(0.1 × 30) = 3
- 이전 프레임 2번 복제 + 현재 프레임 1번 기록 = 총 3프레임

```
수신:  F1 ----0.1초---- F2
출력:  F1  F1  F1  F2
       ↑   ↑복제  ↑복제  ↑현재
```

## 수정 내용

### 파일: `camera_recorder.py`

#### 1. 멤버 변수 추가 (`__init__`)

```python
self.last_frame_time = None   # 마지막 프레임 수신 시각
self.last_frame = None        # 마지막 프레임 이미지 (복제용)
```

#### 2. `_write_frame()` 헬퍼 메서드 추출

프레임 쓰기 로직(ffmpeg/opencv 분기)을 별도 메서드로 추출하여 복제 시 코드 중복 방지:

```python
def _write_frame(self, frame):
    if self.use_ffmpeg:
        self.ffmpeg_process.stdin.write(frame.tobytes())
    else:
        self.video_writer.write(frame)
```

#### 3. `image_callback` 수정

- **첫 프레임**: `last_frame_time`/`last_frame` 초기화, 1프레임만 기록
- **이후 프레임**:
  1. `elapsed = now - last_frame_time`
  2. `expected_frames = max(1, round(elapsed * self.fps))`
  3. `duplicate_count = expected_frames - 1` 만큼 이전 프레임(`last_frame`) 복제 기록
  4. 현재 프레임 1회 기록
  5. `last_frame_time`, `last_frame` 갱신

복제 프레임의 메타데이터(`frame_records`)는 보간된 시각으로 기록한다.

#### 4. `switch_segment` 수정

세그먼트 전환 시 `last_frame_time`과 `last_frame`을 `None`으로 리셋하여
세그먼트 경계에서 오차 누적을 방지한다.

## 프레임 드롭 시 동작

| 상황 | 간격 | expected_frames (FPS=30) | 복제 수 |
|------|------|------------------------|---------|
| 정상 (30fps) | 0.033s | 1 | 0 |
| 15fps 수신 | 0.067s | 2 | 1 |
| 10fps 수신 | 0.1s | 3 | 2 |
| 1초 드롭 | 1.0s | 30 | 29 |

## 검증

```bash
python3 camera_recorder.py --topic /gripper/camera/image_raw --segment 60 --fps 15
```

- 녹화 60초 후 영상 파일 재생 시간이 ~60초인지 확인
- 프레임 드롭 구간에서 영상이 멈춤(정지 프레임)으로 보이면 정상

## 선행 작업

- `05_qos_best_effort_fix`: QoS를 BEST_EFFORT로 변경하여 그리퍼 카메라 프레임 수신이 가능해진 후 본 작업 진행
