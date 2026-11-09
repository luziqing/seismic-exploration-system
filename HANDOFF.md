# HANDOFF — Agent Briefing (Read This First)

**Last updated**: 2026-11-09 · **Maintainer**: niky · **Status**: Wave 1 complete, engineering cleanup done, Wave 2 not started.

## What this project is

SamForGeophysics — a **Kiroween 2026** (Kiro's official Halloween hackathon, Devpost) entry in the **Frankenstein** category: fuse a vision foundation model (SAM) with seismic interpretation so weak deep targets become interpretable. The differentiators are **low-frequency-first conditioning**, a **low-noise "cleaner platform" data variant**, and a **QC-driven self-improving prompt loop** — never a first-of-its-kind claim.

This repository is new (first commit 2026-11-08, no inherited git history). The volume browser / SAM prompt pipeline was adapted from the author's earlier open-source SGSeg project; everything competition-facing (synthetic data, low-frequency spec, QC loop, Kiro workflow) was created inside the submission period. That provenance is disclosed in README's *Eligibility note* — keep it that way.

## Read in this order

1. `AGENTS.md` — non-negotiable rules.
2. `.kiro/steering/` — injected automatically; `product.md`, `tech.md`, `structure.md`, `competition.md` are always-on.
3. `docs/PROJECT_PLAN.md` — full plan (scope, demo storyboard, targets, risks).
4. `.kiro/specs/samforgeophysics-mvp/` — `requirements.md`, `design.md`, and `tasks.md` (live progress; keep checkboxes current).
5. `docs/COMPETITION_RULES.md` and `.kiro/steering/sources.md` — verified facts about the rules and prior work.

## Current state (2026-11-08)

- Local git history only, **not pushed yet**; no remote configured.
- **Wave 1 complete (7/7)**: repo scaffold, `/.kiro` skeleton (3 specs / 6 steering / 3 hooks), deterministic synthetic generator, compliance preflight, data-provenance doc, README "How Kiro was used", rules and citations verified.
- **Wave 2 not started** — this is where work resumes: low-frequency conditioning service, QC service, endpoint wiring, UI toggle.
- Demo volumes `data/npy/synthetic_deep_v1` and `synthetic_deep_v1_clean` exist locally (gitignored, regenerate anytime with the script).

## Hard rules — never break

1. No script, no number. Any quantitative claim must be reproducible by a script in `scripts/` with a fixed seed.
2. Never claim "first SAM for seismic"; prior work is cited in `.kiro/steering/sources.md`.
3. UAV / quantum sensing are background narrative only — never presented as implemented.
4. Public/synthetic data only. No weights, no large volumes, no software-copyright material in git.
5. `/.kiro` stays committed and never appears in `.gitignore` (hooks + preflight enforce this).
6. QC thresholds are declared heuristic constants — never tuned-on-demo then reported as benchmarks.
7. Run both checks below before declaring any task done.

## Code map

| Path | Role |
|---|---|
| `index.html` | Frontend entry (modular, no build step) |
| `src/server.py` | FastAPI routes; serves static + `/api/npy/...` slice endpoints (binary float32) |
| `src/npy_service.py` | Volume store: memmap reads, `meta.json`, `list_volumes` |
| `src/sgy_service.py` / `npy_service.py` / `zarr_service.py` / `vds_service.py` | Upload + alternate volume backends |
| `src/sam_service.py` | SAM loading / embed / predict; weights external at `data/weights/` |
| `src/validation_service.py` | IoU / Dice / Precision / Recall vs ground truth |
| `src/llm_service.py` + `src/static/js/llm-client.js` | Optional LLM interpretation assist (must work without a key) |
| `src/static/js/` — `app.js`, `canvas.js`, `sam-client.js`, `sgy-client.js`, `storage.js` | Toolbar/state, Canvas rendering, SAM client, volume client, persistence |
| `scripts/generate_synthetic_seismic.py` | Deterministic synthetic volumes + truth masks + `--verify-only` |
| `scripts/preflight.py` | Compliance checks called by `.kiro/hooks/*.json` |
| `tests/test_core.py` | Inherited unit tests (require backend deps) |

## Data contract (exact)

- `data/npy/<name>/amplitude.npy` — C-order `float32`, shape `[nIL, nXL, nSamples]`.
- `data/npy/<name>/meta.json` — keys: `source_file`, `il_range`, `xl_range`, `ilines`, `xlines`, `samples`, `n_inlines`, `n_crosslines`, `n_samples`, `dt_us`, `shape` (plus provenance keys on synthetic volumes).
- Reads: `read_inline(i)` → `(nSamples, nXL)`, `read_crossline(j)` → `(nSamples, nIL)`, `read_timeslice(k)` → `(nIL, nXL)`.
- API: `GET /api/npy/list`, `GET /api/npy/{vol}/meta`, `GET /api/npy/{vol}/slice/inline/{i}` (and `crossline/{j}`, `timeslice/{k}`).
- Ground truth: `data/npy/<name>/truth/{fault,horizon,deep_target}_mask.npy` — boolean, same shape.

## Next tasks (Wave 2 — see `tasks.md` for the authoritative list)

1. `src/lowfreq_service.py` — spectral weighting on a 2-D slice; the stored raw volume is never modified.
2. Wire a low-frequency mode into the slice endpoints in `src/server.py`.
3. Low-frequency toggle / raw-vs-conditioned comparison in the frontend.
4. `src/qc_service.py` — fault continuity, horizon closure error; delegate overlap metrics to `validation_service.py`.
5. Focused tests: shape preservation for conditioning; QC behaviour on constructed masks.

## Verify your work

```bash
python scripts/generate_synthetic_seismic.py --verify-only
python scripts/preflight.py --check all
```

Both must pass. `pytest tests/` additionally covers inherited core behaviour once backend dependencies are installed.

## Environment notes

- Windows 11. System Python 3.13 + NumPy 2.5 runs the `scripts/` standalone; the backend pins `numpy<2.0` in `requirements.txt` (the scripts only use stable NumPy APIs, so both work).
- SAM weights are never committed. Missing weights must degrade gracefully: browsing, conditioning and QC remain usable and the UI states what is missing (spec F8).
- Kiro toolchain installed locally: IDE 1.4.121, CLI 3.1.0, Crew 0.12.0. Hooks in `.kiro/hooks/` fire on file-save events and call `scripts/preflight.py`.

## Recent engineering decisions (2026-11-09)

**Cleanup already applied** (commit `70c1b42`) — do not redo:

- Static assets are served only from explicit directories (`/images`, `/static`). Never mount the repository root.
- The frontend has no external CDN dependency; all styles are local files. Keep it that way — the demo must work without internet access.
- Product-facing names (page title, toolbar, footer, dependency header) say SamForGeophysics. SGSeg references in README and steering are deliberate attribution to the earlier technical base and must stay.
- `structure.md`, `design.md` and the `app.js` header now describe the code as it actually is.

**Slice response contract for Wave 2 (fixed):**

- New slice endpoints (for example `?mode=lowfreq`) return **binary `float32` with `X-Rows` / `X-Cols` headers only**, exactly like the existing `/api/npy/...` endpoints. Do not introduce a JSON variant.
- The demo uses the npy volume path exclusively; the older Zarr / VDS JSON endpoints remain for compatibility but are not on the demo path.
- Rationale: one contract means one frontend parser, and the low-frequency view is simply a second presentation of the same slice.

**Verification for Wave 2:** run both commands in "Verify your work" above. Backend dependencies (`fastapi` / `torch`) are not installed on this machine, so `pytest tests/` and a live server run are currently unavailable. Pure-NumPy modules such as `lowfreq_service.py` must be verified standalone with a focused script instead.
