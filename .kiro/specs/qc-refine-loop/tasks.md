# Implementation Plan — QC-Driven Self-Improving Prompt Loop (H3)

> Written before the code (2026-11-12). Scope items S4–S6 in `.kiro/steering/scope.md`; milestone M2, due Mon 11-23. Tick a task only when its check passes, and note the date. If a declared constant has to change, record the old value, the new value, the reason and the before / after output here.

## Wave 0 — Test tooling

- [ ] Add `requirements-dev.txt` (`pytest`, `hypothesis`) and document it in the README run section. Check: `pip install -r requirements-dev.txt` in the `.venv`, `pytest tests` still green

## Wave 1 — QC service (S4; Requirements 1, 2) — due 11-19

- [ ] `src/qc_service.py`: envelope, ring, `contrast_db`, `leak`, `miss`, composite `score`, leak / miss maps, declared constants returned with every result; empty / full / no-ring cases return score 0 with a reason
- [ ] Fault continuity: per-row presence and centre shift, `continuity`, `fragments`, fault score
- [ ] `tests/test_qc_service.py`: constructed slices — exact mask beats mask + background, mask − part of target, empty, full; fault score drops with a gap and with a fragment; time-slice fallback labelled `abs`
- [ ] `tests/test_qc_service_pbt.py` (`hypothesis`): adding background pixels never raises the score; removing target pixels next to an exact mask never raises it; score in `[0, 1]`; same input → same output. Record any bug PBT finds that the unit tests missed (for the README PBT answer)

## Wave 2 — Loop driver (S5; Requirement 3) — due 11-20

- [ ] `src/refine_service.py`: `run(...)` with injectable `segment_fn`; correction at the interior point of the larger of the largest leak / miss regions; stops `max_rounds`, `no_gain`, `nothing_to_fix`, `empty_mask`; best round = highest score, earliest on ties; embed once
- [ ] Truth overlap per round through `validation_service`, stored as `truth_reference`, never read by the driver
- [ ] `tests/test_refine_service.py` with stub segmenters: correction sign, round limit, each stop reason, best round kept when a later round is worse, one embed, driver does not touch truth (stub raises if read)

## Wave 3 — API and persistence (S5; Requirement 4) — due 11-21

- [ ] SQLite tables `refine_runs`, `refine_rounds` (RLE masks) in `src/database.py`, with insert and read-back
- [ ] `POST /api/npy/{vol}/refine` and `GET /api/refine/{run_id}`; normalised points → render pixels; best mask written to `sam_mask` with the round in its provenance; 400 / 404 / 503
- [ ] `tests/test_refine_api.py` with SAM stubbed: validation, coordinate mapping, `GET` equals `POST`, 503 without weights, `sam_mask` written
- [ ] Register the endpoints in `.kiro/steering/tech.md` and the modules in `structure.md`

## Wave 4 — UI panel (S6; Requirement 5) — due 11-22

- [ ] `src/static/js/refine-panel.js`: Auto-refine checkbox (default on for NPY volumes), round table (score, Δ, correction, ★ best, truth IoU as reference), stop reason in English, round selection redraws mask and prompts, corrective points drawn as hollow diamonds
- [ ] Wire into `runSAMInference`; refresh the survey-map footprint after the best mask is written
- [ ] Headless-Chrome run: click → Auto-refine → table with ≥ 1 round → select each round → canvas changes; no JS errors. Frame V5 recordable

## Wave 5 — Measurement and GPU checks (Requirement 6) — due 11-23

- [ ] `scripts/measure_refine.py`: fixed inlines through the deep target, declared simulated-click rule, raw and low-freq views; per round QC score and truth IoU; single-round SAM IoU for comparison; list every case where the loop does not improve truth IoU. Byte-identical reruns on the same GPU. This also answers whether SAM segments the deep target better on the low-frequency view
- [ ] `scripts/test_refine_e2e.py`: real SAM run completes, log replays through `GET /api/refine/{run_id}`
- [ ] Results and allowed wording in `docs/MEASUREMENTS.md`; nothing about the loop in README or video before this

## Cut rule (from scope.md)

If M2 slips: drop fault continuity (Requirement 2 and its tasks), keep the deep-target loop, and hide the fault option in the UI.

## Out of scope

- Horizon closure error (scope D2).
- Box prompts as corrections; more than one correction per round; learning the constants.
- A non-SAM fallback segmenter for machines without weights (the no-weight path shows a clear 503 message instead, scope S7).
