# M3 revision: Product 계층 추가 + Dev/Prod 분리 + 라이브 검증 완료

**날짜:** 2026-04-14
**범위:** `uploader.py`, `scripts/verify_shared_drive.py`, `config/uploader.env.example`, `docs/spec/upload_spec.md`, `docs/spec/deployment_checklist.md`, `docs/management/upload_milestones.md`, `README.md`

## 배경

M3 (`08_m3_upload_restructure_20260414_1401`) 에서는 uploader 폴더 구조를 `barisbrew-recorded-datas/{BRANCH_ID}({BRANCH_NAME})/.../` 로 제안했다. 이후 라이브 Shared Drive 검증 중 두 가지가 드러났다:

1. **Product 계층 누락**: 회사에 로봇 제품이 `barisbrew`(카페), `storagy`(AMR), `deux`(휴머노이드) 세 가지 존재. 동일 archive 폴더 아래 product 없이 branch만 있으면 향후 제품 간 혼동 발생.
2. **Dev/Prod 분리 필요**: 개발/테스트용과 운영용이 같은 경로를 쓰면 권한 실수 리스크.

## 결정 사항

### 최종 폴더 구조

```
[Shared Drive root]
├── robot-data-archive/            ← prod (Shared Drive 루트 직속)
│    └── {PRODUCT}/
│         └── {BRANCH_ID}({BRANCH_NAME})/
│              └── {YYYY-MM}/
│                   └── {YYYYMMDD}/
│                        └── *.mp4
└── 로봇지능화팀/
     └── robot-data-archive-dev/   ← dev (team folder 하위)
          └── (위와 동일 구조)
```

- **Top-level naming**: `robot-data-archive`. "robot" 접두사로 일반 문서 archive와 구분. `data-archive` 단독보다 명시적.
- **Product naming**: 짧은 코드네임 (`barisbrew`, `storagy`, `deux`). CLI 간결, 엔지니어링 관행.
- **Root folder 관리**: 사용자가 Drive에서 수동 생성 → 업로더는 그 폴더 ID만 받음. 업로더가 첫 depth에서 자동 생성하는 건 `{PRODUCT}/` 부터.
- **Dev/Prod 분리 방식**: 동일 SA + 동일 Shared Drive + **`UPLOAD_ROOT_ID`만 다르게 설정**. 중간 계층(`env/` 등) 추가 없음.

### 왜 product를 M3 초안에서 빼고 다시 넣었나

M3 초안 시점에는 `PRODUCT_NAME`이 "10분 슬롯 시절의 레거시"처럼 보여 제거했다. 하지만 회사 제품 다양성이 확인된 지금, **같은 Shared Drive 안에서 제품별 분리가 필수**. 이는 레거시 복원이 아니라 시작부터 포함했어야 할 구조적 결정.

## 코드 변경

### `uploader.py`
- `UploadConfig`에 `product: str` 추가
- argparse `--product` + env `PRODUCT` 추가 (session mode에서 required)
- `build_drive_path_parts(product, branch_id, branch_name, dt)` — 첫 segment로 `product` 사용 (기존 `"barisbrew-recorded-datas"` 고정값 제거)
- `upload_session()` validation에 `product` 필수 체크 추가
- Folder cache key를 `/`.join(path_parts)` 전체로 변경 (product가 다른 경우 캐시 분리)

### `scripts/verify_shared_drive.py`
- Smoke test 경로에 `uploader.build_drive_path_parts()` 를 그대로 사용 → 운영 로직과 1:1 검증
- `SMOKE_TEST_PRODUCT = "_smoketest"`, `SMOKE_TEST_BRANCH_ID = "SMOKE"`, `SMOKE_TEST_BRANCH_NAME = "테스트지점"`
- Cleanup은 top-level `_smoketest/` 폴더 1개만 trash (Drive trash는 recursive)

### `config/uploader.env.example`
- `PRODUCT=barisbrew` 추가
- 주석에 prod/dev 각각의 root folder 설명, SA 키 공유 원칙 명시

### 문서
- `docs/spec/upload_spec.md`, `docs/spec/deployment_checklist.md`, `docs/management/upload_milestones.md`, `README.md` 모두 동일 구조/예시로 갱신

## 라이브 검증 결과

`scripts/verify_shared_drive.py` 6/6 PASS:
```
[1/6] Auth + Drive service build             ... PASS
[2/6] Shared Drive metadata                  ... PASS — name='[XYZ] 본사 자료'
[3/6] Create test folder tree                ... PASS — id=...
[4/6] Upload 1KB dummy file                  ... PASS — md5 verified
[5/6] Re-upload should skip                  ... PASS — idempotent
[6/6] Cleanup test folder + file             ... PASS
```

### 중간 학습: Content manager vs Manager

- **Shared Drive 멤버 관리**: Manager 전용. Content manager는 본인이 멤버 추가 불가 → Manager에게 요청 필수.
- **파일 삭제 권한**: Content manager는 `files.update({"trashed": True})` 가능, `files.delete()` (영구) 불가 → 404. Cleanup 로직은 trash 방식 사용.

### 설정값 (dev 환경 확인됨)

| Key | Value |
|-----|-------|
| SA email | `xyzcorp-data-uploader@xyzcorp-data-pipeline-ops.iam.gserviceaccount.com` |
| SHARED_DRIVE_ID | `0AHx24e3E4gZkUk9PVA` |
| UPLOAD_ROOT_ID (dev) | `1VmWsvbKfwquo3E2atQ1kQzheovLB23YL` (folder: `robot-data-archive-dev`, 로봇지능화팀 하위) |
| UPLOAD_ROOT_ID (prod) | 미생성. 운영 배포 시 Shared Drive root에 `robot-data-archive` 생성 후 ID 등록 |

## 선행 작업

- `08_m3_upload_restructure_20260414_1401` (M3 초안 — offline 검증)

## 후속 작업

- **M4**: cron 기반 SRT 임베딩 + 업로드 + MD5 검증 + 로컬 삭제 통합 스크립트
- **Prod 폴더 생성**: Shared Drive root에 `robot-data-archive/` 생성 후 ID 확보 (운영 배포 시점에)
- **SA 키 로봇 배포**: 각 로봇에 `/etc/ros2-recorder/keys/company-sa.json` 복사 (배포 시)
