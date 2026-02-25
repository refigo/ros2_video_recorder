# FFmpeg H.264 녹화 수정 및 Google Drive 업로드 파이프라인

Date: 2026-02-25

## Overview

FFmpeg 백엔드의 H.264 녹화가 실제로 동작하지 않던 3가지 근본 버그를 수정하고,
Google Drive 업로드 폴더 구조를 `recording_datas/product/branch_id/YYYY/MM/DD/HH-mm/`
형식으로 변경하여 운영 모니터링 + ML 학습 데이터 수집을 하나의 파이프라인으로 통합했다.

## 발견된 버그와 해결

### Bug 1: FFmpeg stderr 버퍼 데드락 (`camera_recorder.py`)

**증상:** 녹화 후 파일이 262 bytes (빈 MP4 헤더만 존재).

**원인:** `subprocess.Popen`에서 `stderr=subprocess.PIPE`로 설정하면 ffmpeg의 인코딩
로그가 파이프 버퍼(기본 64KB)에 쌓인다. 버퍼가 가득 차면 ffmpeg 프로세스가
stderr write에서 블로킹되어 stdin read도 멈춘다. 결과적으로 프레임 데이터가
ffmpeg에 전달되지 못하고, 빈 파일이 생성된다.

**해결:** `stderr=subprocess.DEVNULL`로 변경. ffmpeg 에러 로그가 필요한 경우
별도 로그 파일로 리다이렉트하는 것이 안전하다.

```python
# Before (데드락 발생)
subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)

# After (안전)
subprocess.Popen(cmd, stdin=PIPE, stdout=DEVNULL, stderr=DEVNULL)
```

**배경 지식 — subprocess PIPE 데드락:**
Python `subprocess.PIPE`는 OS 파이프 버퍼 크기에 의존한다 (Linux 기본 64KB).
자식 프로세스가 stdout/stderr에 쓸 때 버퍼가 가득 차면 자식이 블로킹되고,
부모가 read하지 않으면 교착상태에 빠진다. `communicate()`를 쓰거나
`DEVNULL`로 무시하는 것이 표준 해법이다.

---

### Bug 2: Writer Thread 즉시 종료 (`camera_recorder.py`)

**증상:** 위와 동일 (262 bytes 파일).

**원인:** `initialize_recording()`에서 `initialize_ffmpeg()` 호출 시 writer thread가
시작되는데, 이 시점에서 `self.recording = False`이다. Thread의 루프 조건이
`while self.recording or not self.frame_queue.empty()`이므로,
`recording=False` + 빈 큐 → thread가 **즉시 종료**.

```python
# Before (thread가 즉시 종료)
def initialize_recording(self, first_frame):
    self.initialize_ffmpeg()      # thread 시작 → 즉시 종료
    self.recording = True          # 이미 늦음

# After
def initialize_recording(self, first_frame):
    self.recording = True          # 먼저 플래그 설정
    self.initialize_ffmpeg()       # thread 시작 → 루프 유지
```

---

### Bug 3: Queue + Thread 아키텍처의 경쟁 조건

**증상:** 세그먼트 전환 시 두 번째 세그먼트 이후 빈 파일 생성.

**원인:** `image_callback` → `frame_queue.put()` → writer thread → `ffmpeg.stdin.write()`
구조에서, 세그먼트 전환(`switch_segment`) 시 writer thread 종료 → 새 thread 시작
과정에서 큐의 프레임이 유실되거나, thread join과 stdin close의 순서 문제로
ffmpeg가 finalize되지 않는다.

**해결:** Queue + Thread 패턴을 제거하고, `image_callback`에서 직접
`ffmpeg.stdin.write()`를 호출하는 방식으로 단순화.
ROS callback은 이미 `writer_lock` 안에서 실행되므로 thread-safe하다.

```python
# Before: callback → queue → thread → ffmpeg (경쟁 조건)
self.frame_queue.put(cv_image)

# After: callback → ffmpeg (직접 쓰기, 단순하고 안전)
self.ffmpeg_process.stdin.write(cv_image.tobytes())
```

## FFmpeg 녹화 설정 변경

```
ffmpeg -y -f rawvideo -vcodec rawvideo -s 640x360 -pix_fmt bgr24 -r 30 -i -
       -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p output.mp4
```

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| `-c:v libx264` | H.264 인코더 | Google Drive / 브라우저 재생 호환 |
| `-preset medium` | 인코딩 속도/압축 트레이드오프 | `ultrafast`~`veryslow` 범위 |
| `-crf 23` | 품질 (0=무손실, 51=최저) | 23은 시각적으로 무손실에 가까움 |
| `-pix_fmt yuv420p` | 색 공간 | 브라우저/Drive 재생 필수 조건 |

## Google Drive 업로드 변경

### 폴더 구조 변경

```
# Before
robot_<id>/YYYY/MM/DD/shift_operator_HHMMSS/

# After
recording_datas/<product>/<branch_id>/YYYY/MM/DD/HH-mm/
```

- `product`: 서비스명 (env: `PRODUCT_NAME`, default: `baris_brew`)
- `branch_id`: 지점 식별자 (env: `BRANCH_ID`, default: `test_branch`)
- `HH-mm`: 10분 정각 정렬 (예: 17:18 → `17-10`)

### 트랜스코딩 분기 (uploader.py)

업로드 시 MP4 코덱을 확인하여 분기 처리:
- **H.264** → 자막 임베딩만 (`-c:v copy` + `-c:s mov_text`) — 영상 재인코딩 없음
- **mpeg4(mp4v)** → H.264 트랜스코딩 + 자막 임베딩 — 레거시 파일 호환

## 검증 결과

| 테스트 | 결과 |
|--------|------|
| 5초 단일 녹화 (ffmpeg H.264) | 31KB, codec=h264, 4.7s |
| 3초×3 세그먼트 녹화 | 모두 h264, 정상 전환, 메타데이터 생성 |
| 세그먼트 전환 소요 시간 | ~60ms (기존 ~5s에서 개선) |
| OAuth 토큰 갱신 + Drive 업로드 | 10개 파일 업로드 성공 |

---

## 배경 지식: 영상 코덱과 Google Drive 재생

### 코덱이란?

코덱(Codec = Coder + Decoder)은 영상 데이터를 압축(인코딩)하고 복원(디코딩)하는
알고리즘이다. 같은 `.mp4` 파일이라도 내부 코덱이 다르면 재생 호환성이 달라진다.

### H.264 (AVC) — 왜 이것을 쓰는가?

H.264는 현재 가장 널리 지원되는 비디오 코덱이다:
- 모든 브라우저 (Chrome, Firefox, Safari, Edge)에서 네이티브 재생
- Google Drive, YouTube, 대부분의 온라인 플랫폼 지원
- 하드웨어 디코딩 지원 (GPU 가속)
- 높은 압축률 대비 우수한 화질

비교:
| 코덱 | 컨테이너 | 브라우저 재생 | Drive 재생 | 압축률 |
|------|---------|-------------|-----------|--------|
| MPEG-4 Part 2 (mp4v) | .mp4 | X | X | 낮음 |
| **H.264 (AVC)** | .mp4 | O | O | 높음 |
| H.265 (HEVC) | .mp4 | 부분 | 부분 | 매우 높음 |
| VP9 | .webm | O | O | 높음 |
| AV1 | .mp4/.webm | 부분 | 부분 | 최고 |

### CRF (Constant Rate Factor)

CRF는 H.264의 품질 제어 파라미터다:
- **0**: 수학적 무손실 (파일 매우 큼)
- **18**: 시각적 무손실 (육안으로 원본과 구분 불가)
- **23**: 기본값 (좋은 품질, 합리적 파일 크기) ← 현재 설정
- **28**: 약간의 품질 저하, 파일 크기 작음
- **51**: 최저 품질

ML 학습 데이터로 사용할 경우 CRF 18~23이 적절하다. CRF가 낮을수록
프레임의 디테일이 보존되어 모델 학습에 유리하지만 저장 공간이 증가한다.

### Pixel Format: yuv420p

- `bgr24`: OpenCV/카메라의 기본 포맷 (Blue-Green-Red, 픽셀당 24bit)
- `yuv420p`: 브라우저/Drive 재생에 필요한 표준 포맷
  - Y(밝기) 풀 해상도, U/V(색차) 1/4 해상도 → 인간 시각에 최적화된 압축
  - H.264 + yuv420p 조합이 웹 재생의 사실상 표준

### faststart vs 일반 MP4

MP4 파일에는 `moov` atom(메타데이터)이 있다:
- **일반**: moov가 파일 끝에 위치 → 전체 다운로드 후 재생 가능
- **faststart**: moov를 파일 앞으로 이동 → 스트리밍 즉시 재생 가능

`-movflags +faststart`는 파일 완성 후 moov를 앞으로 재배치하는 후처리를 수행한다.
**주의**: stdin 파이프 입력에서는 사용 불가 (seek 불가). 업로드 전 트랜스코딩 단계에서만 적용.

### 자막 트랙 (mov_text)

MP4 컨테이너는 여러 스트림을 담을 수 있다:
- Stream 0: 비디오 (H.264)
- Stream 1: 오디오 (AAC) — 현재 미사용
- Stream 2: 자막 (mov_text) ← SRT를 임베딩

`mov_text`는 MP4의 표준 자막 포맷으로, 영상 프레임 데이터에 영향을 주지 않는다.
별도 스트림이므로 ML 학습 시 비디오 스트림만 읽으면 원본 프레임 그대로 사용 가능하다.

```bash
# 자막 임베딩 (비디오 재인코딩 없이)
ffmpeg -i video.mp4 -i timestamps.srt -c:v copy -c:s mov_text output.mp4

# 자막 추출
ffmpeg -i output.mp4 -map 0:s:0 extracted.srt
```
