# 녹화 최적화 스터디

**날짜:** 2026-04-13

---

## 1. FFmpeg preset과 파일 크기/CPU 부하 관계

### 목표

FFmpeg `-preset` 옵션이 CPU 사용량과 파일 크기에 어떤 영향을 미치는지 이해하고, 본 프로젝트에 적합한 preset을 선정한다.

### 현재 동작

현재 `initialize_ffmpeg()`에서 `-preset medium`을 사용하고 있다.

```
ffmpeg ... -c:v libx264 -preset medium -crf 23 ...
```

### H.264 인코딩 원리 (간략)

H.264 인코더는 영상 데이터에서 **중복(redundancy)**을 찾아 제거함으로써 파일 크기를 줄인다. 주요 기법:

```
┌─────────────────────────────────────────────────────┐
│              H.264 압축 파이프라인                     │
│                                                     │
│  원본 프레임                                          │
│      │                                              │
│      ▼                                              │
│  ┌──────────────────┐                               │
│  │ 모션 추정         │ ← 이전 프레임과 비교해서         │
│  │ (Motion Est.)    │   움직임 벡터를 찾음             │
│  └──────┬───────────┘                               │
│         ▼                                           │
│  ┌──────────────────┐                               │
│  │ 참조 프레임 탐색   │ ← 여러 과거 프레임에서           │
│  │ (Ref. Frames)    │   가장 비슷한 블록을 찾음        │
│  └──────┬───────────┘                               │
│         ▼                                           │
│  ┌──────────────────┐                               │
│  │ 잔차 변환 + 양자화 │ ← 남은 차이만 저장              │
│  │ (Transform+Quant)│                               │
│  └──────┬───────────┘                               │
│         ▼                                           │
│  ┌──────────────────┐                               │
│  │ 엔트로피 코딩      │ ← 허프만/CABAC으로 비트 압축    │
│  └──────────────────┘                               │
│                                                     │
│  preset이 결정하는 것: 각 단계에서 "얼마나 열심히 찾는가" │
└─────────────────────────────────────────────────────┘
```

**비유:** 이사할 때 짐을 박스에 넣는 것과 비슷하다.
- `ultrafast` = 물건을 대충 큰 박스에 넣음 → 빨리 끝나지만 박스를 많이 씀
- `medium` = 크기별로 분류해서 효율적으로 넣음 → 시간이 더 걸리지만 박스 수가 줄어듦
- `slow` = 테트리스처럼 빈틈 없이 넣음 → 매우 느리지만 박스 최소화

### 최적화 방안

preset별 대략적인 CPU/파일 크기 비교 (1080p 30fps, CRF 23 기준):

| preset     | 인코딩 속도 | CPU 사용률 | 파일 크기 (상대) | 비고                     |
|------------|-----------|-----------|----------------|--------------------------|
| ultrafast  | ~240 fps  | 낮음       | 1.0x (기준)     | 압축 최소, 파일 가장 큼      |
| fast       | ~100 fps  | 중간       | ~0.6x          | 적당한 균형점              |
| medium     | ~60 fps   | 높음       | ~0.5x          | FFmpeg 기본값             |
| slow       | ~30 fps   | 매우 높음   | ~0.45x         | 실시간 인코딩 한계          |

> **주의:** 위 수치는 하드웨어와 영상 내용에 따라 크게 달라질 수 있다. 방향성 참고용이다.

**핵심 트레이드오프:**

```
CPU 부하 ◄────────────────────────────► 파일 크기
  낮음     ultrafast  fast  medium  slow     작음
  높음                                       큼
```

### 리스크

- `ultrafast`는 파일 크기가 medium 대비 약 2배 → 디스크 I/O 부하 증가 가능
- `slow` 이상은 실시간 인코딩이 불가능할 수 있음 (30fps 입력을 처리 못함)
- CRF 값은 동일하므로 **화질은 preset과 무관**하다. preset은 "같은 화질을 얼마나 적은 비트로 표현하는가"만 결정함

### 적용 시점

본 프로젝트에서는 **녹화 안정성**이 파일 크기보다 중요하다. 파일은 Google Drive에 업로드 후 로컬에서 삭제된다. 따라서:

- **권장:** `-preset ultrafast` 또는 `-preset fast`
- 디스크 공간이 충분하면 `ultrafast`로 CPU 여유를 최대한 확보
- 디스크 공간이 빠듯하면 `fast`로 타협

---

## 2. tobytes() 제거와 zero-copy (memoryview)

### 목표

프레임 데이터를 FFmpeg stdin에 전달할 때 불필요한 메모리 복사를 제거하여 CPU 및 메모리 대역폭을 절약한다.

### 현재 동작

```python
# _write_frame() 및 ffmpeg_writer_thread() 에서:
self.ffmpeg_process.stdin.write(frame.tobytes())
```

`frame.tobytes()`는 numpy 배열 전체를 새로운 `bytes` 객체로 **복사**한다.

```
┌─────────────────────┐       tobytes()       ┌─────────────────────┐
│  numpy array (6MB)  │ ─────복사(copy)──────► │  bytes object (6MB) │
│  (원본 프레임 데이터)  │                        │  (새로 할당된 메모리)  │
└─────────────────────┘                        └──────────┬──────────┘
                                                          │
                                                    write()
                                                          │
                                                          ▼
                                                ┌─────────────────┐
                                                │  FFmpeg stdin    │
                                                │  (pipe)          │
                                                └─────────────────┘
```

**문제 규모 계산:**
- 1080p BGR 프레임: `1920 x 1080 x 3 = 6,220,800 bytes` (~6MB)
- 30fps 기준: `6MB x 30 = ~180MB/초`의 불필요한 메모리 복사 발생

### 최적화 방안

Python의 buffer protocol을 활용하여 복사 없이(zero-copy) 직접 전달:

```python
# 방법 1: memoryview 사용
self.ffmpeg_process.stdin.write(memoryview(frame))

# 방법 2: numpy의 내부 버퍼 직접 사용
self.ffmpeg_process.stdin.write(frame.data)
```

```
┌─────────────────────┐     memoryview (참조만 전달)
│  numpy array (6MB)  │ ─────────────────────────────► FFmpeg stdin
│  (원본 프레임 데이터)  │     복사 없음! 원본 메모리를       (pipe)
└─────────────────────┘     그대로 읽어감
```

**비유:** 친구에게 정보를 전달할 때:
- `tobytes()` = 책 전체를 복사기로 복사해서 복사본을 건네줌 (시간과 종이 소모)
- `memoryview` = 원본 책을 그대로 보여줌 (복사 없음, 즉시 전달)

### 리스크

| 리스크 | 설명 | 현재 프로젝트 상태 |
|--------|------|-------------------|
| C-contiguous 요구 | `memoryview`는 메모리가 연속적이어야 함. 슬라이스나 전치된 배열은 불가 | `cv_bridge.imgmsg_to_cv2()`는 C-contiguous 배열을 반환하므로 **안전** |
| Race condition | 쓰는 도중 프레임이 수정되면 데이터 손상 | 현재 아키텍처에서 write 후 프레임을 수정하지 않으므로 **안전** |
| 파이프 호환성 | 일부 file object가 memoryview를 거부할 수 있음 | CPython의 `subprocess.Popen` stdin pipe는 memoryview를 지원함. **안전** |

**안전장치 코드 (필요시):**

```python
def _write_frame(self, frame):
    if self.use_ffmpeg and self.ffmpeg_process and self.ffmpeg_process.stdin:
        try:
            # C-contiguous 여부 확인
            if frame.flags['C_CONTIGUOUS']:
                self.ffmpeg_process.stdin.write(frame.data)
            else:
                # fallback: 연속 배열로 변환 후 전달
                contiguous = np.ascontiguousarray(frame)
                self.ffmpeg_process.stdin.write(contiguous.data)
        except (OSError, BrokenPipeError):
            pass
```

### 적용 시점

- **즉시 적용 가능** (리스크 낮음)
- 단, 적용 전 `frame.flags['C_CONTIGUOUS']`가 항상 True인지 로그로 확인하면 더 안전
- 1080p 30fps 기준 **초당 ~180MB의 메모리 복사를 절약** → GC 부담 감소, CPU 캐시 효율 향상

---

## 3. Passthrough encoding (rgb8 -> FFmpeg rgb24)

### 목표

ROS 카메라 토픽의 이미지 인코딩이 `rgb8`인 경우, 불필요한 RGB->BGR 채널 변환을 건너뛰고 FFmpeg에 `rgb24`로 직접 전달한다.

### 현재 동작

```
RealSense 카메라              cv_bridge              FFmpeg
┌──────────┐           ┌──────────────────┐     ┌──────────────┐
│ rgb8     │ ────────► │ imgmsg_to_cv2()  │ ──► │ -pix_fmt     │
│ (R,G,B)  │           │ 'bgr8' 지정       │     │  bgr24       │
└──────────┘           │                  │     └──────────────┘
                       │ R↔B 채널 스왑 발생! │
                       │ 모든 픽셀에 대해     │
                       └──────────────────┘
```

`imgmsg_to_cv2(msg, 'bgr8')`는 입력이 `rgb8`이면 모든 픽셀의 R과 B 채널을 교환한다:

```
각 픽셀: [R, G, B] → [B, G, R]

1080p 기준: 1920 x 1080 = 2,073,600 픽셀
매 프레임마다 ~200만 픽셀의 채널 스왑 발생
```

### 최적화 방안

RGB 데이터를 변환 없이 FFmpeg에 직접 전달:

```
RealSense 카메라                                FFmpeg
┌──────────┐         변환 없이 직접 전달          ┌──────────────┐
│ rgb8     │ ──────────────────────────────────► │ -pix_fmt     │
│ (R,G,B)  │         채널 스왑 없음!              │  rgb24       │
└──────────┘                                    └──────────────┘
```

**구현 예시:**

```python
def _convert_frame(self, msg):
    encoding = msg.encoding

    # Depth 이미지는 기존 로직 유지
    if encoding in ('16UC1', '32FC1'):
        return self._convert_depth_to_bgr(msg), 'bgr24'

    # FFmpeg 사용 시 rgb8은 변환 없이 passthrough
    if self.use_ffmpeg and encoding == 'rgb8':
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        return frame, 'rgb24'

    # 그 외: 기존 BGR 변환
    return self.bridge.imgmsg_to_cv2(msg, 'bgr8'), 'bgr24'
```

FFmpeg 초기화 시 `pix_fmt`를 동적으로 설정:

```python
def initialize_ffmpeg(self, pix_fmt='bgr24'):
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-f', 'rawvideo', '-vcodec', 'rawvideo',
        '-s', f'{self.width}x{self.height}',
        '-pix_fmt', pix_fmt,    # ← 동적으로 설정
        '-r', str(self.fps),
        '-i', '-',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '23',
        '-pix_fmt', 'yuv420p',
        self.output_file
    ]
```

### 리스크

| 리스크 | 설명 | 대응 방안 |
|--------|------|----------|
| 카메라별 인코딩 차이 | RealSense는 `rgb8`이지만 다른 카메라는 `bgr8`일 수 있음 | `msg.encoding`을 확인하여 조건 분기 |
| OpenCV 처리 필요 시 | BGR을 가정하는 OpenCV 함수가 있으면 색상이 뒤바뀜 | 현재 코드에서는 OpenCV 처리 없음. **안전** |
| 프레임 복제 혼합 | `last_frame`이 rgb인데 새 프레임이 bgr이면 색상 깨짐 | 파이프라인 전체에서 인코딩을 일관되게 유지 |
| 세그먼트 전환 | 세그먼트마다 다른 pix_fmt가 사용되면 FFmpeg 초기화가 달라져야 함 | 첫 프레임에서 결정한 pix_fmt를 세션 전체에 적용 |

### 적용 시점

- 실제 RealSense 토픽의 `msg.encoding` 값을 먼저 확인해야 함
- `rgb8`이 확인되면 적용 가능
- 현재 코드에서 OpenCV 프레임 처리가 없으므로 **리스크 낮음**
- 단, depth 이미지 처리 등 BGR을 가정하는 경로가 있으므로 조건 분기 필수

---

## 전체 최적화 요약

| # | 최적화 항목 | 예상 효과 | 리스크 수준 | 적용 난이도 | 우선순위 |
|---|-----------|----------|-----------|-----------|---------|
| 1 | preset `ultrafast` 적용 | CPU 부하 대폭 감소, 파일 크기 ~2배 증가 | 낮음 | 매우 쉬움 (한 줄 변경) | 높음 |
| 2 | `tobytes()` 제거 (zero-copy) | 초당 ~180MB 메모리 복사 절약 | 낮음 | 쉬움 | 높음 |
| 3 | RGB passthrough | 프레임당 ~200만 픽셀 채널 스왑 제거 | 중간 | 보통 (조건 분기 필요) | 중간 |

**적용 권장 순서:** 1 → 2 → 3 (리스크 낮은 것부터, 효과 큰 것부터)
