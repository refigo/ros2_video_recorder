# 자막 임베딩 + Google Drive 재생/CC 검증

Date: 2026-02-25 19:40

## 목표

H.264로 녹화된 원본 영상에 타임스탬프 자막(SRT)을 **프레임 무손상으로 임베딩**한 뒤
Google Drive에 업로드하여 브라우저 재생 + CC 자막 활성화를 검증한다.

## 배경

- 영상 원본은 추후 로봇 액션 모델 파인튜닝 등 ML 학습 데이터로 사용 예정
- 운영팀은 Google Drive에서 영상을 바로 재생하며 타임스탬프로 상황을 파악해야 함
- 이 두 요구를 **파일 1개**로 동시에 충족해야 함 (용량 2배 낭비 방지)

## 핵심 결정: 자막 트랙(mov_text)은 원본을 손상시키지 않는다

MP4 컨테이너는 멀티스트림 구조다:

```
video.mp4
├── Stream 0: Video (H.264)     ← 프레임 데이터 (학습용)
├── Stream 1: Audio (AAC)       ← 미사용
└── Stream 2: Subtitle (mov_text) ← 타임스탬프 자막 (운영 모니터링용)
```

자막은 **별도 스트림**이므로 비디오 프레임에 영향 없음.
ML 학습 시 비디오 스트림만 디코딩하면 자막 없는 원본 프레임 그대로 사용 가능.

## 구현: uploader.py 트랜스코딩 분기

업로드 전 ffprobe로 코덱 확인 → 분기 처리:

| 원본 코덱 | 동작 | ffmpeg 옵션 | 비디오 재인코딩 |
|-----------|------|------------|---------------|
| H.264 | 자막만 임베딩 | `-c:v copy -c:s mov_text -movflags +faststart` | **없음** (무손상) |
| mpeg4 (레거시) | 트랜스코딩 + 자막 | `-c:v libx264 -crf 23 -c:s mov_text -movflags +faststart` | 있음 |
| H.264 (SRT 없음) | 원본 그대로 업로드 | 처리 안 함 | 없음 |

`-c:v copy`는 비디오 스트림을 바이트 단위로 복사하므로 화질 손실이 전혀 없다.

## 검증 과정

### 1. 로컬 자막 임베딩 테스트

```bash
ffmpeg -y \
  -i seg001.mp4 \
  -i seg001_timestamps.srt \
  -c:v copy -c:s mov_text -metadata:s:s:0 language=kor \
  -movflags +faststart \
  output.mp4
```

ffprobe 결과:
```
Stream 0: video h264 (lang=und)
Stream 1: subtitle mov_text (lang=kor)
```

파일 크기: 27KB → 28KB (+1KB 자막 메타데이터만 추가)

### 2. Google Drive 업로드

```
recording_datas/baris_brew/test_branch/2026/02/25/19-20/
├── camera_recording_20260225_192909_seg001.mp4  (28,329 bytes)
├── camera_recording_20260225_192909_seg001_timestamps.csv
├── camera_recording_20260225_192909_seg002.mp4  (25,190 bytes)
├── camera_recording_20260225_192909_seg002_timestamps.csv
├── camera_recording_20260225_192909_seg003.mp4  (17,657 bytes)
└── camera_recording_20260225_192909_seg003_timestamps.csv
```

- SRT 파일은 MP4에 임베딩되었으므로 별도 업로드 제외
- CSV 파일은 ML 학습용 프레임별 메타데이터로 함께 업로드

### 3. Drive 재생 검증 결과

| 항목 | 결과 |
|------|------|
| Drive 브라우저 재생 | **O** — H.264 + yuv420p로 즉시 스트리밍 |
| CC 자막 버튼 | **O** — 활성화 시 KST 타임스탬프 표시 |
| 자막 내용 | `2026-02-25T19:29:09+0900 KST` 형식, 초 단위 갱신 |
| 파일 크기 증가 | +1~2KB (자막 메타데이터만, 무시 가능) |

## 업로드 파이프라인 동작 요약

```
녹화 (--ffmpeg, H.264)
  → videos/session_*/seg001.mp4 + seg001_timestamps.srt + seg001_timestamps.csv

업로드 (uploader.py)
  → ffprobe: codec=h264, srt 존재
  → ffmpeg -c:v copy -c:s mov_text → 임시 파일 (자막 내장)
  → Drive 업로드: MP4 (자막 내장) + CSV (메타데이터)
  → SRT는 업로드 제외 (이미 MP4에 포함)
```

## 남은 작업

- [ ] 10분 정각 정렬 세그먼트 (M2)
- [ ] 자동 업로드 데몬 (M3) — 세그먼트 완료 시 자동 trigger
- [ ] 회사 Drive로 Service Account 전환 (M5)
