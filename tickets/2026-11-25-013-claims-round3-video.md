# TICKET 2026-11-25-013-claims-round3-video

- agent: aux-codex
- worktree: D:\26tmp\KiroProject\sam-worktrees\sam-codex-sam-seg
- base: `kiro` current HEAD; fast-forward this worktree (`git merge --ff-only kiro`) before starting
- goal: Fix three claims-audit findings in docs/VIDEO_SCRIPT.md, then commit.
- input: `D:\26tmp\KiroProject\_claims-audit-final2.txt` (read rows for VIDEO V5b, V2b, V7b); click rule source: `docs/MEASUREMENTS.md`
- Exact fixes:
  1. V5b voice-over and text overlay: say the click is simulated by the script and placed inside the ground-truth target on the raw view. Keep numbers unchanged. Keep the overlay short.
  2. V2b overlay: replace `H2: cleaner platform` with `H2: cleaner (low-noise) recording`.
  3. V7b narration: add one sentence saying what came from the author's earlier SGSeg project (viewer, loaders, basic SAM3 calls) and that it began in June 2026. If this makes the shot longer, shorten other wording in V7b so total stays 165 s. Do not change the shot table's total time.
- Do not change other numbers or claims. Do not touch src, `.kiro/`, README, DEVPOST, main or kiro.
- Run the CJK check on `docs/VIDEO_SCRIPT.md`, write `docs/kiro/reports/S12-claims-round3-video-20261125.md`.
- Commit exactly: `docs(video): claims round 3 fixes (E7)`. Do not merge or push.