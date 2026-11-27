# TICKET 2026-11-24-002-demo-and-docs-audit

- Assignee: aux-antigravity
- Worktree: D:\26tmp\KiroProject\sam-worktrees\sam-antigravity-ui-docs (branch feat/ui-docs)
- Base commit: see `git log -1` after the ff-merge of `kiro`
- Goal: Follow the README "Testing instructions" and `docs/VIDEO_SCRIPT.md` shot by shot on Windows, and report every place where the app, README, DEVPOST.md or the script disagree with each other or with `docs/MEASUREMENTS.md`.
- Inputs: `README.md`, `docs/VIDEO_SCRIPT.md`, `docs/DEVPOST.md`, `docs/MEASUREMENTS.md`, `docs/architecture/`, the running app (see README "Run it"; synthetic data via `scripts/generate_synthetic_seismic.py`).
- Outputs:
  - `docs/audit/2026-11-24-demo-audit.md`: a table (item, expected, observed, file and line, severity).
  - Direct fixes only for typos, wrong paths and broken links in `docs/` and `README.md`. Anything that changes a claim or a number is reported, not fixed.
  - A judge's-eye review of README and DEVPOST.md against the Kiroween criteria in `docs/COMPETITION_RULES.md` (Design and Presentation weigh 40%): three concrete suggestions, each with the exact text to change.
- Paths not to touch: `src/`, `.kiro/`, `scripts/`, `tests/`, `data/`, other worktrees, main/kiro branches.
- Checklist:
  - [x] Every shot V1a to V7b in VIDEO_SCRIPT.md has a row: reproducible yes/no, with what you saw.
  - [x] Every number in README/DEVPOST/VIDEO_SCRIPT is checked against `docs/MEASUREMENTS.md`; mismatches are listed.
  - [x] No claim "first SAM for seismic" anywhere (grep and report).
  - [x] Whether the 5 s architecture-diagram insert at the end of V4a keeps the video under 3 minutes: your timing estimate.
  - [x] Commit on `feat/ui-docs`. Do not merge. No new numbers invented.
- Deadline: 2026-11-27

Hard rules: do not log in anywhere; do not upload or post anything; no secrets.

## Report back (filled in by the executor)

- Files touched:
  - `README.md`: Fixed missing path prefix `src/static/js/` in the table entries (`survey-map.js`, `refine-panel.js`) and missing `.kiro/specs/` prefix in the body text (`.kiro/specs/qc-refine-loop/tasks.md`).
  - `docs/VIDEO_SCRIPT.md`: Fixed missing `docs/architecture/` prefix in the HTML path of the insert note on line 78.
  - `docs/audit/2026-11-24-demo-audit.md`: Created full audit report (shot-by-shot live verification table V1a–V7b, comparison table of all numbers against MEASUREMENTS.md, forbidden-claim scan, 5 s architecture insert duration estimate, and 3 concrete revision suggestions aligned with judging criteria).
  - `tickets/2026-11-24-002-demo-and-docs-audit.md`: Checked off checklist and filled in report back and decision log.
- Test results:
  - `scripts/verify.py` passed completely (`VERIFY OK in 14 s`, covering JS 9/9 syntax, Python 15-file AST, all-green preflight, pytest 200 passed, synthetic data byte-level determinism check).
  - `scripts/test_refine_e2e.py` passed on live GPU (`PASS`, clean volume il 23 ran 3 iterations successfully, noisy volume il 20 triggered `qc_unreliable` stop accurately).
  - `git grep -in "first SAM"` full scan found no policy violation; arXiv citations intact.
- Not done:
  - No blocking issues. Found that README/DEVPOST testing instructions state the startup slice is "inline 1", whereas the actual code centers on "Inline 25 (index 24)"; although users can still enter 20 and jump as instructed, text and behavior diverge, so a fix is proposed in the audit report and Judge Suggestion 3 for the lead to merge.

## Decision log

- Question / Options / Probability / Decided by:
  - Question 1: Whether adding the 5 s architecture diagram insert at the end of V4a exceeds the time limit / Option A: Include insert (170s, keeping 10s margin) Option B: Drop insert (165s) / Probability: A 95% / Decided by: aux-antigravity recommended Option A after timing check to strengthen Design and Tech Implementation scores.
  - Question 2: Whether factual discrepancies in docs (such as inline 1 and relative Devpost links) should be edited directly or reported in the audit / Option A: Fix only typos and missing paths, report factual/claim copy as suggestions only Option B: Edit everything directly / Probability: A 100% / Decided by: aux-antigravity strictly followed the ticket instruction "Direct fixes only for typos, wrong paths and broken links... Anything that changes a claim or a number is reported, not fixed".
