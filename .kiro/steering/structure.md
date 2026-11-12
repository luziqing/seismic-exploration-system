---
inclusion: always
---

# Project Structure

```
SamForGeophysics/
├── .kiro/                     # MUST be committed, never in .gitignore
│   ├── specs/                 # requirements.md / design.md / tasks.md per feature
│   ├── steering/              # this directory: product / tech / structure / ...
│   └── hooks/                 # standalone v1 JSON hooks, auto-activated
├── index.html                # frontend entry
├── src/
│   ├── server.py              # FastAPI routes, thin routing layer
│   ├── sam_service.py         # SAM loading, embed (cached encoder features), predict
│   ├── npy_service.py         # memmap volume reads + meta.json
│   ├── lowfreq_service.py     # low-frequency spectral weighting of a 2-D slice (not yet routed)
│   ├── volume_mask_service.py # 2-D SAM mask -> 3-D voxel mask under data/npy/<vol>/masks/
│   ├── propagation_service.py # cross-slice SAM propagation inside a bounded box
│   ├── sgy_service.py         # SEG-Y upload / conversion
│   ├── sgy|npy|zarr|vds_*     # alternate volume backends
│   ├── validation_service.py  # IoU / Dice / Precision / Recall
│   ├── database.py            # SQLite schema and persistence
│   ├── llm_service.py         # optional interpretation assist
│   └── static/{css,js}/       # Canvas UI, SAM client, survey map, raw/low-freq + noisy/clean compare, storage, LLM chat
├── scripts/
│   ├── generate_synthetic_seismic.py   # deterministic public-domain demo data
│   ├── preflight.py                    # hooks-backed compliance checks
│   ├── run.js                          # npm script runner (picks .venv python)
│   └── test_sam_inference.py, test_propagation_e2e.py   # GPU end-to-end checks; need a running server and weights
├── docs/
│   └── DATA_PROVENANCE.md     # where demo data comes from, and its licence
├── tests/
├── requirements.txt
├── package.json / .env.example
├── LICENSE                    # MIT
└── README.md
```

## Conventions

- Python: `snake_case`, module-level logger `logging.getLogger("sam3-server")`, type hints on public functions.
- JS: classic scripts (no `type="module"`) loaded in a fixed order from `index.html`; modules share `window`-level state. `camelCase`, no framework, no build step.
- Volume names: lowercase `snake_case`; synthetic volumes prefixed `synthetic_`.
- New backend modules are thin, single-purpose services imported by `server.py`; keep route handlers thin.
- Generated artefacts go under `data/` and are gitignored. Only scripts and small text metadata belong in git. Volume masks live in `data/npy/<vol>/masks/`; never write next to or over `amplitude.npy`.
- Do NOT copy anything from `doc/` (software-copyright application material) or from `data/weights/` into the public repository.

## Adding a feature

Follow `.kiro/specs/<feature>/` three-phase flow: requirements → design → tasks. Update `tasks.md` checkboxes as work lands. Run `python scripts/preflight.py --check all` before declaring done.
