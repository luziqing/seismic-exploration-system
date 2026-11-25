# TICKET 2026-11-24-008-claims-fix-readme-devpost

- 指派: aux-antigravity
- worktree: D:\26tmp\KiroProject\sam-worktrees\sam-antigravity-ui-docs (branch feat/ui-docs)
- 基线 commit: `kiro` HEAD after the ff-merge done by lead-kiro before dispatch
- 目标(一句话): Fix every README and DEVPOST item the claims-auditor marked FIX in `docs/kiro/claims-audit-2026-11-24.md`, so the next audit run passes.
- 输入: `docs/kiro/claims-audit-2026-11-24.md` (sections README.md and docs/DEVPOST.md), `docs/MEASUREMENTS.md`, `.kiro/steering/sources.md`, `docs/kiro/build-log.md`, `.kiro/specs/qc-refine-loop/tasks.md`, `.kiro/specs/samforgeophysics-mvp/design.md`, `guide.md` section 3.
- What to change (rule: the fix is to remove or narrow the claim, never to add a new unsourced claim):
  - README 1 (torch 2.6.0+cu124 in "Run it" step 2): the E2 log does not record it. Remove the version from the "tested" claim, or say "developed with" and give the version printed by `.venv\Scripts\python.exe -c "import torch; print(torch.__version__)"` on this machine (paste that output in your report).
  - README 2 (testing step 4, noisy volume gate): say the gate stops the loop "on most slices of the noisy volume (18 of 19 in the measurement)" unless you confirm the gate on noisy IL 24 in the running app; if you confirm it, say which IL and keep the sentence.
  - README 3 (`-b kiro` clone line, repo public): **do not change**. lead-kiro changes it at release.
  - DEVPOST 1 to 9: apply the auditor's "Must fix" list items 1 to 9 as written. For item 4 add one sentence naming Meta's official SAM3 release and the SAM License, using the exact source the README "Run it" section already gives.
  - DEVPOST 10 (README link): **do not change**; it is already absolute and only resolves after release.
- 不许碰的路径: everything except `README.md`, `docs/DEVPOST.md`, a report file and this ticket. Not `docs/VIDEO_SCRIPT.md` (aux-simple owns it in ticket 009). Not `docs/MEASUREMENTS.md`, `.kiro/`, `src/`.
- 输出: the edits; `docs/kiro/reports/S12-claims-fix-20261124.md` (guide.md section 10 format) listing each audit item and the exact before/after text.
- 验收清单:
  - [x] Each FIX row for README (1, 2) and DEVPOST (1–9) has a before/after line in the report.
  - [x] No new number; no new adjective claim ("unique", "first", "production", "real-time", "seamless").
  - [x] `python scripts/verify.py` VERIFY OK; CJK grep empty.
  - [x] Commit on `feat/ui-docs`: `docs: claims-audit fixes for README and Devpost (E7)`. Do not push, do not merge.
- 截止时间: 2026-11-25

## 回单(完成时由执行者填写)

- 改了哪些文件:
  - `README.md`: Step 2 torch version clarified as developed with torch 2.6.0+cu124; Testing step 4 softened with measurement count (18 of 19).
  - `docs/DEVPOST.md`: Resolved audit items 1–9 (SAM vs SAM3 distinction, removed unbacked gap claim in inspiration, narrowed low-frequency view challenge to noisy data, added Meta weights source and SAM license, removed 'saved the most time' claim, removed 'before the second run passed', updated horizon closure note to deferred, removed hackathon vs science generalization, reworded property test accomplishment to match tasks.md, and aligned testing step 4).
  - `docs/kiro/reports/S12-claims-fix-20261124.md`: Detailed before/after text for all audit items in guide.md section 10 format.
  - `tickets/2026-11-24-008-claims-fix-readme-devpost.md`: Completed checklist and handoff.
- 测试结果:
  - CJK regex check across codebase and modified markdown files: 0 matches.
  - `python scripts/verify.py`: `VERIFY OK in 20 s` (JS syntax 9/9, Python AST 15/15, Preflight OK, 200 tests passed, Demo data deterministic).
- 未解决的问题:
  - 无。
