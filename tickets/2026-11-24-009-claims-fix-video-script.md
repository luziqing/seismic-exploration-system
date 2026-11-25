# TICKET 2026-11-24-009-claims-fix-video-script

- 指派: aux-simple (OpenCode, weaker model)
- worktree: D:\26tmp\KiroProject\sam-worktrees\sam-opencode-simple (branch chore/simple)
- 基线 commit: `kiro` HEAD after the ff-merge done by lead-kiro before dispatch
- 目标(一句话): Apply the seven exact text replacements below to `docs/VIDEO_SCRIPT.md`, and nothing else.
- 输入: `docs/VIDEO_SCRIPT.md` only. Each change is a literal find → replace. If a "find" string is not present the stated number of times (once unless said otherwise), stop and report it; do not improvise.

1. Find (appears three times, lines ~12, ~28 and ~63): `never keeps a worse round`
   Replace all three with: `never keeps a round with a worse QC score`
2. Find (appears once, line ~28): `It checks itself, fixes poor clicks, and never keeps a worse round."`
   Replace with: `It checks itself, fixes poor clicks, and never keeps a round with a worse QC score."`
   (If step 1 already changed this line, check that the line now reads exactly like the replacement.)
3. Find: `AUC 0.44 to 0.93 on the noisy volume."`
   Replace with: `AUC 0.44 to 0.93 on the noisy volume. The model was built with a 10 Hz target."`
4. Find: `measured better for the model.`
   Replace with: `measured better on the noisy volume.`
5. Find: `"On our synthetic model, the loop raised the mean IoU`
   Replace with: `"On the clean synthetic volume, the loop raised the mean IoU`
6. Find: `"On the noisy volume, the QC gate recognises the target is too weak and declines to refine.`
   Replace with: `"On most noisy slices, the QC gate recognises the target is too weak and declines to refine.`
7. Find: `` `steering/` (scope, product, tech, structure, competition, sources) ``
   Replace with: `` `steering/` (scope, product, tech, structure, competition, sources, seismic-domain) ``
8. Delete the whole section that starts with the heading `## Optional insert: architecture diagram` down to the end of that section (the heading and its paragraph). Reason: scope S12 limits the video to 165 s.

- 不许碰的路径: everything except `docs/VIDEO_SCRIPT.md` and this ticket file. Do not change timings, shot IDs, or any number other than what is written above.
- 验收清单:
  - [ ] `Select-String docs\VIDEO_SCRIPT.md -SimpleMatch 'never keeps a worse round'` returns nothing.
  - [ ] `Select-String docs\VIDEO_SCRIPT.md -SimpleMatch 'Optional insert'` returns nothing.
  - [ ] `git diff --stat` shows only `docs/VIDEO_SCRIPT.md` and this ticket.
  - [ ] Commit on `chore/simple`: `docs(video): claims-audit fixes (E7)`. Do not merge.
- 截止时间: 2026-11-25

## 回单(完成时由执行者填写)

- 改了哪些文件:
  - `docs/VIDEO_SCRIPT.md` (only the seven literal replacements and the deletion of the `## Optional insert: architecture diagram` section)
  - this ticket file (handoff)
- 测试结果/逐条对照:
  1. `never keeps a worse round` found 3 times (lines 12, 28, 63) → all replaced with `never keeps a round with a worse QC score`.
  2–8. Each remaining "find" string was present exactly once and was replaced literally; line 28 now reads exactly `... fixes poor clicks, and never keeps a round with a worse QC score."` after step 1.
  - `Select-String docs\VIDEO_SCRIPT.md -SimpleMatch 'never keeps a worse round'` → no output.
  - `Select-String docs\VIDEO_SCRIPT.md -SimpleMatch 'Optional insert'` → no output.
  - `git diff --stat` → `docs/VIDEO_SCRIPT.md | 20 ++++++++------------` (1 file; the ticket appears only after this handoff is filled). Reviewed `git diff`: no timing, shot ID or other number changed; the only line removals are the optional-insert heading and its paragraph.
  - `D:\26tmp\soft2-SGSeg\.venv\Scripts\python.exe scripts/verify.py` → `VERIFY OK in 12 s` (200 passed, 0 skipped).
  - Commit on `chore/simple`: `docs(video): claims-audit fixes (E7)`.
- 未解决的问题: none in the replacements. Not run by me: the claims-auditor agent and any video/propagation shot (they are S12/E7 work for the lead). The ticket's C3 ("total 165 s") is unaffected because the deleted section was the optional 5 s insert.
