# TICKET 2026-11-24-002-demo-and-docs-audit

- 指派: aux-antigravity
- worktree: D:\26tmp\KiroProject\sam-worktrees\sam-antigravity-ui-docs (branch feat/ui-docs)
- 基线 commit: see `git log -1` after the ff-merge of `kiro`
- 目标(一句话): Follow the README "Testing instructions" and `docs/VIDEO_SCRIPT.md` shot by shot on Windows, and report every place where the app, README, DEVPOST.md or the script disagree with each other or with `docs/MEASUREMENTS.md`.
- 输入: `README.md`, `docs/VIDEO_SCRIPT.md`, `docs/DEVPOST.md`, `docs/MEASUREMENTS.md`, `docs/architecture/`, the running app (see README "Run it"; synthetic data via `scripts/generate_synthetic_seismic.py`).
- 输出:
  - `docs/audit/2026-11-24-demo-audit.md`: a table (item, expected, observed, file and line, severity).
  - Direct fixes only for typos, wrong paths and broken links in `docs/` and `README.md`. Anything that changes a claim or a number is reported, not fixed.
  - A judge's-eye review of README and DEVPOST.md against the Kiroween criteria in `docs/COMPETITION_RULES.md` (Design and Presentation weigh 40%): three concrete suggestions, each with the exact text to change.
- 不许碰的路径: `src/`, `.kiro/`, `scripts/`, `tests/`, `data/`, other worktrees, main/kiro branches.
- 验收清单:
  - [ ] Every shot V1a to V7b in VIDEO_SCRIPT.md has a row: reproducible yes/no, with what you saw.
  - [ ] Every number in README/DEVPOST/VIDEO_SCRIPT is checked against `docs/MEASUREMENTS.md`; mismatches are listed.
  - [ ] No claim "first SAM for seismic" anywhere (grep and report).
  - [ ] Whether the 5 s architecture-diagram insert at the end of V4a keeps the video under 3 minutes: your timing estimate.
  - [ ] Commit on `feat/ui-docs`. Do not merge. No new numbers invented.
- 截止时间: 2026-11-27

Hard rules: do not log in anywhere; do not upload or post anything; no secrets.

## 回单(完成时由执行者填写)

- 改了哪些文件:
- 测试结果:
- 未解决的问题:

## 判定记录

- 问题 / 选项 / 概率 / 最后谁定的:
