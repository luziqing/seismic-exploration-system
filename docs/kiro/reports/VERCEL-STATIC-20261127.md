# VERCEL-STATIC: Zero-serverless static web demo on Vercel

- Branch / commits: `feat/vercel-static-demo` from baseline `fcd4e8e` (`origin/kiro`, `5253a64` is not an ancestor; includes initial `4d456f9` plus full-inline revision commit)
- Worktree: isolated worktree `sam-worktrees/sam-antigravity-vercel`
- Files changed / added:
  - `vercel.json`: `framework: null`, `installCommand: "echo \"static demo: no install\""`, `buildCommand: "node scripts/build_static_demo.mjs"`, `outputDirectory: "dist"`, cache header for `/demo/assets/(.*)`
  - `.vercelignore`: strict allowlist excluding `*.py`, `requirements*.txt`, `tests/`, `data/`, `docs/`, `.kiro/`
  - `scripts/export_static_demo.py`: exports all 48 inlines (`0..47`) for both synthetic volumes (`synthetic_deep_v1`, `synthetic_deep_v1_clean`) in both `raw` and `lowfreq` modes (`192` `.i16` files, 24,576 B each) + `manifest.json`, and records local GPU refine runs (`<= 6 MB` ceiling)
  - `scripts/build_static_demo.mjs`: zero-dependency Node build outputting `dist/`, injecting `<script src="/demo/demo-shim.js"></script>` into `index.html`, enforcing `0` `.py` files and `< 8 MB` total size
  - `demo/demo-shim.js`: intercepts `/api/*` in `window.fetch`, lazily loads and caches requested `.i16` inline slices on demand, assembles any `crossline` or `timeslice` (`raw` and `lowfreq`) in-browser from the cached inlines, returns honest `503` / out-of-range `404` JSON responses, injects the top demo banner and replay controls (`clean` IL 24 and `noisy` IL 21)
  - `demo/assets/manifest.json` + 192 `.i16` files (`demo/assets/<vol>/<mode>/il_0..47.i16`)
  - `demo/recorded/refine_clean_il24.json`, `demo/recorded/refine_noisy_il21.json`, `demo/recorded/PROVENANCE.md` (standalone GPU run provenance with exact `[nx, ny]` click coordinates and trailing-digit variance note)
  - `tests/test_static_demo.py`: checks size budgets (`demo/ <= 6 MB`, `dist/ < 8 MB`), SHA-256 + byte-level inline reproducibility, exact crossline & timeslice equality between inline-stitched `int16`/`float32` slices and quantized `npy_service`/`lowfreq_service` outputs, `build_static_demo.mjs` single-line `index.html` diff, 100% shim route coverage across `src/static/js/*.js`, and zero CJK
  - `README.md`, `.kiro/steering/scope.md`, `.kiro/steering/structure.md`: updated static web demo scope, `demo/` (`<= 6 MB`) convention, and `D3` approval note
  - Unchanged vs `fcd4e8e`: `index.html`, `src/**`, `requirements*.txt`, `.gitignore`

- Verification summary (re-run on final HEAD):
  - `demo/` total size: `4,902,937` bytes (`4.676 MiB <= 6 MB`)
  - `node scripts/build_static_demo.mjs`: `Built static demo: 210 files, 5098986 bytes (4.863 MiB)` (`< 8 MB`, `0` `.py` files, 1-line `index.html` diff)
  - `.venv\Scripts\python.exe scripts/verify.py`: `218 passed, 1 warning`, `VERIFY OK`
  - `.venv\Scripts\python.exe scripts/preflight.py --check all`: `OK kiro`, `OK claims`, `OK data`
  - Headless Chrome (`1600x900` CDP against `dist/`): verified lazy initial IL 25 load (1 `.i16` fetched upfront), slider sweep to IL 1 and IL 48, crossline `raw` + `lowfreq` + `Compare`, timeslice `raw` + `lowfreq` + `Compare`, out-of-range inline `48` returning `404`, clean & noisy replay runs, `503` messages on `Propagate` / `▶ SAM`, zero `/api/` network leaks, zero console/page errors, zero CJK
