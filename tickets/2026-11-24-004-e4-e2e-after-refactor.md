# TICKET 2026-11-24-004-e4-e2e-after-refactor

- Assignee: aux-codex
- Worktree: D:\26tmp\KiroProject\sam-worktrees\sam-codex-sam-seg (branch feat/sam-seg)
- Base commit: `kiro` HEAD after the ff-merge done by lead-kiro before dispatch (`git log -1`)
- Goal: Prove with a live server and the real SAM3 weights that the merged refactor of ticket 001 did not change behavior, and complete scope item E4 (the full demo flow runs 3 times in a row).
- Inputs:
  - `guide.md` sections 3, 9 (E4 row) and 10; `.kiro/steering/scope.md` section 0
  - `scripts/test_refine_e2e.py`, `scripts/test_propagation_e2e.py`, `test_frontend_flow.py`
  - SAM3 weights at `D:\26tmp\KiroProject\SamForGeophysics\data\weights\` (read-only)
- Setup (inside your worktree only):
  1. `python scripts/generate_synthetic_seismic.py` into this worktree's `data/` (then `--verify-only` must pass).
  2. Junction the weights, do not copy them: `cmd /c mklink /J data\weights D:\26tmp\KiroProject\SamForGeophysics\data\weights`. `data/` is gitignored; never `git add -f`.
  3. Start the server from this worktree on port **9340** (9339 may be in use). Stop it when done.
- Outputs:
  - `docs/kiro/reports/E4-20261124.md` in the format of guide.md section 10.
  - One short E4 entry appended to `docs/kiro/build-log.md` (date, what ran, result).
- Paths not to touch: `src/` (no code changes in this ticket; if something fails, report it, do not fix it), `.kiro/`, `README.md`, `docs/DEVPOST.md`, `docs/VIDEO_SCRIPT.md`, `docs/MEASUREMENTS.md`, `scripts/measure_*.py`, the main repo `D:\26tmp\KiroProject\SamForGeophysics` (read the weights only).
- Checklist:
  - [ ] `scripts/test_refine_e2e.py` and `scripts/test_propagation_e2e.py` pass against the server on 9340 (paste the key output lines).
  - [ ] E4: the flow low-freq → compare → noisy/clean → SAM + Auto-refine → round selection → export runs 3 times in a row without restarting the server or reloading the page, headless Chrome at 1600×900, no page or console errors (favicon 404 ignored). Look at the screenshots you take.
  - [ ] `python scripts/verify.py` prints VERIFY OK in this worktree once data is generated.
  - [ ] Test masks you created are deleted; the server is stopped; no temp dirs left; `git status` shows only the report and build-log.
  - [ ] Commit on `feat/sam-seg`: `docs(kiro): E4 repeatable demo and e2e after refactor (E4)`. Do not push, do not merge.
- Deadline: 2026-11-26

No invented numbers. Do not re-run `measure_refine.py` or `measure_lowfreq.py`. Say plainly what you did not verify.

## Report back (filled in by the executor)

- Files touched: E4 report, Kiro build log, and this handoff.
- Test results: Live CUDA refine and propagation passed, HTTP frontend checks passed on a cold server, and VERIFY OK. All three browser cycles exported the selected round on a single page.
- Not done: E4 console acceptance remains open. Missing saved masks produce non-favicon HTTP 404 console errors. No pre-refactor comparison was run.
