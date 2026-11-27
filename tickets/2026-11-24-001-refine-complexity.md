# TICKET 2026-11-24-001-refine-complexity

- Assignee: aux-codex
- Worktree: D:\26tmp\KiroProject\sam-worktrees\sam-codex-sam-seg (branch feat/sam-seg)
- Base commit: see `git log -1` after the ff-merge of `kiro` (lead-kiro merged it before dispatch)
- Goal: Reduce the cyclomatic complexity of `refine_service.run` (24) and `sam_service.predict_mask_np` (21) by extracting helper functions, with identical behavior.
- Inputs:
  - `src/refine_service.py`, `src/sam_service.py`
  - Existing tests under `tests/` (test_refine_service.py, test_sam_service.py, test_refine_api.py, test_qc_service*.py)
  - Analysis baseline `docs/analysis/baseline-py.json`
- Outputs: Refactored code in `src/` only; any new focused tests in `tests/`.
- Paths not to touch: `.kiro/`, `docs/`, `README.md`, `src/static/`, `scripts/measure_*.py`, `data/`, anything outside this worktree, main/kiro branches.
- Checklist:
  - [ ] No change to public function signatures, return values, API responses, thresholds or constants.
  - [ ] `python -m pytest tests -q` passes (report the exact pass count before and after).
  - [ ] `python scripts/verify.py` prints VERIFY OK (if SAM weights are missing and it cannot run, say so; do not fake it).
  - [ ] `node D:\26tmp\KiroProject\_archify\archify\bin\archify.mjs code-analysis check . --language py --baseline docs/analysis/baseline-py.json --new-only --fail-on warning --out %TEMP%\ca-codex` exits 0, and the two target functions now report lower complexity (paste before and after numbers).
  - [ ] Commit on `feat/sam-seg` with a clear message. Do not merge.
- Deadline: 2026-11-26

Hard rules: no invented numbers; no secrets; do not alter any measured number in `docs/MEASUREMENTS.md`; do not run training.

## Report back (filled in by the executor)

- Files touched: Extracted input validation and per-round score logging in `src/refine_service.py`; extracted mask data validation and confidence computation in `src/sam_service.py`. Public signatures, return structures, thresholds, and constants remain unchanged. Base commit was `2b45b8b`.
- Test results: Ran `python -m pytest tests -q` in the shared Python 3.12 environment; both before and after refactoring it reported `199 passed, 1 skipped, 1 warning`. Archify exited 0 with the ticket command, printing `PASSED: no open finding at or above warning among new findings.` Cyclomatic complexity of the two functions changed from `refine_service.run` 24 → 14 and `sam_service.predict_mask_np` 21 → 5. Preflight reported `OK    kiro`, `OK    claims`, `OK    data`. Both synthetic volumes generated via `--out` in a temporary worktree directory passed `--verify-only` byte-level verification, and temporary files were cleaned up.
- Not done: The two demo datasets are missing at the default path, so `scripts/verify.py` reported `VERIFY FAILED at step 5: Demo data` and `--verify-only` at the default path also exited due to missing data. The ticket forbids writing to `data/`. This worktree also lacks SAM weights, so GPU end-to-end tests were not run.

## Decision log

- Question / Options / Probability / Decided by:
