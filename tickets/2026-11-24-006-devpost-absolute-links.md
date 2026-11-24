# TICKET 2026-11-24-006-devpost-absolute-links

- 指派: aux-simple (OpenCode, weaker model)
- worktree: D:\26tmp\KiroProject\sam-worktrees\sam-opencode-simple (branch chore/simple)
- 基线 commit: `kiro` HEAD after the ff-merge done by lead-kiro before dispatch (`git log -1`)
- 目标(一句话): In `docs/DEVPOST.md`, replace every relative link with an absolute GitHub URL, because the text is pasted into devpost.com where relative links break.
- 输入: `docs/DEVPOST.md` only.
- Rules for the new URLs:
  - A link to the README "Run it" section becomes `https://github.com/luziqing/seismic-exploration-system#run-it`.
  - Any other relative link `../X` or `X` becomes `https://github.com/luziqing/seismic-exploration-system/blob/main/X` (path from the repo root; `main` is the release branch).
  - External `http(s)` links stay exactly as they are.
- 输出: the corrected `docs/DEVPOST.md`; the list of changed links in the handoff below.
- 不许碰的路径: everything except `docs/DEVPOST.md` and this ticket file. Do not change any sentence, word or number; only the URL inside `( )` of a link.
- 验收清单:
  - [ ] `Select-String docs\DEVPOST.md -Pattern '\]\((?!https?:)'` returns nothing.
  - [ ] `git diff --stat` shows only `docs/DEVPOST.md` and this ticket.
  - [ ] Commit on `chore/simple`: `docs(devpost): absolute links for devpost.com (S12)`. Do not merge.
- 截止时间: 2026-11-25

If a link target is unclear, do not guess: list it under 未解决的问题 and reply to lead-kiro.

## 回单(完成时由执行者填写)

- 改了哪些文件:
  - `docs/DEVPOST.md` (last line only; link target changed, text unchanged)
  - this ticket file (handoff)
- 改动的链接(1 条; no other relative links found):
  - `[README](../README.md)` → `[README](https://github.com/luziqing/seismic-exploration-system#run-it)` (README "Run it" section; `README.md` has `## Run it` at line 30, so `#run-it` is the correct anchor)
  - External links (`https://arxiv.org/abs/2407.14121`, `https://arxiv.org/abs/2606.15786`) left unchanged.
- 测试结果:
  - `Select-String docs\DEVPOST.md -Pattern '\]\((?!https?:)'` → no output.
  - `git diff --stat` after the link edit → `docs/DEVPOST.md | 2 +-`, 1 file changed, 1 insertion(+), 1 deletion(-).
  - `D:\26tmp\soft2-SGSeg\.venv\Scripts\python.exe scripts/verify.py` → `VERIFY OK in 12 s` (200 passed, 0 skipped; had to generate the demo data first because this worktree had none: `generate_synthetic_seismic.py` and `--clean` both reported `OK deterministic ... byte-identical`).
  - Commit on `chore/simple`: `docs(devpost): absolute links for devpost.com (S12)`.
- 未解决的问题: none. One note: `git diff --stat` also lists this ticket file after the handoff is filled, as allowed by the ticket.
