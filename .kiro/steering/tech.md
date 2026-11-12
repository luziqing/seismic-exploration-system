---
inclusion: always
---

# Technology Stack

## Backend

- Python 3.10+, FastAPI + uvicorn, NumPy `<2.0`, SciPy (`ndimage` for propagation prompts), Pillow, matplotlib (headless `Agg`).
- SAM inference via `src/sam_service.py`. Weights (`sam3.pt` or equivalent) are **never committed**; load from `data/weights/` at runtime and degrade to a documented CPU / no-weight mode.
- SAM calls: encode each image once under `torch.inference_mode()` and reuse the cached features for every prompt (Ultralytics `set_image` does not disable autograd on its own). All predictor access goes through `sam_service`'s lock; do not call `_model.predict` directly from other modules.
- Persistence: SQLite (`src/database.py`) with a localStorage crash-recovery layer in the browser.
- Optional LLM interpretation assist (`src/llm_service.py`, `src/static/js/llm-client.js`). Must be optional — the app must work with no API key.

## Frontend

- Static `index.html` + vanilla ES modules in `src/static/js/`, Canvas rendering in `canvas.js`, CSS in `src/static/css/`.
- No build step, no npm toolchain required for the core UI. Keep it that way unless a spec says otherwise.

## Seismic volume format (SGSeg-compatible)

`data/npy/<volume_name>/amplitude.npy` — C-order `float32`, shape `[nIL, nXL, nSamples]`.
`data/npy/<volume_name>/meta.json` — required keys: `source_file`, `il_range`, `xl_range`, `ilines`, `xlines`, `samples`, `n_inlines`, `n_crosslines`, `n_samples`, `dt_us`, `shape`.

Read paths in `src/npy_service.py`: `read_inline(il)` → `(nSamples, nXL)`, `read_crossline(xl)` → `(nSamples, nIL)`, `read_timeslice(t)` → `(nIL, nXL)`.

HTTP API (`src/server.py`):
- `GET /api/npy/list`
- `GET /api/npy/{vol}/meta`
- `GET /api/npy/{vol}/slice/inline/{i}` (binary float32)
- `GET /api/npy/{vol}/slice/crossline/{j}`
- `GET /api/npy/{vol}/slice/timeslice/{k}`
- All three accept `?mode=raw|lowfreq` (default `raw`). `lowfreq` applies `lowfreq_service` along the time axis using `dt_us` from `meta.json`; a timeslice filters every trace first (volumes up to 256 MB). Same binary contract either way.

- `POST /api/npy/{vol}/embed` `{direction, index, mode}` — the server renders the slice (grey 2–98 % stretch, uniform integer upscale) and embeds it for SAM; returns `embedding_id`, `image_size`, `scale`, `grid_shape`. The UI must use this for NPY volumes and never embed a canvas screenshot (it carries pick markers and overlays; bug B1).

Volume mask and propagation (spec: `.kiro/specs/volume-propagation/`):
- `POST /api/npy/{vol}/mask` — write one slice's SAM mask into `data/npy/{vol}/masks/<name>.npy` (bool, same shape as the volume) plus `<name>.json` provenance
- `POST /api/npy/{vol}/propagate` — grow a seed slice along its normal axis inside a bounded box
- `GET /api/npy/{vol}/masks`, `GET /api/npy/{vol}/mask/{name}/info`, `GET /api/npy/{vol}/mask/{name}/footprint` (survey map: voxels per trace, binary float32 `(nIL, nXL)`)
- `GET /api/npy/{vol}/mask/{name}/slice/{direction}/{index}` (binary float32 0/1, same orientation as the amplitude slice)

## Planned additions (see the spec)

- `src/lowfreq_service.py` is routed through the slice endpoints (`?mode=lowfreq`); still to do: the UI toggle and side-by-side view (scope S2). Never destroy the original volume — keep the raw slice for comparison.
- `src/qc_service.py`: label-free deep-target QC (edge leakage, envelope contrast) and fault continuity, consumed by a prompt-refinement loop of at most 3 rounds (spec: `.kiro/specs/qc-refine-loop/`). Horizon closure error is deferred (`scope.md` D2).
- `src/validation_service.py` already provides IoU / Dice / Precision / Recall against ground-truth masks. Reuse it; do not re-implement metrics.

## Hard constraints

- Deterministic synthetic data: same seed → byte-identical output. Verify with `--verify-only`.
- No network calls required to generate demo data or render a slice.
- No invented metrics. If a number appears in README or the video, it must be reproducible by a script in `scripts/`.
