# TICKET 2026-11-24-002-demo-and-docs-audit

- 指派: aux-antigravity
- worktree: D:\26tmp\KiroProject\sam-worktrees\sam-antigravity-ui-docs (branch feat/ui-docs)
- 基线 commit: see `git log -1` after the ff-merge of `kiro`
- 目标(一句话): Follow the README "Testing instructions" and `docs/VIDEO_SCRIPT.md` shot by shot on Windows, and report every place where the app, README, DEVPOST.md or the script disagree with each other or with `docs/MEASUREMENTS.md`.
- 输入: `README.md`, `docs/VIDEO_SCRIPT.md`, `docs/DEVPOST.md`, `docs/MEASUREMENTS.md`, `docs/architecture/`, the running app (see README "Run it"; synthetic data via `scripts/generate_synthetic_seismic.py`).
- 输出:
  - `docs/audit/2026-11-24-demo-audit.md`: a table (item, expected, observed, file and line, severity).
  - Direct fixes only for typos, wrong paths and broken links in `docs/` and `README.md`. Anything that changes a claim or a number is reported, not fixed.
  - A judge's-eye review of README and DEVPOST.md against the Kiroween criteria in `docs/COMPETITION_RULES.md` (Design and Presentation weigh 40%): three concrete suggestions, each with the exact text to change.
- 不许碰的路径: `src/`, `.kiro/`, `scripts/`, `tests/`, `data/`, other worktrees, main/kiro branches.
- 验收清单:
  - [x] Every shot V1a to V7b in VIDEO_SCRIPT.md has a row: reproducible yes/no, with what you saw.
  - [x] Every number in README/DEVPOST/VIDEO_SCRIPT is checked against `docs/MEASUREMENTS.md`; mismatches are listed.
  - [x] No claim "first SAM for seismic" anywhere (grep and report).
  - [x] Whether the 5 s architecture-diagram insert at the end of V4a keeps the video under 3 minutes: your timing estimate.
  - [x] Commit on `feat/ui-docs`. Do not merge. No new numbers invented.
- 截止时间: 2026-11-27

Hard rules: do not log in anywhere; do not upload or post anything; no secrets.

## 回单(完成时由执行者填写)

- 改了哪些文件:
  - `README.md`: 修复表项缺失路径前缀 `src/static/js/`（`survey-map.js`, `refine-panel.js`）及正文中缺失的 `.kiro/specs/` 前缀（`.kiro/specs/qc-refine-loop/tasks.md`）。
  - `docs/VIDEO_SCRIPT.md`: 修复第 78 行插片说明中 HTML 路径缺少 `docs/architecture/` 前缀的问题。
  - `docs/audit/2026-11-24-demo-audit.md`: 新建完整审计报告（包含 V1a~V7b 逐镜实机复验表、所有数值与 MEASUREMENTS.md 对照表、禁用声明核查、5 秒架构插片时长测算、面向评审标准的 3 条具体改写建议）。
  - `tickets/2026-11-24-002-demo-and-docs-audit.md`: 勾选验收清单并填写回单与判定记录。
- 测试结果:
  - `scripts/verify.py` 全部通过 (`VERIFY OK in 14 s`，包含 JS 9/9 语法、Python 15 文件 AST、preflight 全绿、pytest 200 passed、合成数据字节级确定性比对通过)。
  - `scripts/test_refine_e2e.py` 实机 GPU 通过（`PASS`，clean 卷 il 23 成功迭代 3 轮，noisy 卷 il 20 准确触发 `qc_unreliable` 停机）。
  - `git grep -in "first SAM"` 全量核查无违规声称，arXiv 论文引用健全。
- 未解决的问题:
  - 无阻碍性问题。发现 README/DEVPOST 测试步骤中叙述的开机首切片为 "inline 1"，而实机代码为居中加载 "Inline 25 (index 24)"；虽不影响用户按提示输入 20 跳转，但属文实不一，已在审计报告与评委建议 3 中提供修改方案，待负责人合入。

## 判定记录

- 问题 / 选项 / 概率 / 最后谁定的:
  - 问题 1: V4a 末尾 5 秒架构图插片是否超时 / 选项 A: 包含插片（170s，保留 10s 余量）选项 B: 放弃插片（165s）/ 概率: A 95% / 最后谁定的: aux-antigravity 实测推荐采用选项 A，强化 Design 与 Tech Implementation 得分。
  - 问题 2: 文档中涉及事实偏差的文字（如 inline 1 与 Devpost 相对链接）是直接修改还是审计汇报 / 选项 A: 仅修复 typo 与路径缺失，事实与声称性文案仅汇报建议 选项 B: 直接全部改动 / 概率: A 100% / 最后谁定的: aux-antigravity 严格遵守 ticket 指令“Direct fixes only for typos, wrong paths and broken links... Anything that changes a claim or a number is reported, not fixed”。
