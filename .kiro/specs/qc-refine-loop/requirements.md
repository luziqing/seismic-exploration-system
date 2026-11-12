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

#### Acceptance Criteria

1. WHEN a binary mask and its slice are given THEN the QC service SHALL compute, from the slice envelope only: the **contrast** (median envelope inside the mask over median envelope in the ring, in dB), the **leak fraction** (share of mask pixels whose envelope looks like the ring), the **miss fraction** (share of ring pixels whose envelope looks like the mask), and a **composite score** in `[0, 1]`.
2. THE QC service SHALL NOT read any ground-truth mask.
3. WHEN pixels that look like background are added to a mask THEN the leak fraction SHALL not decrease and the composite score SHALL not increase; WHEN target-like pixels next to the mask are left out THEN the miss fraction SHALL not decrease and the composite score SHALL not increase (checked with constructed masks and property-based tests).
4. THE QC service SHALL declare every threshold as a module-level constant with a one-line reason, and SHALL return the constants used with every result.
5. IF the mask is empty, covers the whole slice, or leaves no ring pixels THEN the QC service SHALL return a composite score of 0 and a reason, not raise.
6. THE composite score and its parts SHALL be deterministic for a given slice and mask.

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
4. THE loop SHALL stop early WHEN the composite score improves by less than `MIN_GAIN` over the best round so far, OR WHEN the largest leak / miss region is smaller than `MIN_REGION_PX`, OR WHEN SAM returns an empty mask; the stop reason SHALL be recorded.
5. THE loop SHALL return the **best** round by composite score (ties: the earliest), not the last round.
6. THE loop SHALL embed the slice once and reuse the embedding for every round.
7. THE driver SHALL NOT use ground truth to choose prompts, rounds or the best round.

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
