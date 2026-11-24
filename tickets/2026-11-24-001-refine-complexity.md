# TICKET 2026-11-24-001-refine-complexity

- 指派: aux-codex
- worktree: D:\26tmp\KiroProject\sam-worktrees\sam-codex-sam-seg (branch feat/sam-seg)
- 基线 commit: see `git log -1` after the ff-merge of `kiro` (lead-kiro merged it before dispatch)
- 目标(一句话): Reduce the cyclomatic complexity of `refine_service.run` (24) and `sam_service.predict_mask_np` (21) by extracting helper functions, with identical behavior.
- 输入:
  - `src/refine_service.py`, `src/sam_service.py`
  - Existing tests under `tests/` (test_refine_service.py, test_sam_service.py, test_refine_api.py, test_qc_service*.py)
  - Analysis baseline `docs/analysis/baseline-py.json`
- 输出: Refactored code in `src/` only; any new focused tests in `tests/`.
- 不许碰的路径: `.kiro/`, `docs/`, `README.md`, `src/static/`, `scripts/measure_*.py`, `data/`, anything outside this worktree, main/kiro branches.
- 验收清单:
  - [ ] No change to public function signatures, return values, API responses, thresholds or constants.
  - [ ] `python -m pytest tests -q` passes (report the exact pass count before and after).
  - [ ] `python scripts/verify.py` prints VERIFY OK (if SAM weights are missing and it cannot run, say so; do not fake it).
  - [ ] `node D:\26tmp\KiroProject\_archify\archify\bin\archify.mjs code-analysis check . --language py --baseline docs/analysis/baseline-py.json --new-only --fail-on warning --out %TEMP%\ca-codex` exits 0, and the two target functions now report lower complexity (paste before and after numbers).
  - [ ] Commit on `feat/sam-seg` with a clear message. Do not merge.
- 截止时间: 2026-11-26

Hard rules: no invented numbers; no secrets; do not alter any measured number in `docs/MEASUREMENTS.md`; do not run training.

## 回单(完成时由执行者填写)

- 改了哪些文件: `src/refine_service.py` 提取输入校验和单轮评分记录；`src/sam_service.py` 提取掩码数据校验和置信度计算。公开签名、返回结构、阈值和常量保持原样。基线为 `2b45b8b`。
- 测试结果: 共享 Python 3.12 环境运行 `python -m pytest tests -q`，重构前后均为 `199 passed, 1 skipped, 1 warning`。Archify 按工单命令退出 0，输出 `PASSED: no open finding at or above warning among new findings.` 两个函数的圈复杂度分别为 `refine_service.run` 24 → 14、`sam_service.predict_mask_np` 21 → 5。Preflight 输出 `OK    kiro`、`OK    claims`、`OK    data`。通过 `--out` 在 worktree 临时目录生成的两套合成数据均通过 `--verify-only` 字节级校验，临时文件已清理。
- 未解决的问题: 默认路径缺少两套演示数据，`scripts/verify.py` 的结果为 `VERIFY FAILED at step 5: Demo data`，默认路径的 `--verify-only` 也因缺数据退出。工单禁止写入 `data/`。本 worktree 也缺少 SAM 权重，未运行 GPU 端到端测试。

## 判定记录

- 问题 / 选项 / 概率 / 最后谁定的:
