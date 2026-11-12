# Requirements Document — QC-Driven Self-Improving Prompt Loop (H3)

## Introduction

After SAM segments a slice from the interpreter's clicks, the system scores the result with quality-control (QC) metrics that need **no ground truth**, finds the worst part of the mask, adds one corrective point there, and runs SAM again, for at most 3 rounds. It keeps the best round and shows every round's score so the improvement (or its absence) is visible. This is highlight H3 and frame V5 of the demo.

Scope: `.kiro/steering/scope.md` items S4 (QC service), S5 (refinement driver and API) and S6 (UI panel). Decision D2 replaces the MVP's "horizon closure error" with label-free deep-target metrics; horizon closure is out of scope. Unlike `volume-propagation`, this spec is written **before** the code.

Terms:

- **Slice**: one inline, crossline or time slice of an NPY volume, in its native grid `(rows, cols)` and in one view mode (`raw` or `lowfreq`).
- **Envelope**: the instantaneous amplitude of the slice, `|hilbert(trace)|` along the time axis.
- **Ring**: the pixels within `RING_PX` of the mask but outside it.
- **Round**: one SAM prediction with a given prompt set, followed by QC.
- **Truth overlap**: IoU / Dice / Precision / Recall against the synthetic ground-truth mask, from `src/validation_service.py`.

## Requirements

### Requirement 1 — Label-free QC of a deep-target mask

**User Story:** As an interpreter, I want each segmentation scored without ground truth, so that the same check would work on real data where no truth exists.

> Revised 2026-11-12 (owner chose option C after the first design failed this requirement; see `tasks.md` Findings). "Target-like" is now defined relative to the envelope where the interpreter clicked, and the ring starts after a guard band.

#### Acceptance Criteria

1. WHEN a binary mask, its slice and the interpreter's positive clicks are given THEN the QC service SHALL take the envelope in a small window around the positive clicks as the **reference**, call a pixel **target-like** when its envelope is within `TARGET_BAND_DB` of the reference median, and compute: the **leak fraction** (share of mask pixels that are not target-like), the **miss fraction** (share of ring pixels, beyond a guard band, that are target-like), the **contrast** (median envelope inside the mask over the ring, in dB, reported only) and a **composite score** `(1 − leak)·(1 − miss)` in `[0, 1]`.
2. THE QC service SHALL NOT read any ground-truth mask.
3. WHEN pixels that look like background are added to a mask THEN the composite score SHALL not increase by `SCORE_RESOLUTION` or more; WHEN target pixels are left out of a mask, in a band wider than the guard band, THEN the composite score SHALL not increase by `SCORE_RESOLUTION` or more; WHEN a mask is grown into a nearby reflector much brighter than the clicked target THEN the composite score SHALL decrease. These SHALL be checked with property-based tests on constructed scenes, including scenes with a brighter reflector next to the target. `SCORE_RESOLUTION` (0.01) is the score's stated resolution: score differences below it carry no meaning, and the loop never acts on them (Requirement 3.4, 3.5).
4. THE QC service SHALL declare every threshold as a module-level constant with a one-line reason, and SHALL return the constants used with every result. Constants SHALL be chosen from their definitions and the constructed-scene tests only, never by looking at the demo volumes' ground truth.
5. IF the mask is empty, covers the whole slice, leaves no ring pixels, or no positive click lies inside the slice THEN the QC service SHALL return a composite score of 0 and a reason, not raise.
6. THE composite score and its parts SHALL be deterministic for a given slice, mask and clicks.
7. THE QC SHALL always be computed on the **raw (full-band)** slice, whichever view SAM segmented. (Decision A, 2026-11-12. Basis: the one-shot demo check in `tasks.md`, where the low-frequency view's QC never ranked the truth mask best (0/6). Constructed reflector scenes did **not** reproduce that failure — the low-freq QC was fooled in 3 of 200 — so the decision rests on the demo check alone. On the same scenes the raw-view QC was never fooled, 0/200.)
8. THE QC SHALL report whether it is **reliable** on the slice: WHEN more than `GATE_MAX_TARGET_LIKE_FRAC` of all slice pixels are target-like THEN the clicked reference does not single out anything and the result SHALL be marked unreliable, with a reason.

### Requirement 2 — Fault continuity QC

**User Story:** As an interpreter, I want a fault mask scored for continuity, so that a broken fault trace is flagged.

#### Acceptance Criteria

1. WHEN the target type is `fault` THEN the QC service SHALL compute, per sample row inside the mask's vertical extent, whether the mask is present and how far its column centre moves from the previous row, and SHALL report **continuity** (share of consecutive rows that are present and move by at most `CONTINUITY_TOL_COLS`) and the **fragment count** (connected components).
2. THE fault composite score SHALL decrease when a gap is cut into a continuous fault mask, and when a detached fragment is added.
3. IF fault continuity is not ready by M2 THEN the loop SHALL run for deep targets only (cut rule in `scope.md`), and the UI SHALL not offer the fault type.

### Requirement 3 — Corrective prompt and loop control

**User Story:** As an interpreter, I want the system to fix the worst part of a poor mask by itself, so that I do not re-prompt by hand.

#### Acceptance Criteria

1. WHEN a round ends THEN the driver SHALL find the largest connected region of **leaked** pixels (in the mask, background-like) and of **missed** pixels (in the ring, target-like), and SHALL add one corrective point at the interior point (distance-transform peak) of the larger region: negative for a leak, positive for a miss.
2. THE first round SHALL use only the interpreter's prompts; each later round SHALL use all earlier prompts plus one corrective point.
3. THE loop SHALL run at most `MAX_ROUNDS = 3` rounds.
4. THE loop SHALL stop early WHEN the composite score improves by less than `MIN_GAIN` (= `SCORE_RESOLUTION`) over the best round so far, OR WHEN the largest leak / miss region is smaller than `MIN_REGION_PX`, OR WHEN SAM returns an empty mask; the stop reason SHALL be recorded.
5. THE loop SHALL return the **best** round, not the last round: a later round replaces the best round only if its composite score is higher by at least `MIN_GAIN`.
6. THE loop SHALL embed the slice once and reuse the embedding for every round.
7. THE driver SHALL NOT use ground truth to choose prompts, rounds or the best round.
8. WHEN the first round's QC is unreliable (Requirement 1.8) THEN the driver SHALL NOT add corrective points; it SHALL return round 1 with stop reason `qc_unreliable`, and the UI SHALL say in plain English that the target is too weak for label-free QC on this slice.

### Requirement 4 — API and round log

**User Story:** As a judge, I want every round recorded, so that the improvement shown in the video can be replayed and checked.

#### Acceptance Criteria

1. WHEN a client posts `POST /api/npy/{vol}/refine` with direction, index, view mode, target type and the interpreter's points THEN the server SHALL run the loop and return, per round: prompts, QC metrics, composite score, change from the previous round, and the mask in the native grid; plus the best round, the stop reason and the QC constants.
2. Points SHALL be given as normalised slice coordinates `[x, y]` in `[0, 1]` with labels 1 (include) or 0 (exclude), so the request does not depend on any rendering scale.
3. WHEN the volume has a ground-truth mask for the target type THEN each round SHALL also report the truth overlap, marked as reference only; WHEN it has none THEN the field SHALL be `null`.
4. THE run and its rounds SHALL be stored in SQLite and SHALL be retrievable with `GET /api/refine/{run_id}` with the same content as the original response.
5. WHEN `write_mask` is true (default) THEN the best round's mask SHALL be written to the `sam_mask` volume mask for that slice, with the round recorded in its provenance.
6. IF SAM weights are missing THEN the endpoint SHALL return HTTP 503 with a message naming the missing file; invalid input SHALL return 400; an unknown volume 404.

### Requirement 5 — Round-by-round QC panel

**User Story:** As a judge watching the demo, I want to see the loop work round by round, so that the self-improving step is obvious without narration.

#### Acceptance Criteria

1. THE UI SHALL offer an **Auto-refine** control next to the SAM button; WHEN it is on THEN running SAM SHALL call the refine endpoint instead of a single prediction.
2. WHEN a refine run returns THEN a panel SHALL list each round with its composite score, the change from the previous round, the corrective point (+ or −), and mark the best round; it SHALL show the stop reason in plain English.
3. WHEN the user selects a round THEN the canvas SHALL show that round's mask and prompts, corrective points drawn distinctly from the user's points.
4. WHEN truth overlap is available THEN the panel SHALL show it in a separate column labelled as a reference on synthetic truth, not as the score.
5. THE panel text SHALL be in English (scope S8).

### Requirement 6 — Reproducible numbers

**User Story:** As a reviewer, I want any loop result quoted in the README or video to be re-runnable.

#### Acceptance Criteria

1. A script `scripts/measure_refine.py` SHALL run the loop on a fixed set of slices and fixed simulated clicks, on raw and low-frequency views, and print per round the composite score and the truth IoU, plus the IoU of a single SAM round for comparison.
2. THE simulated click rule SHALL be declared in the script and SHALL NOT change after the first run.
3. THE script SHALL report the cases where the loop does not improve truth IoU, not only the averages.
4. No loop number SHALL appear in README or video unless this script prints it.
