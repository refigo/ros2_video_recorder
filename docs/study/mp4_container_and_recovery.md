# MP4 컨테이너 구조, moov atom, 크래시 복구

**날짜:** 2026-04-17

이 문서는 MP4 파일 포맷의 내부 구조를 설명하고, 특히 **moov atom이 없는 깨진 파일의 원인, 감지, 복구 방법**을 다룬다. 비디오 파일 포맷에 익숙하지 않은 개발자를 대상으로 한다.

---

## 1. MP4 컨테이너 구조

### 1.1 Atom (Box) 이란?

MP4 파일은 **atom** (ISO 표준에서는 **box**)이라는 블록의 연속으로 구성된다. 각 atom은:

```
┌─────────────────────────────────────┐
│  4 bytes: 크기 (size)                │
│  4 bytes: 타입 (fourcc, 예: 'moov') │
│  N bytes: 데이터 (payload)           │
└─────────────────────────────────────┘
```

**비유:** MP4 파일은 여러 개의 "상자"가 나란히 쌓인 택배 묶음이다. 각 상자에는 라벨(타입)이 붙어있고, 안에 특정 종류의 물건(데이터)이 들어있다.

### 1.2 주요 최상위 Atom

일반적인 MP4 파일의 구조:

```
MP4 파일
│
├── ftyp   ── 파일 타입 선언 ("이 파일은 MP4입니다")
│              항상 첫 번째. 재생기가 파일 포맷을 식별하는 데 사용.
│
├── mdat   ── 미디어 데이터 (Media Data)
│              실제 압축된 영상/음성 프레임이 연속으로 저장됨.
│              이 데이터만으로는 재생 불가 — 인덱스(moov)가 필요.
│
└── moov   ── 무비 메타데이터 (Movie Metadata) ← 핵심!
               mdat의 "목차". 각 프레임의 위치, 크기, 시간 정보.
               이것이 없으면 mdat는 의미 없는 바이너리 덩어리.
```

**비유로 이해하기:**

```
┌─ mdat = 도서관의 책들 ────────────────────────┐
│                                              │
│  수만 개의 프레임이 순서대로 쌓여있지만,           │
│  각 프레임이 어디서 시작하고 끝나는지,             │
│  몇 번째 초의 프레임인지 알 수 없다.             │
│  (책이 정리 안 된 채로 쌓여있는 창고)             │
└──────────────────────────────────────────────┘

┌─ moov = 도서관의 카드 카탈로그 ──────────────────┐
│                                               │
│  "프레임 1: mdat의 0x1000 위치, 크기 4523 bytes"│
│  "프레임 2: mdat의 0x21AB 위치, 크기 3891 bytes"│
│  "프레임 1은 0.000초, 프레임 2는 0.033초..."     │
│  (각 책의 위치와 분류를 기록한 카드 카탈로그)       │
└───────────────────────────────────────────────┘
```

### 1.3 moov 내부 구조

moov는 그 자체로 여러 하위 atom을 포함하는 컨테이너이다:

```
moov
├── mvhd ── 전체 영상 헤더: 총 재생 시간, 생성 시간
│
├── trak ── 트랙 (영상, 음성, 자막 각각 1개)
│   ├── tkhd ── 트랙 헤더: 해상도, 트랙 ID
│   └── mdia
│       ├── mdhd ── 미디어 헤더: timescale, 언어
│       ├── hdlr ── 핸들러: 이 트랙이 video인지 audio인지
│       └── minf
│           └── stbl ── 샘플 테이블 ← 가장 중요한 부분
│               ├── stsd ── 코덱 설정 (H.264의 SPS/PPS 등)
│               ├── stsz ── 각 프레임의 바이트 크기
│               ├── stco ── 각 청크의 mdat 내 바이트 오프셋
│               ├── stts ── 각 프레임의 타임스탬프
│               ├── ctts ── B-프레임의 표시 시점 보정값
│               └── stss ── 키프레임(I-프레임) 목록
│
└── (다른 trak들 — 음성, 자막 등)
```

**`stbl` (Sample Table)이 핵심인 이유:** 재생기가 "3분 15초 지점으로 이동"하려면:

1. `stts`에서 3분 15초에 해당하는 프레임 번호를 찾고
2. `stss`에서 그 직전의 키프레임 번호를 찾고
3. `stco`에서 해당 키프레임의 mdat 내 바이트 위치를 찾고
4. `stsz`로 그 프레임의 크기를 알아내서
5. mdat에서 해당 바이트 범위를 읽어 디코딩

이 모든 정보가 moov에 있다. **moov 없이는 단 하나의 프레임도 디코딩할 수 없다.**

---

## 2. moov atom의 위치: 기본 vs faststart

### 2.1 기본 동작: moov가 파일 끝에 위치

FFmpeg은 기본적으로 moov를 파일 끝에 쓴다:

```
인코딩 시작
    │
    ▼
┌────────┐    프레임 데이터를 mdat에 계속 추가
│  ftyp  │         │
├────────┤         ▼
│        │    인코딩 진행 중... (moov에 들어갈 정보를
│  mdat  │    메모리에 축적하면서 프레임은 mdat에 기록)
│        │         │
│ (계속  │         ▼
│  증가) │    인코딩 완료 / 정상 종료
├────────┤         │
│  moov  │    ◄────┘  close() 호출 시 moov를 한 번에 기록
└────────┘
```

**왜 끝에 쓰는가:**
- `stco` (프레임 위치)와 `stsz` (프레임 크기)는 모든 프레임을 인코딩해야 완성됨
- 인코딩 중에는 "총 몇 프레임이 나올지" 모름
- 따라서 moov는 인코딩이 끝나야만 작성 가능

### 2.2 `-movflags +faststart`: moov를 앞으로 이동

```bash
ffmpeg -i input.mp4 -movflags +faststart output.mp4
```

이 옵션은 인코딩 완료 후 **2-pass 재배치**를 수행한다:

```
Pass 1: 정상 인코딩
┌────────┐
│  ftyp  │
├────────┤
│  mdat  │
├────────┤
│  moov  │  ← 끝에 생성됨
└────────┘

Pass 2: moov를 앞으로 이동 + stco 오프셋 재계산
┌────────┐
│  ftyp  │
├────────┤
│  moov  │  ← 앞으로 이동!
├────────┤
│  mdat  │  ← stco의 모든 오프셋이 moov 크기만큼 증가
└────────┘
```

**faststart의 이점:**
- HTTP 프로그레시브 다운로드: 파일 앞부분만 받아도 재생 시작 가능
- 스트리밍 서버(CDN): 전체 파일 업로드 완료 전에 서빙 가능

**faststart는 크래시 안전성과 무관하다:**
- 인코딩 중 크래시 → Pass 2가 실행되지 않음 → moov 없음
- Pass 2 중 크래시 → 출력 파일이 부분적으로 재작성된 상태 → 더 심각한 손상 가능

---

## 3. 크래시 시나리오: moov가 없는 파일

### 3.1 어떻게 발생하는가

```
정상 종료                              비정상 종료 (크래시)
─────────                             ────────────────
                                      
프레임 기록 → 프레임 기록 → ... →       프레임 기록 → 프레임 기록 → ...
                                                │
close() 호출                                     ╳ SIGKILL / 정전 / OOM
    │                                            │
    ▼                                            ▼
moov 기록 ✅                              moov 기록 안 됨 ❌
    │                                     (메모리에만 있던 정보 소멸)
    ▼                                            │
파일 완성                                         ▼
[ftyp][mdat][moov] ✅                      [ftyp][mdat] ❌
                                           (재생 불가)
```

**moov 손실이 발생하는 상황:**
- `SIGKILL` (`kill -9`): 프로세스 즉시 종료, cleanup 코드 실행 불가
- OOM (Out of Memory): 커널이 프로세스를 강제 종료
- 정전 / 하드웨어 리셋
- 커널 패닉
- ffmpeg 프로세스의 stdin 파이프가 비정상적으로 끊김 (부모 프로세스 크래시)

### 3.2 moov가 없는 파일의 상태

```
┌────────────────────────────────────────────┐
│             깨진 MP4 파일                    │
│                                            │
│  ftyp: ✅ 정상 (파일 포맷 식별 가능)          │
│  mdat: ✅ 압축된 프레임 데이터 존재            │
│         (정상적으로 인코딩된 H.264 NAL units) │
│  moov: ❌ 없음                              │
│                                            │
│  결과: "데이터는 있지만 목차가 없는 책"         │
│  → 어떤 표준 재생기도 재생 불가                │
│  → ffprobe: "moov atom not found" 에러      │
└────────────────────────────────────────────┘
```

**중요:** mdat 내의 데이터 자체는 정상이다. H.264 NAL unit들이 올바르게 인코딩되어 있고, 순서대로 저장되어 있다. 단지 "어디서 시작하고 끝나는지" 인덱스가 없을 뿐이다.

---

## 4. moov 없는 파일 감지 방법

### 4.1 ffprobe를 이용한 감지 (권장)

```bash
# 방법 1: 에러 메시지로 감지
ffprobe -v error "suspect_file.mp4" 2>&1
# moov 없으면 출력: "[mov,mp4,...] moov atom not found"
# 정상이면: 에러 없음

# 방법 2: 종료 코드로 감지
ffprobe -v error "suspect_file.mp4" > /dev/null 2>&1
echo $?
# 0 = 정상, 1 = 에러 (moov 없음 포함)

# 방법 3: 스트림 정보 조회 시도
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,duration \
  -of default=noprint_wrappers=1 "suspect_file.mp4"
# 정상: codec_name=h264, width=640, height=480, duration=3600.0
# moov 없음: "moov atom not found" 에러 + 출력 없음
```

### 4.2 Python에서의 감지

```python
import subprocess

def has_valid_moov(mp4_path: str) -> bool:
    """moov atom이 존재하고 파일이 재생 가능한지 확인."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name",
         "-of", "default=noprint_wrappers=1", mp4_path],
        capture_output=True, text=True, timeout=10,
    )
    return result.returncode == 0 and "codec_name=" in result.stdout
```

### 4.3 바이너리 직접 스캔

moov fourcc (`6D 6F 6F 76`)를 파일 내에서 검색:

```python
import struct

def scan_top_level_atoms(path: str) -> list[str]:
    """MP4 파일의 최상위 atom 타입 목록을 반환."""
    atoms = []
    with open(path, "rb") as f:
        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            size, fourcc = struct.unpack(">I4s", header)
            fourcc = fourcc.decode("ascii", errors="replace")
            atoms.append(fourcc)
            if size == 1:  # 64-bit extended size
                ext = f.read(8)
                size = struct.unpack(">Q", ext)[0]
                f.seek(size - 16, 1)
            elif size == 0:  # atom extends to EOF
                break
            else:
                f.seek(size - 8, 1)
    return atoms

atoms = scan_top_level_atoms("suspect.mp4")
has_mdat = "mdat" in atoms
has_moov = "moov" in atoms

if has_mdat and not has_moov:
    print("크래시 파일: mdat 있지만 moov 없음")
elif has_moov and has_mdat:
    print("구조적으로 정상")
```

---

## 5. moov 없는 파일의 복구

### 5.1 복구 도구 비교

| 도구 | 원리 | 참조 파일 필요 | 신뢰도 | 자동화 가능 |
|------|------|:---:|------|:---:|
| `untrunc` | 참조 파일에서 코덱 설정 복사 + NAL unit 스캔으로 moov 재구성 | ✅ | 중~상 | ✅ |
| `ffmpeg` raw 추출 | mdat에서 raw H.264 bitstream 추출 → 재먹싱 | ❌ (수동) | 중 | ⚠️ |
| `MP4Box -add` | GPAC의 자체 프레임 스캐너로 moov 재구성 시도 | ❌ | 낮~중 | ✅ |
| 상용 도구 | GUI 기반 복구 (Stellar, Treasured 등) | 경우에 따라 | 중 | ❌ |

### 5.2 `untrunc` 사용법 (권장)

[untrunc](https://github.com/anthwlock/untrunc) (anthwlock fork, 적극 유지보수)

```bash
# 빌드 (Ubuntu)
sudo apt install libavformat-dev libavcodec-dev libavutil-dev
git clone https://github.com/anthwlock/untrunc.git
cd untrunc && make

# 복구
# reference.mp4: 같은 카메라, 같은 설정으로 정상 녹화된 파일
# broken.mp4: moov가 없는 깨진 파일
./untrunc reference.mp4 broken.mp4
# → broken_fixed.mp4 생성
```

**원리:**

```
reference.mp4                       broken.mp4
┌──────────┐                       ┌──────────┐
│ ftyp     │                       │ ftyp     │
├──────────┤                       ├──────────┤
│ mdat     │                       │ mdat     │ ← 데이터는 있다
├──────────┤                       ├──────────┤
│ moov     │ ── 코덱 설정 복사 ──►  │ (없음)   │
│ ├ stsd   │    (SPS/PPS, codec)   └──────────┘
│ ├ stsz   │
│ └ stco   │    untrunc가 broken.mp4의 mdat를
└──────────┘    바이트 단위로 스캔하면서 NAL unit
                시작점을 찾고, reference의 코덱
                설정을 이용해 새 moov를 생성

                       │
                       ▼
                 broken_fixed.mp4
                 ┌──────────┐
                 │ ftyp     │
                 ├──────────┤
                 │ moov     │ ← 재구성됨!
                 ├──────────┤
                 │ mdat     │
                 └──────────┘
```

**제한 사항:**
- 참조 파일은 깨진 파일과 **동일한 코덱, 해상도, 인코더 설정**이어야 함
- B-프레임의 표시 순서(PTS) 복원이 부정확할 수 있음
- 오디오/비디오 동기화가 약간 어긋날 수 있음
- Fragmented MP4에는 작동하지 않음

**본 프로젝트에서의 활용:** 같은 `camera_recorder.py`로 녹화한 정상 파일이 하나만 있으면 참조 파일로 사용 가능. 모든 녹화가 동일한 인코더 설정(640x480, libx264, preset medium)이므로 호환성 높음.

### 5.3 ffmpeg raw bitstream 추출 + 재먹싱

mdat의 시작 오프셋을 수동으로 찾아 raw H.264를 추출하는 방법:

```bash
# 1. mdat 시작 위치 찾기 (hex editor 또는 python)
python3 -c "
data = open('broken.mp4', 'rb').read(1000)
idx = data.find(b'mdat')
print(f'mdat fourcc at offset: {idx}')
# mdat atom의 payload는 fourcc 이후 시작
print(f'mdat payload starts at: {idx + 4}')
"

# 2. mdat payload를 raw H.264로 추출
dd if=broken.mp4 bs=1 skip=<payload_offset> of=raw.h264

# 3. raw H.264를 MP4로 재먹싱
ffmpeg -framerate 30 -i raw.h264 -c copy recovered.mp4
```

> **주의:** 이 방법은 fragile하다. mdat 시작 위치가 정확해야 하고, raw H.264에 SPS/PPS NAL이 포함되어 있어야 하며, framerate를 정확히 알아야 한다.

### 5.4 복구가 불가능한 경우

- mdat 데이터 자체가 손상된 경우 (디스크 에러, 불완전 flush)
- mdat의 시작 부분이 누락된 경우 (SPS/PPS NAL 소실)
- 인코딩 중 설정이 변경된 경우 (해상도 변경 등)

---

## 6. 예방 전략

크래시 복구보다 **크래시에도 안전한 구조**를 만드는 것이 중요하다.

### 6.1 주기적 세그먼트 분할 (현재 프로젝트 방식) ✅

```
┌─ 1시간 세그먼트 전략 ────────────────────────────────────┐
│                                                         │
│  시간 ──►                                               │
│  |── 세그먼트 1 ──|── 세그먼트 2 ──|── 세그먼트 3 ──|     │
│       close() ✅       close() ✅       기록 중...       │
│       moov 있음         moov 있음         moov 없음      │
│                                              ╳ 크래시   │
│                                                         │
│  결과: 세그먼트 1, 2 = 완전 → 세그먼트 3만 손실 (최대 1시간) │
└─────────────────────────────────────────────────────────┘
```

**장점:** 최대 데이터 손실 = 현재 세그먼트 길이 (1시간)
**현재 상태:** 본 프로젝트가 이미 사용 중 (`camera_recorder.py`의 wall-clock aligned 세그먼트)

### 6.2 SIGTERM 핸들러로 Graceful Shutdown

SIGTERM을 받으면 ffmpeg의 stdin을 닫아서 정상 종료를 유도:

```
SIGTERM 수신
    │
    ▼
ffmpeg stdin 닫기 (pipe close)
    │
    ▼
ffmpeg가 남은 프레임 flush + moov 기록
    │
    ▼
정상 종료 (moov 있음) ✅
```

```python
import signal

def _sigterm_handler(signum, frame):
    """SIGTERM 시 ffmpeg를 정상 종료시킨다."""
    if self.ffmpeg_process and self.ffmpeg_process.stdin:
        self.ffmpeg_process.stdin.close()
        self.ffmpeg_process.wait(timeout=30)
    sys.exit(0)

signal.signal(signal.SIGTERM, _sigterm_handler)
```

**중요:** SIGTERM은 graceful shutdown이 가능하지만, **SIGKILL (`kill -9`)은 방어할 수 없다.** systemd 배포 시:

```ini
[Service]
# SIGTERM으로 종료 요청 (기본값)
KillSignal=SIGTERM
# ffmpeg가 moov를 쓸 시간 확보 (30초)
TimeoutStopSec=30
```

### 6.3 Fragmented MP4 (`frag_keyframe+empty_moov`)

moov를 파일 시작에 미리 쓰고, 주기적으로 `moof` (Movie Fragment) atom을 기록하는 방식:

```
일반 MP4:
[ftyp][mdat ... 전체 데이터 ...][moov]  ← 끝에서 한 번만 기록

Fragmented MP4:
[ftyp][moov(빈)][moof][mdat][moof][mdat][moof][mdat]...
                  │           │           │
                  └─ 각 fragment가 자체 인덱스를 포함
                     크래시 시 마지막 fragment만 손실
```

```bash
ffmpeg -i input \
  -movflags frag_keyframe+empty_moov+default_base_moof \
  -frag_duration 2000000 \
  output.mp4
```

**장점:**
- 크래시 안전: 마지막 fragment (몇 초)만 손실
- moov가 파일 시작에 있으므로 스트리밍 친화적

**단점:**
- 일부 구형 재생기/편집기에서 호환성 문제
- 파일 크기가 아주 약간 증가 (moof overhead: fragment당 ~300-500 bytes)
- 긴 파일에서 seeking이 느릴 수 있음 (`sidx` atom 없으면 moof를 순차 스캔)

**현재 프로젝트에서 사용하지 않는 이유:** 세그먼트 분할 (6.1) + SIGTERM 핸들러 (6.2)로 충분한 안전성 확보. 호환성 리스크를 감수할 필요 없음. 미래에 세그먼트 길이를 매우 길게 변경하거나 SIGKILL 빈도가 높은 환경이면 재고.

### 6.4 전략 비교

| 전략 | 최대 데이터 손실 | 구현 복잡도 | 호환성 | 현재 상태 |
|------|--------------|-----------|-------|----------|
| 세그먼트 분할 | 1 세그먼트 (1시간) | 낮음 | 완벽 | ✅ 사용 중 |
| SIGTERM 핸들러 | 0 (SIGTERM 시) | 낮음 | 완벽 | ⬜ BL-10 예정 |
| Fragmented MP4 | 마지막 fragment (초 단위) | 중간 | 일부 제한 | ❌ 미사용 |
| 세그먼트 + SIGTERM | 0 (정상) / 1 세그먼트 (SIGKILL) | 낮음 | 완벽 | 🎯 목표 |

---

## 7. moov atom의 크기

### 7.1 무엇이 크기를 결정하는가

moov 크기는 **프레임 수에 비례**한다. 주요 항목:

| 항목 | 프레임당 바이트 | 설명 |
|------|:---:|------|
| `stsz` (프레임 크기) | 4 bytes | 각 프레임의 바이트 크기 기록 |
| `stco` (프레임 위치) | 4 bytes (또는 8) | 각 청크의 mdat 내 오프셋 |
| `stts` (타임스탬프) | 가변 | 프레임별 DTS (run-length 인코딩) |
| `ctts` (PTS 보정) | 가변 | B-프레임이 있을 때만 |
| `stss` (키프레임) | 가변 | 키프레임 번호 목록 |

### 7.2 실측 예상 크기

```
1시간 30fps 영상 (비디오만):
  프레임 수 = 3600초 × 30fps = 108,000 프레임
  stsz: 108,000 × 4 = ~420 KB
  stco: 108,000 × 4 = ~420 KB (또는 co64일 경우 ×8)
  stts + ctts + stss: ~200 KB

  moov 총 크기: 약 2~5 MB
```

### 7.3 파일 대비 비율

| 녹화 시간 | moov 크기 | 파일 크기 (CRF 28, 주간) | 비율 |
|-----------|----------|------------------------|------|
| 10분 | ~0.5 MB | ~30 MB | ~1.6% |
| 1시간 | ~3 MB | ~180 MB | ~1.7% |

moov overhead는 전체 파일 크기 대비 무시할 수 있는 수준이다.

---

## 8. 본 프로젝트에서의 크래시 복구 계획

### 8.1 현재 상태 (BL-10)

현재 `camera_recorder.py`는 크래시 시 `.recording_XXX.mp4` 파일이 남으며:
- 시작 시 이전 `.recording_*` 파일을 복구하는 로직 없음
- SIGTERM 핸들러 없음 (KeyboardInterrupt만 처리)

### 8.2 계획된 구현 (M5 전)

```
recorder 시작 시:
    │
    ├── videos/에서 .recording_* 파일 검색
    │
    ├── 발견 시:
    │   ├── ffprobe로 moov 존재 확인
    │   │   ├── moov 있음 → .recording_ prefix 제거 (정상 파일로 전환)
    │   │   └── moov 없음 → .corrupted_ prefix로 이동 (파이프라인 배제)
    │   └── 로그 기록
    │
    └── SIGTERM 핸들러 등록 → ffmpeg stdin 닫기 → 정상 종료

결과: SIGTERM = 데이터 손실 0, SIGKILL = 최대 1 세그먼트 손실
```

### 8.3 복구 시 untrunc 활용 가능성

`.corrupted_` 파일 (moov 없음)에 대해:
- 정상 녹화 파일이 하나라도 있으면 `untrunc`으로 복구 시도 가능
- 자동 복구는 리스크가 있으므로, 수동 복구 가이드를 제공하는 것이 적절

---

## 참고

- [`video_encoding_fundamentals.md`](video_encoding_fundamentals.md) — CRF, 야간 용량 폭증
- [`operational_gotchas.md`](operational_gotchas.md) §3 — `os.replace` atomicity, §6 — file state machine
- [`../spec/recording_spec.md`](../spec/recording_spec.md) — 세그먼트 녹화 설계
- [ISO 14496-12](https://www.iso.org/standard/68960.html) — MP4 (ISOBMFF) 공식 표준
- [untrunc (anthwlock fork)](https://github.com/anthwlock/untrunc) — moov 복구 도구
- [FFmpeg MP4 Muxer](https://ffmpeg.org/ffmpeg-formats.html#mov_002c-mp4_002c-ismv) — movflags 옵션 공식 문서
