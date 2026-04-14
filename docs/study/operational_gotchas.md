# Operational Gotchas & Lessons Learned

Last updated: 2026-04-14

이 문서는 녹화/업로드 파이프라인 구축 과정에서 마주친 **비직관적인 제약과 하드웨어/플랫폼 특성**을 모아둡니다. 새로운 개발자가 환경을 세팅하거나, 기능을 수정하거나, 배포 문제를 디버깅할 때 먼저 훑어볼 참고서.

각 항목은 **사실 → 왜 중요한가 → 어떻게 대응하는가** 구조.

---

## 1. Python / NumPy 버전 고정 (ROS2 Humble)

**사실:** ROS2 Humble의 `rclpy`, `cv_bridge`는 **Python 3.10 + NumPy 1.x 전용 C 확장**으로 빌드되어 있다. Python 3.11/3.12나 NumPy 2.x에서 import 시 즉시 실패하거나 segfault.

**왜 중요:** 대부분의 현대 Python 툴체인(uv, conda, pyenv)이 기본 Python을 3.11+ 로 잡아놓는다. 무심코 `pip install numpy` 하면 2.x가 설치되면서 다음 실행 때 `cv_bridge.imgmsg_to_cv2` 가 segfault.

**대응:**
- recorder 실행은 항상 `/usr/bin/python3.10` 절대경로로
- `/usr/bin/python3.10 -m pip install --user 'numpy<2'` 로 고정
- 자세한 가이드: [`docs/study/ros2_humble_env_setup.md`](ros2_humble_env_setup.md)

---

## 2. FFmpeg: `.embedding.tmp` 확장자에는 `-f mp4` 필수

**사실:** ffmpeg는 출력 파일의 확장자로 포맷을 추론한다. `.embedding.tmp` 같은 비표준 확장자는 인식 못 해서 `Unable to find a suitable output format` 에러로 실패.

**왜 중요:** M4 embed 로직은 atomic replace를 위해 `{name}.mp4.embedding.tmp`로 먼저 쓰고 성공 시 원본으로 교체한다. 이때 `-f mp4`를 명시하지 않으면 실패.

**대응:** `scripts/embed_srt.py`의 ffmpeg 명령에 `-f mp4` 포함되어 있음. 비슷한 atomic 패턴을 다른 곳에 추가할 때 잊지 말 것.

---

## 3. `os.replace` atomicity는 same-filesystem 전용

**사실:** POSIX 상에서 atomic rename은 같은 파일시스템 내에서만 보장된다. `/var/lib/ros2-recorder/videos/` 와 `/tmp/...` 가 다른 마운트에 있다면 `os.replace()`가 실패하거나 non-atomic fallback (copy+unlink) 동작.

**왜 중요:** M4 embed는 `.embedding.tmp`를 원본과 **같은 디렉토리에** 생성하므로 OK. 하지만 M5에서 systemd 배포 시 `/tmp`나 다른 볼륨을 임시 작업 경로로 쓰면 안 됨.

**대응:** 모든 tmp 파일은 원본과 **같은 디렉토리**에 생성할 것. cross-fs 이동이 필요하면 `shutil.move`로 명시.

---

## 4. Google Drive 권한 모델: Manager vs Content manager

**사실:** Shared Drive에는 5단계 권한이 있다 (Viewer / Commenter / Contributor / Content manager / Manager). 비슷해 보이지만 **명확한 경계**가 있다:

| 작업 | Content manager | Manager |
|------|:---:|:---:|
| 파일 업로드/수정/이동 | ✅ | ✅ |
| 파일을 **휴지통으로** 이동 (`files.update({trashed: True})`) | ✅ | ✅ |
| 파일 **영구 삭제** (`files.delete()`) | ❌ (404 반환) | ✅ |
| **멤버 추가/제거** | ❌ | ✅ |
| Shared Drive 설정 변경 | ❌ | ✅ |

**왜 중요:**
- **Live 검증 실패 1**: SA를 Shared Drive 멤버로 추가 안 함 → 모든 API 호출이 `Shared drive not found: <id>` (404)
- **Live 검증 실패 2**: Cleanup 로직이 `files.delete()` 쓰면 Content manager에선 404. Trash 방식이어야 함.

**대응:**
- 새 로봇 배포 시 SA 이메일을 **Content manager** 권한으로 Shared Drive에 추가 (Manager는 보안상 과함)
- 프로그래밍적 cleanup은 반드시 `files.update({"trashed": True})`. 30일 후 자동 영구 삭제됨.
- 자세한 배포 가이드: [`docs/spec/deployment_checklist.md`](../spec/deployment_checklist.md)

---

## 5. libx264 CRF + 야간 센서 노이즈 = 용량 폭증

**사실:** M2 recorder는 `libx264 -preset medium -crf 23` 설정 사용. CRF는 **품질 고정**이라 비트레이트가 장면 복잡도에 따라 자유변동(VBR). 24시간 녹화 시 **bitrate 편차 최대 27배** 관측됨:

| 시간대 | Bitrate | 원인 |
|--------|---------|------|
| 저녁 (조명 안정) | ~50 kbps | 정적 장면, 압축 효율 최고 |
| 자정~새벽 (저조도) | ~1 Mbps | 센서 gain 증가 → 랜덤 노이즈 grain → inter-frame 예측 실패 |
| 일출 (조명 전환) | ~1.35 Mbps | 노이즈 + 급변 조명 |
| 오전 (밝음) | ~55 kbps | 다시 압축 효율 회복 |

**왜 중요:**
- 저조도에서 **1시간 세그먼트 = 600 MB** 발생 가능. 업로드 대역폭 + Drive 저장 용량 계획 필요.
- Cron upload 시 overlap 방지 (M5에서 `flock` 고려) — 600 MB가 느린 네트워크에서 1시간 초과할 수 있음.

**대응:**
- 현재 시점: 품질 우선으로 유지. 측정 + 문서화만.
- M9 최적화 예정: `-crf 28` (~30% 용량 감소), `-maxrate 2M -bufsize 4M` (피크 억제), 또는 저조도 시 센서 gain 제한.
- 참고: [`docs/study/recording_optimization.md`](recording_optimization.md) (M9 backlog)

---

## 6. File-based state machine: `.recording_` prefix + 확장자 규칙

**사실:** recorder와 uploader는 **파일명 prefix/pair 존재 여부로** 파이프라인 단계를 구분한다. IPC/DB 없음.

```
녹화 중     : .recording_XXX.mp4 + .recording_XXX.srt   (recorder 소유)
녹화 완료   : XXX.mp4 + XXX.srt                         (embed 대상)
임베딩 완료 : XXX.mp4 (subtitle track 포함, srt 삭제됨)  (upload 대상)
업로드 완료 : (파일 삭제)                                (terminal)
```

**왜 중요:**
- `scripts/embed_srt.py`, `scripts/upload_cron.py`, `uploader.collect_session_files` 가 모두 이 규칙을 독립적으로 준수해야 함. 한 곳이라도 위반하면 미완성 파일 업로드 등 사고.
- M2/M4 구현의 핵심 불변식 — 깨면 연쇄적으로 고장남.

**대응:**
- 새 파이프라인 단계 추가 시 새 확장자 prefix/suffix로 표시하고, 모든 scanner가 동일하게 필터하도록 할 것.
- `.recording_` prefix는 recorder 전용. 다른 프로세스는 절대 건드리지 않음.
- 자세한 설계: [`docs/spec/recording_spec.md`](../spec/recording_spec.md) §2 (File-based State Machine)

---

## 7. Robot 제품 코드네임

**사실:** 회사 로봇 3종 — 코드네임은 Drive 폴더명, CLI `--product` 인자, env `PRODUCT`에 그대로 사용됨:

| Codename | Product | 용도 |
|----------|---------|------|
| `barisbrew` | 카페 로봇 | 현재 M2-M6 안정화 타겟 |
| `storagy` | 자율주행 로봇 (AMR) | 인프라 공유, 개별 런칭은 이후 |
| `deux` | 휴머노이드 | 인프라 공유, 개별 런칭은 이후 |

**왜 중요:** Drive 경로가 `{UPLOAD_ROOT}/{PRODUCT}/{BRANCH_ID}({BRANCH_NAME})/.../`. 오타가 나면 새 폴더가 생성돼서 데이터가 분산됨.

**대응:**
- env template(`config/uploader.env.example`)과 배포 체크리스트에서 가능한 값을 명시
- (미래) CLI/uploader에서 whitelist 검증 추가 고려

---

## 8. Dev / Prod 분리 구조

**사실:** 동일 SA 키 + 동일 Shared Drive, **`UPLOAD_ROOT_ID`만 다르게**:
- **Prod:** Shared Drive 루트 직속 `robot-data-archive/`
- **Dev:** 팀 폴더 `로봇지능화팀/robot-data-archive-dev/`

**왜 중요:** 단일 변수만 바꾸면 dev ↔ prod 전환. 새 SA 키 발급, 새 Drive 멤버 등록 불필요. 실수로 prod 폴더에 dev 테스트 데이터 쏟아지는 사고 방지를 위해 명확한 네이밍 + 분리된 루트 ID.

**대응:**
- 로봇별 `/etc/ros2-recorder/uploader.env`에서 `UPLOAD_ROOT_ID`만 환경에 맞게 설정
- Prod 루트 폴더(`robot-data-archive/`)는 운영 배포 직전까지 생성 안 해도 됨 (dev만 있어도 OK)

---

## 9. Shared Drive 404 = "SA가 멤버가 아님"

**사실:** `service.drives().get(driveId=<id>)` 호출이 **`Shared drive not found: <id>`** 로 404 반환 시, drive ID가 맞는데도 실패한다면 거의 항상 **SA가 해당 Shared Drive 멤버가 아님**.

**왜 중요:** 에러 메시지가 "not found"라 ID를 잘못 찍은 줄 알고 혼란. 실제로는 권한 없어서 404로 응답하는 Google의 보안 정책.

**대응:**
- `scripts/verify_shared_drive.py` step 2가 이 상황을 구체적으로 진단하는 힌트 출력.
- 멤버 추가는 Manager가 직접 해주거나 요청해야 함 (gotcha #4 참고).

---

## 10. Cron 실행 주기 vs 파일 충돌

**사실:** recorder가 wall-clock `:00`에 세그먼트 rename. Cron은 `:01`에 실행. `min-age-seconds=30` 필터 있음. 세 장치 합치면 **세그먼트 완료 후 최소 60초** 뒤에 embed/upload 시작.

**왜 중요:** recorder가 `.recording_XXX` → `XXX` rename 하는 순간에 uploader가 스캔 중이면 파일 상태 불일치 가능. 30초 buffer + :01 delay = 안전.

**대응:**
- Cron entry는 정확히 `1 * * * *` (매시 :01)
- `min-age-seconds`는 기본값 30 유지. 더 공격적으로 줄이지 말 것.
- 세그먼트 전환 로직을 바꿀 때 이 불변식이 유지되는지 확인 (`camera_recorder.py`의 `switch_segment`).

---

## 참고 문서

- [`docs/spec/recording_spec.md`](../spec/recording_spec.md) — 녹화 구현 상세
- [`docs/spec/upload_spec.md`](../spec/upload_spec.md) — 업로드 구조 + 인증
- [`docs/spec/deployment_checklist.md`](../spec/deployment_checklist.md) — 로봇 배포 절차
- [`docs/study/ros2_humble_env_setup.md`](ros2_humble_env_setup.md) — Python/NumPy 환경
- [`docs/management/upload_milestones.md`](../management/upload_milestones.md) — 마일스톤 진척도
- `docs/history/` — 각 마일스톤 구현 히스토리
