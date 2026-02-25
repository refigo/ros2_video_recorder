# LeRobot 데이터셋 호환성 스펙

Last updated: 2026-02-25

## 목적

이 문서는 ROS2 Video Recorder의 영상 출력이 [LeRobot](https://github.com/huggingface/lerobot)
데이터셋 형식과 호환되기 위한 요구사항을 정의한다.
녹화된 영상을 추후 로봇 액션 모델 파인튜닝(Diffusion Policy, ACT 등)에
직접 활용할 수 있도록 하는 것이 목표이다.

## LeRobot 데이터셋 구조 (v3.0)

```
dataset_repo/
  meta/
    info.json              # 스키마, 코덱, fps, 해상도, 피처 정의
    stats.json             # 정규화용 통계 (mean/std/min/max)
    tasks.jsonl            # 태스크 자연어 설명
    episodes/              # 에피소드별 메타데이터 (chunked Parquet)
  data/
    chunk-{idx}/
      file-{idx}.parquet   # 상태/액션 시계열 (float32)
  videos/
    observation.images.{cam_key}/
      chunk-{idx}/
        file-{idx}.mp4     # 비디오 (여러 에피소드가 연결된 하나의 파일)
```

### info.json 비디오 피처 예시

```json
{
  "observation.images.cam_high": {
    "dtype": "video",
    "shape": [480, 640, 3],
    "names": ["height", "width", "channels"],
    "video_info": {
      "video.fps": 50.0,
      "video.codec": "av1",
      "video.pix_fmt": "yuv420p",
      "video.is_depth_map": false,
      "has_audio": false
    }
  }
}
```

## 인코딩 파라미터 비교

### 코덱

| 코덱 | LeRobot 지원 | 비고 |
|------|-------------|------|
| **AV1** (`libsvtav1`) | 기본값 | 최고 압축률, 인코딩 느림 |
| **H.264** (`libx264`) | 공식 지원 | 범용 호환, 인코딩 빠름, Drive 재생 가능 |
| **H.265** (`libx265`) | 공식 지원 | H.264보다 높은 압축률, 브라우저 지원 제한 |
| HW 가속 | 지원 | `h264_nvenc`, `h264_vaapi`, `h264_qsv` 등 |

LeRobot의 `VALID_VIDEO_CODECS`:
`h264`, `hevc`, `libsvtav1`, `auto`, `h264_videotoolbox`, `hevc_videotoolbox`,
`h264_nvenc`, `hevc_nvenc`, `h264_vaapi`, `h264_qsv`

**결정:** 녹화 단계에서는 **H.264**를 사용한다.
- Google Drive 브라우저 재생 호환 (운영 모니터링 필수 요건)
- LeRobot에서 공식 지원
- 필요 시 LeRobot 변환 단계에서 AV1로 재인코딩 가능
- 실시간 인코딩 부하가 AV1보다 낮음

### GOP (Group of Pictures) — 가장 중요한 차이

```
GOP = 2 (LeRobot)
  I B I B I B I B ...     ← 매 2프레임마다 키프레임
  → 아무 프레임이나 즉시 디코딩 가능 (최대 1프레임 추가 디코딩)

GOP = 250 (ffmpeg 기본)
  I B B B ... B I B B ...  ← 250프레임마다 키프레임
  → 특정 프레임 접근 시 최대 250프레임 디코딩 필요
```

ML 학습에서는 배치마다 랜덤 프레임에 접근하므로 GOP가 작아야 한다.
**GOP 2는 LeRobot 호환의 핵심 요구사항.**

| GOP | 랜덤 접근 속도 | 파일 크기 | 용도 |
|-----|--------------|----------|------|
| 2 | 매우 빠름 | 크다 (~30% 증가) | ML 학습용 |
| 30 | 보통 | 보통 | 스트리밍 |
| 250 | 느림 | 작다 | 아카이브 |

### CRF (Constant Rate Factor)

| CRF | PSNR | 파일 크기 비율 | 학습 성능 영향 |
|-----|------|--------------|---------------|
| 18 | ~45dB | 1x (기준) | 없음 |
| 23 | ~40dB | ~0.5x | 없음 |
| 30 | 35-40dB | ~0.2x | 없음 (HF 검증 완료) |

HuggingFace 팀이 CRF 30에서 Diffusion Policy(PushT), ACT(ALOHA) 학습 성능에
측정 가능한 차이가 없음을 검증했다.

**결정:** 현재 CRF 23 유지. 저장 공간이 이슈가 되면 CRF 30으로 전환 가능.

### 픽셀 포맷

| 포맷 | 설명 | LeRobot 지원 |
|------|------|-------------|
| **yuv420p** | 4:2:0 크로마 서브샘플링 | 기본값, 권장 |
| yuv444p | 4:4:4 풀 크로마 | AV1/HEVC에서 자동 다운그레이드 |

**현재 설정 `yuv420p` — 호환.**

### 컨테이너

MP4 (`.mp4`) — **현재 설정 호환.**
LeRobot은 연결(concatenation) 시 `movflags=faststart`를 사용한다.

## 현재 호환 상태 요약

| 항목 | LeRobot 요구 | 현재 설정 | 상태 |
|------|-------------|----------|------|
| 코덱 | AV1 (기본) / H.264 (지원) | H.264 | ✅ 호환 |
| 픽셀 포맷 | yuv420p | yuv420p | ✅ 호환 |
| 컨테이너 | .mp4 | .mp4 | ✅ 호환 |
| GOP size | 2 | 기본값 (~250) | ❌ 수정 필요 |
| CRF | 30 | 23 | ⚠️ 동작하지만 최적은 아님 |
| 해상도 | 제한 없음 | 640x360 | ✅ 호환 |
| FPS | 제한 없음 | 30 | ✅ 호환 |
| 자막 트랙 (mov_text) | 무관 (비디오 스트림만 사용) | 임베딩 | ✅ 영향 없음 |

## LeRobot 변환 시 필요한 추가 작업

녹화된 MP4를 LeRobot 데이터셋으로 변환하려면 다음이 필요하다:

1. **에피소드 분할**: 연속 녹화를 태스크 단위 에피소드로 분할
2. **상태/액션 데이터**: robot arm joints를 Parquet 형식으로 동기화 저장
3. **info.json 생성**: 피처 스키마, 통계, 에피소드 메타데이터
4. **비디오 재인코딩 (선택)**: H.264 → AV1, GOP 조정

## 참고 자료

- [LeRobot Dataset v3.0 문서](https://huggingface.co/docs/lerobot/lerobot-dataset-v3)
- [Scaling robotics datasets with video encoding (HF Blog)](https://huggingface.co/blog/video-encoding)
- [LeRobot GitHub](https://github.com/huggingface/lerobot)
- [PR #983: PyAV 인코딩 전환](https://github.com/huggingface/lerobot/pull/983)
