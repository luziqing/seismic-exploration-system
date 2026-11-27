# TICKET 2026-11-24-011-final-claims-video

- Assignee: aux-codex
- Worktree: D:\26tmp\KiroProject\sam-worktrees\sam-codex-sam-seg
- Base commit: `kiro` current HEAD; fast-forward this worktree before starting
- Goal: Fix the final claims-audit video wording, then commit.
- Input: `D:\26tmp\KiroProject\_claims-audit-final.txt`
- Exact fixes only:
  1. VIDEO V2a overlay: change `AUC 0.44 → 0.93 (script: measure_lowfreq.py)` to `AUC 0.44 → 0.93 on the synthetic noisy volume (script: measure_lowfreq.py)`.
  2. VIDEO V5b overlay: change `IoU 0.80 → 0.81 (mean), 0.88 → 0.89 (median)` to `IoU 0.80 → 0.81 (mean), 0.88 → 0.89 (median), clean synthetic volume`.
  3. VIDEO V7 voice-over: replace `A custom agent reviews every public number against the measurements.` with `A custom agent reviews public text against the measurements.`
- Do not change timings, shot IDs, other numbers, or any other file except `docs/VIDEO_SCRIPT.md` and this ticket.
- Run the video text checks, fill the handoff, and commit exactly: `docs(video): final claims fixes (E7)`.
- Do not merge or push.
