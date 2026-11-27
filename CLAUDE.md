> **Superseded for development work:** read [`guide.md`](guide.md) and `.kiro/steering/scope.md` section 0 first. This file is older (status and plans here may be out of date).

# CLAUDE.md — SamForGeophysics (Kiroween 2026 · Frankenstein)

> For Claude / Kiro agents taking over this project. Positioned the same as `GEMINI.md`, except grounded in **actual code state as of 2026-11-09** and providing the overall plan through the submission deadline.
> Hard rules follow `AGENTS.md` and `.kiro/steering/*.md`; wherever this document conflicts with them, those files govern.

---

## 0. Reading order

1. `AGENTS.md`: non-negotiable rules.
2. `.kiro/steering/`: `product.md` / `tech.md` / `structure.md` / `competition.md` (always included); `seismic-domain.md` (auto-loaded); `sources.md` (manual reference `#sources`).
3. `.kiro/specs/samforgeophysics-mvp/`: `requirements.md` → `design.md` → `tasks.md` (authoritative checklist for task completion).
4. `docs/COMPETITION_RULES.md` (official rule summary verified 2026-11-08), `docs/PROJECT_PLAN.md` (scope, demo storyboard, risks).
5. `HANDOFF.md`, `GEMINI.md`: earlier handoff notes, partly outdated (see §3).

---

## 1. One-sentence project summary

Stitch the vision foundation model SAM onto seismic interpretation using **low-frequency-first conditioning (H1)**, **low-noise "cleaner platform" contrast volumes (H2)**, and a **QC-driven self-improving prompt loop (H3)** so deep weak targets become interpretable. Submitted to the Frankenstein track.

Do not claim novelty as the first SAM for seismic (prior work: arXiv:2407.14121, arXiv:2606.15786). UAV / quantum sensing are background narrative only and were never implemented.

---

## 2. Feature inventory (actual state, 2026-11-09)

Status definitions: **committed** = in git history on the `kiro` branch; **uncommitted** = changes from other agents in the working tree not yet committed; **missing** = no code yet. Measured results are in §2.4.

### 2.1 Data and compliance foundation (Wave 1, committed)

| Feature | Location | Status |
|---|---|---|
| Deterministic synthetic volumes (noisy `synthetic_deep_v1` / low-noise `synthetic_deep_v1_clean`) + ground-truth masks (fault / horizon / deep_target) | `scripts/generate_synthetic_seismic.py` | Committed, byte-level check via `--verify-only` |
| Compliance preflight checks (`.kiro` visibility, forbidden claims, data provenance) | `scripts/preflight.py` | Committed |
| 3 hook files (all `PostFileSave`, invoking preflight / generator verification, plus 1 agent prompt) | `.kiro/hooks/*.json` | Committed |
| 1 spec + 6 steering files | `.kiro/specs/`, `.kiro/steering/` | Committed |
| Unified npm scripts (`start` / `test` / `check` / `data:*` / `preflight`), port 9339 | `package.json`, `scripts/run.js` | Committed |
| Auto-load volume on first open + volume switcher | Frontend | Committed (`f0ad826`) |

### 2.2 Interpretation platform inherited from SGSeg (committed)

| Feature | Location |
|---|---|
| npy volume browsing: inline / crossline / timeslice, binary float32 + `X-Rows`/`X-Cols` | `src/npy_service.py`, `src/server.py` |
| SEG-Y upload & conversion; Zarr / VDS fallback backends (not on the demo path) | `src/sgy_service.py`, `zarr_service.py`, `vds_service.py` |
| SAM embedding + point-prompt inference (`/api/embed`, `/api/predict`, `/api/status`, `/api/devices`) | `src/sam_service.py`, `src/static/js/sam-client.js` |
| Picking, GeoJSON/CSV export & import, SQLite sessions + localStorage crash recovery | `src/database.py`, `src/static/js/storage.js` |
| IoU / Dice / Precision / Recall | `src/validation_service.py` |
| Optional LLM interpretation assistant (must still start without an API key) | `src/llm_service.py`, `llm-client.js` |

### 2.3 Wave 2 and beyond (mostly uncommitted or missing)

| Feature | Location | Status |
|---|---|---|
| Low-frequency conditioning: 1D RFFT along time axis × cosine taper weights (full pass ≤14 Hz, attenuated to 0.05 ≥30 Hz) × IRFFT | `src/lowfreq_service.py`, `tests/test_lowfreq.py` | **Uncommitted**; checked off in `tasks.md`; **not yet wired into any endpoint or UI** |
| Volume mask: project SAM 2D masks back onto volume grid, stored under `data/npy/<vol>/masks/` | `src/volume_mask_service.py`, `tests/test_volume_mask.py` | Committed (`5d7499f`); spec in `.kiro/specs/volume-propagation/` |
| Cross-slice propagation: generate point prompts automatically from previous mask, run slice-by-slice inference, IoU anti-drift guard | `src/propagation_service.py`, `tests/test_propagation.py` | Committed (`5d7499f`); same spec; adds `scipy` dependency |
| Volume mask / propagation API: `POST /api/npy/{vol}/mask`, `POST .../propagate`, `GET .../masks`, `GET .../mask/{name}/info`, `GET .../mask/{name}/slice/{dir}/{i}` | `src/server.py` | **Uncommitted** |
| Frontend "🔁 Propagate" button + range panel; SAM results auto-saved into volume mask | `index.html`, `sam-client.js` | **Uncommitted** |
| `?mode=raw|lowfreq` slice parameter | `src/server.py`, `tests/test_slice_modes.py` | Implemented (11-12, scope S1) |
| Raw / Low-freq toggle and side-by-side comparison | `src/static/js/compare.js` | Implemented (11-12, scope S2) |
| Noisy / Clean one-click comparison (UI expression of H2) | `src/static/js/compare.js` | Implemented (11-12, scope S2: one-click toggle + side-by-side compare) |
| `qc_service.py`: fault continuity, horizon closure error | — | **Missing** |
| Self-improving loop (≤3 rounds, early stopping, keep best round, per-round log API + UI panel) | — | **Missing** (H3, demo highlight) |
| Reproducible measurement scripts (source of any public numbers) | `scripts/measure_lowfreq.py`, `docs/MEASUREMENTS.md` | H1/H2 implemented (11-12, scope S3); H3 pending S5 |
| Publicly reachable live instance | — | **Missing** |
| English UI | Frontend | **Missing** (buttons and status copy mostly in Chinese) |

### 2.4 Measured test results (2026-11-09, local RTX 4090 D)

Environment: `.venv` has Python 3.12.7, NumPy 1.26.4, FastAPI 0.137.0, torch 2.6.0+cu124 (CUDA available), scipy 1.17.1. The note in `HANDOFF.md` saying "fastapi / torch not installed on this machine" is outdated.

| Check | Result |
|---|---|
| `npm run check` (JS syntax + Python AST + preflight) | Passed |
| `npm test` (preflight + data determinism check) | Passed |
| `pytest tests` under `.venv` | 79 passed (including the three new test files) |
| Server startup `python src/server.py` (port 9339) | OK; only warns that openvds is not installed (not on demo path) |
| `GET /api/npy/list` | Returns both synthetic volumes, 48×48×256 |
| Three slice endpoints | 200; inline / crossline are 256×48, timeslice is 48×48, all binary float32 |
| `scripts/test_sam_inference.py` (5 inlines, embed → predict → write volume mask → read back) | Passed. Single embed ~7.5 s (first 14.7 s including model load), single predict ~3 s |
| `POST /api/npy/{vol}/propagate` (seed inline 20, ±2) | First run: returned 200, but mask was empty with no slices written, elapsed 32 s. **After fix**: `scripts/test_propagation_e2e.py` passed completely (see item 1 below) |

Issues observed from live measurements (internal record only; do not advertise any unscripted numbers publicly):

1. ~~Propagation unusable in practice~~ **Fixed (11-09 evening)**: Same root cause as item 2. After fixing, `scripts/test_propagation_e2e.py` writes 10 non-empty slices within ±5 of the seed in ~3 s. The `total_voxels` change is not a bug: the second phase of that script re-seeds on the same mask, overwriting the seed slice.
2. ~~High SAM latency~~ **Fixed (11-09 evening)**: Ultralytics `Predictor.set_image` ran outside `inference_mode`, keeping the entire autograd graph attached to cached encoder features (~35 GB VRAM for a single embedding). `sam_service._encode_image` is now wrapped in `torch.inference_mode()`, with a regression test in `tests/test_sam_service.py`. After the fix, in-process embed is ~0.3 s and cached predict is ~0.04 s; HTTP predict is ~0.4 s, with the extra time mostly spent JSON-serializing the 1024×768 mask. Also, the test scripts originally used `localhost`, which on Windows added ~2 s per request trying IPv6 first; both e2e scripts were switched to `127.0.0.1`.
3. **Unstable SAM coverage on weak targets**: per-slice IoU is roughly 0.34–0.60, and masks spread laterally across the full XL range (0–47). This is exactly what H1 and H3 aim to improve, but improvement must only be measured using fixed-seed scripts.
4. **`GET /api/npy/list` returns server-local absolute paths** (`path` field). Should be removed before public exposure.

---

## 3. Known inconsistencies (handle first when taking over)

1. **Stale documentation**: `README.md` Honest status still lists low-freq as "not yet implemented"; `HANDOFF.md` says "Wave 2 not started" and "3 specs" when there is only 1 spec; `GEMINI.md` does not mention volume masks or propagation.
2. ~~Scope drift~~ **Resolved (A2)**: Volume mask + cross-slice propagation now have spec `.kiro/specs/volume-propagation/` (backfilled, remaining work listed in its `tasks.md`).
3. **Dependencies and conventions**: `scipy`, new endpoints, and new modules are registered in `tech.md` / `structure.md`. Comments and error messages in `propagation_service.py` / `volume_mask_service.py` are still in Chinese (slotted into Wave 5 of volume-propagation).
4. **Checked low-freq items in `tasks.md` only cover the service layer**; endpoint and UI items remain unchecked, which is accurate. Do not check them before verification.
5. **Uncommitted changes were partially verified** (§2.4): static checks, 79 tests, slice endpoints, and the SAM → volume mask path all pass; **the propagation path failed in live testing**. Unit tests missed this because `test_propagation.py` did not cover coordinate mapping from real SAM outputs. `.venv` already has full backend dependencies; environment notes in `HANDOFF.md` are outdated.
6. **Preflight's forbidden-claim scan does not cover `CLAUDE.md` / `GEMINI.md`** (it only scans README, AGENTS, HANDOFF, docs, steering, and specs). Both files live in the public repo and should be added to the scan targets.
7. Another copy `../SamForGeophysics-kiro-handoff/` exists under the workspace root, producing duplicate search hits. Edit only `SamForGeophysics/`.

---

## 4. Hard rules (summary; full text in `AGENTS.md`)

- No script, no numbers. Public numbers must be reproduced by a fixed-seed script in `scripts/` and qualified as obtained on this synthetic model with declared heuristic thresholds.
- Never claim this is the first SAM for seismic; do not present UAV / quantum sensing as implemented.
- Only public or synthetic data in git. Files under `data/` such as `mig304.sgy`, `inp001/`, `uploads/`, and `weights/` stay local only and are never committed.
- `/.kiro` must stay committed and never enter `.gitignore` (instant disqualification).
- QC thresholds are declared heuristic constants; never tune parameters on the demo volume and report them as a benchmark.
- Slice endpoints only return binary float32 + `X-Rows`/`X-Cols`; do not add JSON variants.
- No frontend build step and no external CDNs; serve static assets only from `/images` and `/static`.
- When weights, network, or API keys are missing, browsing, conditioning, and QC must remain functional, with the UI clearly stating what is missing.

---

## 5. Development plan and boundaries

**`.kiro/steering/scope.md` is authoritative** (established 2026-11-12 from the full official rules PDF; always included). Key points:

- Delivery format: **test build** (public repository + testing instructions), not a hosted public instance; rules allow "a website, functioning demo, or a test build". Project must remain runnable until judging ends on **2027-01-29**.
- Scope: feature items S1–S12 + stability/executability items E1–E7; volume mask and propagation are frozen; see scope §3.3 for the explicit "out of scope" list.
- Milestones (Beijing time): M1 H1/H2 11-16 → M2 H3 11-23 → M3 productization + test build 11-29 → **11-30 feature freeze** → M4 12-03 submission, with 12-04 kept as buffer only.
- Kiro usage writeup must answer the 8 official questions (IDE/CLI/Web/Crew, custom agents, hooks, spec-driven flow, steering, MCP, PBT, powers) and describe only what was genuinely used.

## 6. Decisions requiring the owner

See `scope.md` §8 (decisions) and §9 (owner-only items: confirm SGSeg attribution, apply for Kiro credits, make repository public, SAM3 weights acquisition path, second machine verification, YouTube and Devpost).

---
## 7. Interfaces and data contracts (do not modify)

- Volume: `data/npy/<name>/amplitude.npy`, `float32`, C-order, `[nIL, nXL, nSamples]`; metadata `meta.json`; ground truth `truth/{fault,horizon,deep_target}_mask.npy` (bool, same shape).
- Reads: `read_inline(i)` → `(nSamples, nXL)`, `read_crossline(j)` → `(nSamples, nIL)`, `read_timeslice(k)` → `(nIL, nXL)`.
- Slices: `GET /api/npy/{vol}/slice/{inline|crossline|timeslice}/{idx}[?mode=raw|lowfreq]`, binary float32 + `X-Rows` / `X-Cols`.
- Volume mask: `data/npy/<vol>/masks/<name>.npy` (bool, same shape) + `<name>.json` (per-slice provenance log). Write only to `masks/`; never overwrite `amplitude.npy`.

---

## 8. Required checks before finishing

```bash
npm run check                                   # JS syntax + Python AST + preflight
npm test                                        # preflight + data determinism verification
.venv\Scripts\python.exe -m pytest tests -q     # full unit test suite (.venv has backend deps)
# When touching SAM / volume masks, start the server and run end-to-end smoke tests:
.venv\Scripts\python.exe src/server.py
.venv\Scripts\python.exe scripts/test_sam_inference.py   # writes test masks under data/npy/<vol>/masks/; delete after running
```

Equivalent direct commands: `python scripts/generate_synthetic_seismic.py --verify-only` and `python scripts/preflight.py --check all`. Work may only be declared done after both pass and `tasks.md` is updated accordingly.
