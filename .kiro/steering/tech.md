---
inclusion: always
---

# Technology Stack

## Backend

- Python 3.10+, FastAPI + uvicorn, NumPy `<2.0`, Pillow, matplotlib (headless `Agg`).
- SAM inference via `src/sam_service.py`. Weights (`sam3.pt` or equivalent) are **never committed**; load from `data/weights/` at runtime and degrade to a documented CPU / no-weight mode.
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

## Planned additions (see the spec)

- `src/lowfreq_service.py`: band-pass / spectral weighting that emphasises the low-frequency band before SAM prompting. Never destroy the original volume — keep the raw slice for comparison.
- `src/qc_service.py`: fault continuity and horizon closure error, consumed by a 2–3 round prompt-refinement loop.
- `src/validation_service.py` already provides IoU / Dice / Precision / Recall against ground-truth masks. Reuse it; do not re-implement metrics.

## Hard constraints

- Deterministic synthetic data: same seed → byte-identical output. Verify with `--verify-only`.
- No network calls required to generate demo data or render a slice.
- No invented metrics. If a number appears in README or the video, it must be reproducible by a script in `scripts/`.
