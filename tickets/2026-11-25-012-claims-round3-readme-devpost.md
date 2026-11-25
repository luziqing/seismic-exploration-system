# TICKET 2026-11-25-012-claims-round3-readme-devpost

- agent: aux-antigravity
- worktree: D:\26tmp\KiroProject\sam-worktrees\sam-antigravity-ui-docs
- base: `kiro` current HEAD; fast-forward this worktree (`git merge --ff-only kiro`) before starting
- goal: Fix four claims-audit findings in README.md and docs/DEVPOST.md, then commit.
- input: `D:\26tmp\KiroProject\_claims-audit-final2.txt` (read the matching rows); click rule source: `docs/MEASUREMENTS.md` (protocol of measure_refine.py)
- Exact fixes:
  1. README Results table row "Does the QC loop improve a one-click SAM3 mask?" and DEVPOST Accomplishments "QC loop results": state that the click is simulated by the script, placed inside the ground-truth target on the raw view. Use the exact wording of `docs/MEASUREMENTS.md`. Keep all numbers unchanged.
  2. README "Run it" Platform line: replace `a current Chrome / Edge / Firefox` with `a current desktop browser (tested with Chrome only)`.
  3. README step 2: remove the sentence/phrase that says the check should print a `+cu124` version. Keep the `pip install ... --index-url .../cu124` command line itself, but add no claim about versions. The check should only say it should print True for CUDA.
  4. DEVPOST IDE paragraphs (both places that say the IDE was used for editing and reviewing code and documents): reduce to `Kiro IDE was also used (owner statement; no separate log is kept).` Keep the CLI statements unchanged.
- Do not change other numbers or claims. Do not touch src, `.kiro/`, `VIDEO_SCRIPT.md`, main or kiro.
- Run `.venv\Scripts\python.exe scripts\verify.py` (expect failure only at data/weights in a worktree, which is acceptable if so; say which step), the CJK check on README.md and docs/DEVPOST.md, write `docs/kiro/reports/S12-claims-round3-readme-devpost-20261125.md`.
- Commit exactly: `docs: claims round 3 fixes for README and Devpost (E7)`. Do not merge or push.