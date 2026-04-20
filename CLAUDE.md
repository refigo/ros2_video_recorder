# CLAUDE.md

## Completion Criteria
- Always verify actual functionality before reporting a task as done.
- Verification means running the changed feature and confirming it works as intended — not just type checks, linting, or syntax validation.
- If direct verification is impossible due to environment constraints (e.g., ROS2), state that explicitly and report what was verified within the possible scope.

## Verification Principle
- Before registering any deferred execution (cron, systemd timer, at, etc.) or deploying to a live environment, always manually run the same operation under equivalent conditions first. Never schedule without prior verification.

## Documentation Structure
- `docs/spec/` — System specifications and design decisions (recording, upload, deployment)
- `docs/management/` — Milestones, backlog, and progress tracking
- `docs/study/` — Technical study notes (video encoding, MP4 recovery, ROS2 environment)
- `docs/history/` — Chronological implementation records per milestone/feature

## Project Status
- See `docs/management/progress.md` for current milestone status and next steps.
- See `docs/management/upload_milestones.md` for full milestone definitions.
