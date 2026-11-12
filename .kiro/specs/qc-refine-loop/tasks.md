# Implementation Plan — QC-Driven Self-Improving Prompt Loop (H3)

> Written before the code (2026-11-12). Scope items S4–S6 in `.kiro/steering/scope.md`; milestone M2, due Mon 11-23. Tick a task only when its check passes, and note the date. If a declared constant has to change, record the old value, the new value, the reason and the before / after output here.

## Wave 0 — Test tooling

- [x] Add `requirements-dev.txt` (`pytest`, `hypothesis`) and document it in the README run section. Check: `pip install -r requirements-dev.txt` in the `.venv`, `pytest tests` still green

## Wave 1 — QC service (S4; Requirements 1, 2) — due 11-19

- [x] (2026-11-12, design C) `src/qc_service.py`: envelope, ring, `contrast_db`, `leak`, `miss`, composite `score`, leak / miss maps, declared constants returned with every result; empty / full / no-ring cases return score 0 with a reason
- [x] (2026-11-12) Fault continuity: per-row presence and centre shift, `continuity`, `fragments`, fault score
- [x] (2026-11-12, 17 tests) `tests/test_qc_service.py`: constructed slices — exact mask beats mask + background, mask − part of target, empty, full; fault score drops with a gap and with a fragment; time-slice fallback labelled `abs`
- [x] (2026-11-12, 6 properties incl. brighter reflector) `tests/test_qc_service_pbt.py` (`hypothesis`): adding background pixels never raises the score; removing target pixels next to an exact mask never raises it; score in `[0, 1]`; same input → same output. Record any bug PBT finds that the unit tests missed (for the README PBT answer)

### Findings 2026-11-12 — the declared QC design does not meet Requirement 1.3

Implemented exactly as declared (`RING_PX 4`, `BG_PERCENTILE 75`, `TARGET_PERCENTILE 25`, `CONTRAST_REF_DB 6`); 15 unit tests on constructed slices pass. Then:

1. **Property-based test found a counterexample the unit tests missed.** `test_adding_background_never_improves_the_mask` fails: for a block at rows 8–19, cols 4–11, adding a band of pure-noise *amplitude* below it raised the score 0.9643 → 0.9677 (miss 0.036 → 0.032). In a direct scan, 583 of 900 such cases raised the score. Cause: the Hilbert envelope spreads target energy a few samples past the target's edge, so the ring right next to an exact mask looks target-like ("miss"); growing the mask into that halo lowers `miss`.
2. **On the demo volumes the ground-truth mask is not ranked best.** Inlines 16 / 20 / 24, truth mask vs truth grown 20 rows upward vs truth cut in half: the truth mask had the highest score in **0 of 12** (2 volumes × 2 views × 3 inlines). Raw view: truth scores 0.000–0.019. Cause: the fourth horizon runs about 3–10 samples above the target window over the target traces and is brighter than the target (raw envelope ≈ 0.38 vs ≈ 0.09 inside, clean volume), so the ring contains it and growing the mask into it looks like an improvement. With this QC, the loop would steer SAM toward the horizon.
3. While diagnosing, two variants were tried on the demo data (`BG_PERCENTILE 50`; a low-frequency-fraction evidence map). Neither ranked the truth best consistently (1/12 and 5/10). These were exploratory looks at demo truth, so neither may be adopted on that basis.

Status: `qc_service.py` and its tests are committed as a record; the failing property is marked `xfail(strict=True)` pointing here. Wave 1 is **not** done. A redesign needs the owner's decision (see the S4 row in `scope.md`).

### Redesign C, 2026-11-12 (owner chose option C)

Spec updated first (Requirement 1, design "Reference (option C)"). Then:

1. **Constructed-scene tests drove two corrections, both recorded here.**
   - Hard-edged sine blocks are not a valid "exact mask": a block's envelope extends past its edges, so cutting a block's edge column can legitimately improve the fit. Scenes were rebuilt like the generator (Ricker target, exact mask = −6 dB envelope extent). With Ricker scenes the remaining violations were: cuts of 1–2 traces (inside the 2-px guard band: 218 / 236 of 400; cuts ≥ 3 traces: 0) and "+ background band" scoring above the exact mask in 16 of 3,000 scenes by at most 0.0089.
   - So Requirement 1.3 now states two resolution limits: errors narrower than `GUARD_PX` are not seen, and score differences below `SCORE_RESOLUTION = 0.01` carry no meaning (the loop's `MIN_GAIN` is the same value, so it never acts on them). No other constant changed: `SEED_HALF 2`, `TARGET_BAND_DB 6`, `GUARD_PX 2`, `RING_PX 4` are as first declared for C.
2. **Result:** 17 unit tests and 6 property tests (200 examples each, including a brighter reflector 3–10 samples above the target) pass. Requirement 1 is met on constructed scenes.
3. **One-shot check on the demo volumes (run once, not used to tune).** Simulated click = interior point of the truth slice; truth mask vs three mistakes (+20 rows up into the horizon, right half cut, +6 background traces). Truth ranked best in **4 of 12**:

   | Volume | View | Inlines 16 / 20 / 24 truth ranked best |
   |---|---|---|
   | clean (30 dB) | raw | **3 / 3** (truth 0.84–0.89 vs best mistake 0.64–0.68) |
   | clean (30 dB) | low-freq | 0 / 3 (+20 up scores higher) |
   | noisy (6 dB) | raw | 1 / 3 |
   | noisy (6 dB) | low-freq | 0 / 3 (+20 up scores higher) |

   Why, from the envelope profile over the target traces (clean, inline 20): in the **raw** view the horizon above the target peaks at ≈ 0.36 against ≈ 0.10 inside the target, so C correctly calls it "not target". In the **low-frequency** view the filter removes the horizon's 32 Hz energy and it drops to ≈ 0.09, the same level as the target; an amplitude-based QC cannot tell them apart there. In the **noisy raw** view the target sits at the noise level (that is the point of H1), so there is nothing for an amplitude QC to anchor on.

**Consequence for the loop and the demo (owner decision needed):** the QC is trustworthy where the target is visible by amplitude and its neighbours differ in amplitude — on the demo data, the clean volume's raw view. It is not trustworthy on the low-frequency view, which is exactly the view H1 recommends for the noisy volume. Choosing a different QC view or metric now would be a design change made after looking at demo truth, so it is not done here.

### Decision A, 2026-11-12 (owner): QC on the raw view + reliability gate

Spec first (Requirement 1.7, 1.8, 3.8; design "Envelope", "Reliability gate"). `GATE_MAX_TARGET_LIKE_FRAC = 0.5` was fixed from its definition ("most of the slice looks like the clicked area") before any check.

- Constructed scenes: visible targets always pass the gate (200 examples); targets at or below the noise level always fail it (200 examples). 27 QC tests pass.
- Honest note on the basis for "raw view": on constructed reflector scenes the low-frequency-view QC was fooled in only **3 of 200** cases (raw view: 0 of 200), so these scenes do not reproduce the failure seen on the demo volumes. Decision A therefore rests on the demo check above, and the docs say so.
- One-shot gate check on the demo volumes (raw view, same simulated clicks, run once):

  | Volume | Inlines 16 / 20 / 24 target-like fraction | Gate | Truth vs best mistake |
  |---|---|---|---|
  | clean | 0.195 / 0.208 / 0.203 | reliable | 0.838 vs 0.659, 0.887 vs 0.680, 0.861 vs 0.659 — truth best 3/3 |
  | noisy | 0.594 / 0.611 / 0.610 | **unreliable** | (QC not used; loop would stop with `qc_unreliable`) |

  The gate switches the loop off exactly on the slices where the QC was not trustworthy. On the demo, H3 runs on the clean volume, and the noisy volume shows the gate's message.

## Wave 2 — Loop driver (S5; Requirement 3) — due 11-20

- [x] (2026-11-12) `src/refine_service.py`: `run(...)` with injectable `segment_fn`; correction at the interior point of the larger of the largest leak / miss regions; stops `max_rounds`, `no_gain`, `nothing_to_fix`, `empty_mask`; best round = highest score, earliest on ties; embed once
- [x] (2026-11-12; separate `attach_truth()` after the loop, `run()` has no truth parameter) Truth overlap per round through `validation_service`, stored as `truth_reference`, never read by the driver
- [x] (2026-11-12, 15 tests, incl. `qc_unreliable` stop and QC reference fixed to the user's click) `tests/test_refine_service.py` with stub segmenters: correction sign, round limit, each stop reason, best round kept when a later round is worse, one embed, driver does not touch truth (stub raises if read)

## Wave 3 — API and persistence (S5; Requirement 4) — due 11-21

- [x] (2026-11-12) SQLite tables `refine_runs`, `refine_rounds` (RLE masks) in `src/database.py`, with insert and read-back
- [x] (2026-11-12) `POST /api/npy/{vol}/refine` and `GET /api/refine/{run_id}`; normalised points → render pixels; best mask written to `sam_mask` with the round in its provenance; 400 / 404 / 503
- [x] (2026-11-12, 18 tests) `tests/test_refine_api.py` with SAM stubbed: validation, coordinate mapping, `GET` equals `POST`, 503 without weights, `sam_mask` written
- [x] (2026-11-12) Register the endpoints in `.kiro/steering/tech.md` and the modules in `structure.md`

### Diagnostic real-SAM runs, 2026-11-12 (not the Wave 5 measurement; not for README or video)

In-process, click = interior point of the truth slice, inlines 16 / 20 / 24, `write_mask: false`:

- **Clean volume:** round 1 is already good (truth IoU 0.87–0.94). In 4 of 6 runs the correction made SAM worse (e.g. IoU 0.91 → 0.33) and the QC score dropped too, so the loop stopped with `no_gain` and kept round 1. In 2 of 6 a correction raised the QC score by ≥ 0.01 and became best: IoU 0.89 → 0.88 (il 16) and 0.90 → 0.93 (il 24). The best-round rule never kept a worse-QC round.
- **Noisy volume:** the gate stopped every run after round 1 (`qc_unreliable`), as intended.
- **Side finding for H1:** on the noisy volume, SAM with this single click reached truth IoU 0.61–0.69 on the raw view but only 0.07–0.08 on the low-frequency view. So the low-frequency view does not help SAM here, although it separates the target by energy (`docs/MEASUREMENTS.md`). Wave 5 must measure this properly before anything is said about it.
- Latency: ~0.5 s per run after the model is loaded.

## Wave 4 — UI panel (S6; Requirement 5) — due 11-22

- [x] (2026-11-13) `src/static/js/refine-panel.js`: Auto-refine checkbox (default on for NPY volumes), round table (score, Δ, correction, ★ best, truth IoU as reference), stop reason in English, round selection redraws mask and prompts, corrective points drawn as hollow diamonds
- [x] (2026-11-13) Wire into `runSAMInference`; refresh the survey-map footprint after the best mask is written
- [x] (2026-11-13; clean IL 24: 3 rounds, masks 1580 / 909 / 778 px per round, 2 diamonds; noisy IL 21: gate message; Auto-refine off -> /predict; time slice disables the control; no JS errors) Headless-Chrome run: click → Auto-refine → table with ≥ 1 round → select each round → canvas changes; no JS errors. Frame V5 recordable

## Wave 5 — Measurement and GPU checks (Requirement 6) — due 11-23

- [x] (2026-11-13, run once; two reruns byte-identical text + JSON on the RTX 4090 D) `scripts/measure_refine.py`: fixed inlines through the deep target, declared simulated-click rule, raw and low-freq views; per round QC score and truth IoU; single-round SAM IoU for comparison; list every case where the loop does not improve truth IoU. Byte-identical reruns on the same GPU. This also answers whether SAM segments the deep target better on the low-frequency view
- [x] (2026-11-13: clean il 23 3 rounds, noisy il 20 `qc_unreliable`, both replay identical) `scripts/test_refine_e2e.py`: real SAM run completes, log replays through `GET /api/refine/{run_id}`
- [x] (2026-11-13) Results and allowed wording in `docs/MEASUREMENTS.md`; nothing about the loop in README or video before this

### Wave 5 result and the UI defaults it set, 2026-11-13

`scripts/measure_refine.py`, one click at the truth interior point, 19 inlines per volume (full table in `docs/MEASUREMENTS.md`):

- SAM view: **raw**. Noisy volume IoU 0.43 (raw) vs 0.06 (low-freq). On the clean volume low-freq gives a better round 1 (0.885 vs 0.798) but the raw-view QC then makes the loop worse there (1 better / 4 worse), so the loop and the plain SAM button both segment the raw slice whatever is displayed. This reverses the S2 behaviour "SAM on the low-freq view embeds `mode: lowfreq`".
- Auto-refine: **on**. Clean / raw: mean IoU 0.798 -> 0.814, 9 better / 3 worse / 7 unchanged. Limitation recorded, not redesigned: in 3 cases the QC kept a round that is worse against truth (il 16, 28, 29).
- Noisy: gate stopped 18 / 19 runs; il 27 sat exactly at the limit (0.500) and ran.
- UI change found by the browser run: the panel was first placed bottom-left and covered the deep target, which blocked clicks on it; moved to top-left.

## Order and limits (scope.md §0, 2026-11-12)

Wave 5's `measure_refine.py` runs **before** Wave 4, once, with one declared click rule; its output sets two UI defaults (view SAM segments, Auto-refine on/off). No other experiments. The UI offers the deep target only.

## Cut rule (from scope.md)

If M2 slips: drop fault continuity (Requirement 2 and its tasks), keep the deep-target loop, and hide the fault option in the UI.

## Out of scope

- Horizon closure error (scope D2).
- Box prompts as corrections; more than one correction per round; learning the constants.
- A non-SAM fallback segmenter for machines without weights (the no-weight path shows a clear 503 message instead, scope S7).
