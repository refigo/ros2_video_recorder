# M4: Cron 통합 (SRT embed + upload + verify + delete)

**날짜:** 2026-04-14
**범위:** `scripts/embed_srt.py` (신규), `scripts/upload_cron.py` (신규), `scripts/upload_cron.sh` (신규), `config/uploader.env.example`, `docs/spec/upload_spec.md`, `docs/spec/recording_spec.md`, `docs/spec/deployment_checklist.md`, `docs/management/upload_milestones.md`, `README.md`

## 목표

M2 recorder가 생성한 `.mp4`+`.srt` 쌍을 매시 cron으로 처리:
1. SRT를 MP4에 `mov_text`로 embed → 원본 교체 → `.srt` 삭제
2. Embed된 MP4를 Shared Drive에 업로드 → MD5 검증 → 로컬 삭제

한 번의 `upload_cron.sh` 실행으로 두 단계를 완결. cron이 중간에 죽어도 다음 실행에서 남은 파일부터 재개 (file-based state machine).

## 배경

M3에서 `uploader.py`의 `transcode_for_drive()`가 업로드 시점에 embed를 수행하도록 만들어놓은 상태였다. 이를 pre-embed 단계로 분리하는 이유:

- **단계 독립성**: embed 실패(bad srt, disk full)가 다른 파일의 업로드를 막지 않음.
- **재시도 효율**: 업로드 실패 시 embed된 mp4는 로컬에 남고, 다음 cron에서 embed 없이 업로드만 재시도.
- **관찰 가능성**: `ls videos/` 로 각 파일이 어느 단계인지 즉시 확인 가능.
- **향후 분리**: uploader는 "이미 처리된 파일을 단순 업로드"하는 모델로 명확해짐.

`transcode_for_drive()`는 이제 이미 H.264 + subtitle이 있는 파일에 대해 no-op pass-through. M4는 기존 uploader.py를 수정 없이 재사용.

## 파일 상태 머신

```
녹화 중     : .recording_XXX.mp4 + .recording_XXX.srt   # recorder 소유
녹화 완료   : XXX.mp4 + XXX.srt                         # embed 대상
임베딩 완료 : XXX.mp4 (subtitle track 포함, srt 삭제됨)  # upload 대상
업로드 완료 : (로컬 파일 삭제)                           # terminal
```

## 구현

### `scripts/embed_srt.py`

모듈 + CLI:

- `has_subtitle_track(mp4)` — `ffprobe -select_streams s` 로 서브타이틀 스트림 존재 여부 확인
- `cleanup_stale_tmp(dir)` — 이전 실행 크래시로 남은 `*.embedding.tmp` 정리
- `embed_one(mp4, srt)` — `ffmpeg -c:v copy -c:s mov_text -metadata:s:s:0 language=kor -movflags +faststart -f mp4 {mp4}.embedding.tmp` → `os.replace(tmp, mp4)` → `os.remove(srt)`
- `run(dir, min_age_seconds)` — 스캔, `.recording_` / stale tmp / recent 필터, per-file 실패 격리, `EmbedResult(embedded, recovered, skipped, failed)` 반환

**발견사항:** ffmpeg는 출력 확장자로 포맷을 추론하는데 `.embedding.tmp`는 인식 못 함 → `-f mp4` 명시 필요.

**복구 경로:** 이미 subtitle을 가진 mp4 + orphan `.srt`가 같이 발견되면 remux 생략하고 srt만 삭제 (replace와 srt-delete 사이에서 크래시한 상황 복구).

### `scripts/upload_cron.py`

Orchestrator. env (`GOOGLE_APPLICATION_CREDENTIALS`, `UPLOAD_ROOT_ID`, `UPLOAD_SHARED_DRIVE_ID`, `PRODUCT`, `BRANCH_ID`, `BRANCH_NAME`, `VIDEOS_DIR`) 읽어서:
1. `embed_srt.run()` 호출
2. `uploader.build_drive_service()` + `uploader.upload_session()` 호출 (delete_local=True, verify_md5=True)
3. Embed failed 또는 upload exception 발생 시 exit 1

banner/timing log를 stdout에 써서 cron mail이나 redirect로 캡처.

### `scripts/upload_cron.sh`

Cron이 호출하는 단일 진입점:
```bash
ENV_FILE=${UPLOADER_ENV_FILE:-/etc/ros2-recorder/uploader.env}
[ -f "$ENV_FILE" ] && set -a && source "$ENV_FILE" && set +a
exec /usr/bin/python3.10 scripts/upload_cron.py "$@"
```

Python은 ROS2 Humble env와 동일한 `/usr/bin/python3.10` 고정 (메모리 `project_ros2_humble_env.md` 참조).

## 검증

### Offline (`test_m4_verify.py` ad-hoc, 실행 후 삭제)

6/6 PASS:
1. Fresh embed on 2 pairs, `.recording_` 쌍 미손상 — ✅
2. Re-run is idempotent (no-op, skipped=1) — ✅
3. Partial-crash 복구 (이미 embed된 mp4 + restored srt → srt만 삭제, recovered=1) — ✅
4. Stale `.embedding.tmp` 정리 — ✅
5. Orphan srt without matching mp4 무시 — ✅
6. `upload_cron --dry-run` 로그에 `barisbrew/BB003(성수본점)/2026-04/20260414` 경로 정상 출력 — ✅

### Live E2E (dev Shared Drive)

`MGOTEST_20260414T100001+0900_topview_video.{mp4,srt}` (11 MB pair) 을 `/tmp/m4_live`로 복사 후 실행:

```
[1st run]
Embed phase done in 0.2s: {'embedded': 1, ...}
Resolved Drive folder: barisbrew/MGOTEST(테스트지점)/2026-04/20260414 → 1iZSwXW...
Uploaded: ...mp4 (id=1rhhhCP...)
Deleted local: /tmp/m4_live/...mp4
Upload phase done in 15.5s: uploaded=1
exit=0  total=15.7s

[2nd run]
Embed phase done in 0.0s: {all zeros}
No files found in session: /tmp/m4_live
exit=0  total=0.0s
```

Dev Drive 정리: `barisbrew/` 폴더 tree trash 이동.

## 학습

- `.embedding.tmp` 같이 비표준 확장자로 ffmpeg 출력 시 `-f mp4` 명시 필요
- `os.replace`는 same-filesystem에서 atomic — `/tmp` fixture와 `videos/` 모두 같은 fs이면 안전
- Embed 후 mp4 mtime은 현재시각으로 갱신됨 → 직후 재실행 시 min-age 필터에 걸려 no-op (test 2에서 min_age=0 사용)

## 선행 작업

- M3 (uploader Drive routing + dev Shared Drive live 검증)

## 후속 작업 (M5)

- crontab 실제 등록 (`1 * * * * /opt/ros2-recorder/scripts/upload_cron.sh`)
- systemd service unit for `camera_recorder.py`
- `/etc/ros2-recorder/` 배포 레이아웃 정립 + 설치 스크립트
- Log rotation (journald or logrotate)
- `flock` guard (1시간 이상 걸리는 업로드 overlap 방지 — 저위험이지만 명시적으로 차단)
