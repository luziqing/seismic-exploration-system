# TICKET 2026-11-24-010-final-claims-readme-devpost

- Assignee: aux-antigravity
- Worktree: D:\26tmp\KiroProject\sam-worktrees\sam-antigravity-ui-docs
- Base commit: `kiro` current HEAD; fast-forward this worktree before starting
- Goal: Fix the final claims-audit README/DEVPOST findings, then commit.
- Input: `D:\26tmp\KiroProject\_claims-audit-final.txt`
- Exact fixes:
  1. README: remove the unsourced phrase `developed with torch 2.6.0+cu124`; keep the fresh-machine test statement.
  2. DEVPOST Inspiration: replace `beneath kilometres of stronger signal and noise` with `below stronger reflections and noise`.
  3. DEVPOST Challenge 2: change the wording so it says the UI pick produced a 32-pixel marker mask and clean server rendering produced a 521,298-pixel mask; explicitly say these counts expose the overlay-corruption bug and are not ground-truth target measurements.
  4. DEVPOST Accomplishments: replace `following only the README` with wording that says the sub-agent followed the README after obtaining the repository bundle.
- Do not change any other numbers or claims. Do not touch source, `.kiro/`, `VIDEO_SCRIPT.md`, or main/kiro.
- Run `python scripts/verify.py`, CJK check, fill a report, and commit exactly: `docs: final claims fixes for README and Devpost (E7)`.
- Do not merge or push.
