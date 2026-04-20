# Robot Deployment Checklist

Last updated: 2026-04-14

This checklist covers adding a **new robot** to the recording + upload pipeline. One-time company-wide setup (GCP project, Service Account, Shared Drive membership) is assumed done — see `docs/spec/upload_spec.md` and the Shared Drive verification plan.

> **배포 전 필독:** [`docs/study/operational_gotchas.md`](../study/operational_gotchas.md) — 권한 모델, `-f mp4` 필수, `os.replace` same-fs, 저조도 용량 폭증 등 함정 모음.

## Prerequisites (one-time, company-wide)

- [ ] Company GCP project with Drive API enabled
- [ ] Service Account created, JSON key downloaded to a secure location (not committed)
- [ ] Shared Drive `[XYZ] 본사 자료` exists; SA added as **Content manager** (Manager가 등록해줘야 함 — Content manager는 멤버 추가 권한 없음)
- [ ] **Prod** root folder `robot-data-archive` (Shared Drive root 직속) 생성, ID 기록
- [ ] **Dev** root folder `robot-data-archive-dev` (`로봇지능화팀/` 하위) 생성, ID 기록
- [ ] `scripts/verify_shared_drive.py` executed once against dev root and all 6 steps PASS

Values recorded:

| Key | Value |
|-----|-------|
| `GOOGLE_APPLICATION_CREDENTIALS` (path on robot) | `/etc/ros2-recorder/keys/company-sa.json` |
| `UPLOAD_SHARED_DRIVE_ID` | `<from Shared Drive URL>` |
| `UPLOAD_ROOT_ID` (prod) | `<from robot-data-archive folder URL>` |
| `UPLOAD_ROOT_ID` (dev) | `<from robot-data-archive-dev folder URL>` |
| `PRODUCT` | one of `barisbrew`, `storagy`, `deux` (per robot fleet) |

## Per-robot deployment steps

### 1. Copy the Service Account key

```bash
sudo mkdir -p /etc/ros2-recorder/keys
sudo cp company-sa.json /etc/ros2-recorder/keys/company-sa.json
sudo chmod 600 /etc/ros2-recorder/keys/company-sa.json
sudo chown root:root /etc/ros2-recorder/keys/company-sa.json
```

Transfer the key file via a secure channel (ssh/scp over trusted network). Never place it under a git working tree.

### 2. Install the env file

> **Why .env, not YAML?** systemd `EnvironmentFile=` and shell `source` both load `.env` natively. Our config is flat key=value — YAML would add a parser dependency (`yq` or Python) for no structural benefit.

```bash
sudo mkdir -p /etc/ros2-recorder
sudo cp config/recorder.env.example /etc/ros2-recorder/recorder.env
sudo ${EDITOR:-nano} /etc/ros2-recorder/recorder.env
# Replace:
#   UPLOAD_SHARED_DRIVE_ID=...
#   UPLOAD_ROOT_ID=...    ← prod for production robots, dev for lab/testing
#   PRODUCT=barisbrew     ← robot product this fleet belongs to
#   BRANCH_ID=BBxxx       ← this robot's branch code
#   BRANCH_NAME=...       ← this robot's branch display name
sudo chmod 640 /etc/ros2-recorder/recorder.env
```

### 3. Smoke-test Drive access from this robot

```bash
set -a
source /etc/ros2-recorder/recorder.env
set +a
cd ~/git_repo_mine/ros2_video_recorder
.venv/bin/python scripts/verify_shared_drive.py
```

All 6 steps must PASS. If Step 2 fails the robot cannot see the Shared Drive (check network + SA membership). If Step 3 fails we'll need to discuss a folder-name fallback (ASCII only).

### 4. Install recorder + uploader services

```bash
# From the repo root:
sudo scripts/install.sh /opt/ros2-recorder
```

This installs:
- systemd unit `ros2-camera-recorder.service` (recorder daemon)
- Cron entry: `deliver.sh` at `:01` every hour (embed + upload pipeline)
- Log directory `/var/log/ros2-recorder/`

The install script does NOT enable or start the service. Test manually first:

```bash
# Test recorder (Ctrl+C to stop):
set -a && source /etc/ros2-recorder/recorder.env && set +a
scripts/start_recorder.sh

# Test upload pipeline:
scripts/deliver.sh --min-age-seconds 0
```

Then enable:
```bash
sudo systemctl enable --now ros2-camera-recorder
```

- [ ] verify: `journalctl -u ros2-camera-recorder -f` shows recording output
- [ ] verify: hourly segment appears in Drive under `<UPLOAD_ROOT>/<PRODUCT>/<BRANCH_ID>(<BRANCH_NAME>)/YYYY-MM/YYYYMMDD/`

## Rollback

To retire a robot or rotate credentials:

1. Disable systemd/cron units on the robot
2. Remove `/etc/ros2-recorder/keys/company-sa.json`
3. (Admin) If key was compromised, delete the SA key in GCP Console → the key is invalidated globally; issue a new one and redeploy to remaining robots

## Verifying end-to-end (per site)

After Step 4, wait for the first hourly boundary + 1 minute and check:

```bash
# local
ls -lh videos/ | tail
# no .recording_ files older than 30 min (stale = recorder crashed)

# Drive (in browser)
# Navigate: [XYZ] 본사 자료 → robot-data-archive[-dev] → <PRODUCT> → <BRANCH_ID>(<BRANCH_NAME>) → <YYYY-MM> → <YYYYMMDD>
# Open one MP4 → H.264 playback + CC subtitle should work
```
