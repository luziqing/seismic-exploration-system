# Implementation Plan — SamForGeophysics MVP

> Update checkboxes as tasks land. Waves group independent work; Kiro can run tasks inside a wave in parallel.

## Wave 1 — Foundation (no dependencies)

- [x] Create a new public-repo-ready project with no inherited git history
- [x] Commit a substantive `/.kiro` skeleton (specs, steering, hooks)
- [x] Add `.gitignore` that explicitly keeps `/.kiro` tracked
- [x] `scripts/generate_synthetic_seismic.py` — deterministic synthetic volume, `meta.json`, truth masks, `--verify-only` (done 2026-11-08; byte-identical verification passing)
- [x] `scripts/preflight.py` — `kiro` / `claims` / `data` / `all` checks (done 2026-11-08; all three checks green)
- [x] `docs/DATA_PROVENANCE.md` and README "How Kiro was used" section (done 2026-11-08)
- [x] Verify prior-work citations and competition dates (`#sources`) (done 2026-11-08; official Devpost rules and both arXiv papers verified — see `docs/COMPETITION_RULES.md`)

## Wave 2 — Conditioning and QC (depends on Wave 1 generator)

- [x] `src/lowfreq_service.py` — spectral weighting on a 2-D slice, raw volume preserved (done 2026-11-09)
- [ ] Wire low-frequency mode into `src/server.py` slice endpoints
- [ ] Add low-frequency toggle / comparison in `src/static/js/`
- [ ] `src/qc_service.py` — label-free deep-target QC (edge leakage, envelope contrast) + fault continuity; ground-truth overlap via `validation_service.py` reported only (scope D2; details in `.kiro/specs/qc-refine-loop/`)
- [ ] Focused tests for shape preservation and QC behaviour on constructed masks

## Wave 3 — Self-improving loop (depends on Wave 2)

- [ ] Prompt-refinement driver: worst-region localisation, corrective point/box, max 3 rounds, early stop
- [ ] Persist round log and expose it via an API endpoint
- [ ] Render round-by-round QC panel in the UI

## Wave 4 — Product polish (depends on Wave 3)

- [x] Demo-friendly default state: synthetic volume loaded on first open (done 2026-11-09, `f0ad826`)
- [ ] Graceful no-weight / no-API-key path with visible status
- [ ] Visual pass on canvas, toolbar and QC panel (Design, 20%)
- [ ] Export flow end-to-end check (GeoJSON + CSV)

## Wave 5 — Submission (depends on Wave 4)

- [ ] <3 minute video script and public YouTube upload
- [ ] README: Kiro usage evidence, honest claims, reproducible numbers
- [ ] `python scripts/preflight.py --check all` clean
- [ ] Final hard-requirement checklist in `#competition` all ticked
- [ ] Submit before Dec 4, 14:00 PT (Dec 5, 06:00 Beijing)

## Explicitly out of scope

- UAV hardware, quantum sensing hardware, and any claim that they were built.
- Fine-tuning SAM on field data (requires proprietary data and is not needed for the Frankenstein angle).
- Any accuracy benchmark not reproducible by a script in this repo.
