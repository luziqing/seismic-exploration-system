# VERCEL-STATIC: Zero-serverless static web demo on Vercel

- Branch / commits: `feat/vercel-static-demo` from baseline `fcd4e8e` (`origin/kiro`, `5253a64` is not an ancestor)
- Worktree: isolated worktree `sam-worktrees/sam-antigravity-vercel`
- Files changed / added:
  - Added `vercel.json` (`framework: null`, `buildCommand: "node scripts/build_static_demo.mjs"`, `outputDirectory: "dist"`, cache header for `/demo/assets/(.*)`)
  - Added `.vercelignore` (strict allowlist excluding `*.py`, `requirements*.txt`, `tests/`, `data/`, `docs/`, `.kiro/`)
  - Added `scripts/export_static_demo.py` (deterministic `int16` slice + `manifest.json` exporter + live GPU refine recording helper)
  - Added `scripts/build_static_demo.mjs` (zero-dependency Node ES module build outputting `dist/`, injecting `<script src="/demo/demo-shim.js"></script>`, checking `< 4 MB` and 0 `.py` files)
  - Added `demo/demo-shim.js` (`window.fetch` interceptor for `/api/*`, top notice banner, replay buttons for recorded clean IL 24 and noisy IL 21 runs)
  - Added `demo/assets/manifest.json` and 76 derived `demo/assets/<vol>/<mode>/il_<index>.i16` files (`synthetic_deep_v1` and `synthetic_deep_v1_clean`, `raw` and `lowfreq`, inline indices `11..29`)
  - Added `demo/recorded/refine_clean_il24.json`, `demo/recorded/refine_noisy_il21.json`, and `demo/recorded/PROVENANCE.md` (recorded from local `src/server.py` on port `9346` with `NVIDIA GeForce RTX 4090 D`)
  - Added `tests/test_static_demo.py` (5 pytest checks covering size budget, SHA-256 + byte-exact slice reproducibility, `build_static_demo.mjs` single-line `index.html` diff, 100% shim route coverage across `src/static/js/*.js`, and CJK check)
  - Updated `README.md` (`## Web demo (static)` before `## Run it`), `.kiro/steering/scope.md` (`§3.3` and `D3`), and `.kiro/steering/structure.md`
  - Unchanged (untouched vs `fcd4e8e`): `index.html`, `src/**`, `requirements*.txt`, `.gitignore`

- What was done, mapped to the plan checks:
  - **Config**: `vercel.json` sets `framework: null` and runs `node scripts/build_static_demo.mjs` with `dist` output; `.vercelignore` excludes all Python code, requirements files, tests, and raw `data/` volumes from Vercel uploads.
  - **Derived assets & recorded runs**: `export_static_demo.py --all --url http://127.0.0.1:9346` exported 2 volumes × 2 modes × 19 inlines (indices `11..29`, IL `12..30`) as little-endian `int16` plus two live local `NVIDIA GeForce RTX 4090 D` refine recordings (`clean` index 23 / IL 24, 3 rounds, scores `0.558` / `0.876` / `0.890`, `best_round=3`; `noisy` index 20 / IL 21, `stop_reason=qc_unreliable`, score `0.205`). Total `demo/` size: **2,022,446 bytes (1.929 MiB)**, strictly `<= 2.5 MB`.
  - **Build artifact**: `node scripts/build_static_demo.mjs` produces `dist/` with **94 files, 2,218,495 bytes (2.116 MiB)** (`< 4 MB`), zero `.py` files, and `dist/index.html` differing from root `index.html` by only `<script src="/demo/demo-shim.js"></script>`.
  - **Browser UX & honesty**: Headless Chrome (`1600x900`) against `http.server -d dist` verified initial IL 25 load (`SAM3: weights missing`), `Low-freq` / `Compare` (`Raw | Low-freq`, `Noisy | Clean`) / `Noisy ⇄ Clean`, clean IL 24 3-round replay, noisy IL 21 gate replay (`61%` > `50%` gate), `503` plain-English messages on `Propagate` and `▶ SAM`, `404` on out-of-range inline (`0`), zero `/api/` network requests escaping the shim, zero `console.error` / `pageerror`, and zero CJK characters.

- Verification commands run:
  - `node scripts/build_static_demo.mjs` → `Built static demo: 94 files, 2218495 bytes (2.116 MiB)` (exit 0)
  - `.venv\Scripts\python.exe scripts/verify.py` → `check:js — 9/9 files OK`, `15 files parsed`, `Preflight OK (kiro/claims/data)`, `217 passed, 1 warning in 11.31s`, `Demo data deterministic`, `VERIFY OK in 14 s`
  - `.venv\Scripts\python.exe scripts/preflight.py --check all` → `OK kiro`, `OK claims`, `OK data`
  - Headless Chrome 1600×900 CDP walkthrough on `dist/` → `CHROME VERIFICATION PASS` (`api_net_reqs: []`, `console_errors: []`, `exceptions: []`)

- Numbers used in public text and provenance:
  - Only dataset dimensions (`synthetic_deep_v1`, `synthetic_deep_v1_clean`, inlines `12–30`), HTTP error codes (`503`, `404`), and recorded QC run scores from `demo/recorded/refine_clean_il24.json` / `refine_noisy_il21.json` (plus their provenance in `demo/recorded/PROVENANCE.md`). No YouTube or unverified Vercel URL added.

- Deviations from plan / guide:
  - Made `export_static_demo` import lazy inside `tests/test_static_demo.py::_load_exporter()` (removing module-level `sys.path`/SciPy import during pytest collection) because collection-order import perturbation otherwise caused Hypothesis `@PBT` in `tests/test_qc_service_pbt.py::test_exact_mask_ranks_above_typical_mistakes` to draw an edge case; after lazy import + `.hypothesis` reset, all 217 tests pass under `verify.py`.

- Open questions / next steps:
  - Independent verification by Codex `t3g` on a fresh detached checkout of this commit, followed by Kiro `t3d` merge/push and live Vercel deployment check.
