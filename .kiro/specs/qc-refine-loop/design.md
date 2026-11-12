# Design Document — QC-Driven Self-Improving Prompt Loop (H3)

## Overview

| Module | Responsibility | Depends on |
|---|---|---|
| `src/qc_service.py` (new) | Label-free QC of one 2-D mask on one slice: deep-target metrics, fault continuity, composite score. Pure NumPy / SciPy, no SAM, no truth | `scipy.signal.hilbert`, `scipy.ndimage` |
| `src/refine_service.py` (new) | The loop: embed once, predict, QC, choose a corrective point, repeat, keep the best round, optional truth overlap for reporting | `sam_service`, `qc_service`, `validation_service`, `propagation_service.render_slice_image`, `volume_mask_service` |
| `src/database.py` (changed) | Tables `refine_runs`, `refine_rounds`; insert and read back | SQLite |
| `src/server.py` (changed) | `POST /api/npy/{vol}/refine`, `GET /api/refine/{run_id}` | the above |
| `src/static/js/refine-panel.js` (new) | Auto-refine toggle, round panel, round selection on the canvas | `sam-client.js` globals |
| `scripts/measure_refine.py` (new) | Fixed-click GPU measurement for README / video numbers | the endpoint or the services in-process |

The loop lives in its own service so it can be unit-tested with a stub segmenter (a function `points, labels → mask`), with no GPU.

## Data flow

```mermaid
sequenceDiagram
    participant U as Browser
    participant S as server.py
    participant R as refine_service
    participant M as sam_service
    participant Q as qc_service
    U->>S: POST /api/npy/{vol}/refine {direction, index, mode, target, points[nx,ny], labels}
    S->>R: run(slice, view, prompts)
    R->>M: embed(rendered slice)  (once)
    loop round = 1..3
        R->>M: predict(prompts)  (decoder only, ~0.04 s)
        M-->>R: mask (image pixels) → native grid
        R->>Q: score(slice envelope, mask)
        Q-->>R: {contrast_db, leak, miss, score, regions}
        alt stop rule hit
            R->>R: stop, record reason
        else
            R->>R: add ±1 point at worst region
        end
    end
    R->>R: best = argmax score (earliest on ties); truth IoU per round if truth exists (reporting only)
    R-->>S: run log
    S->>S: store run + rounds (SQLite); write best mask to sam_mask
    S-->>U: run log
```

## QC metrics (`qc_service.py`)

Input: `slice2d` (float32, native grid, `rows = samples` for inline / crossline), `mask` (bool, same shape), `target_type`.

**Envelope.** `env = |hilbert(slice2d, axis=0)|` for inline / crossline (time is axis 0). For time slices there is no time axis in the slice; QC uses `|slice2d|` and says so in the result (`envelope: "abs"`). Computed on the view the user segmented (`raw` or `lowfreq`), so QC judges what SAM saw.

**Ring.** `ring = dilate(mask, GUARD_PX + RING_PX) & ~dilate(mask, GUARD_PX)` (chessboard dilation), clipped to the slice. The guard band keeps the envelope's own halo just outside the target out of the ring.

**Reference (option C, revised 2026-11-12).** The interpreter's positive clicks, in native-grid `(row, col)`, define what the target looks like: `ref = median(env[window])`, where `window` is the union of `(2·SEED_HALF+1)²` squares around the positive clicks. A pixel is **target-like** when `|20·log10(env / ref)| ≤ TARGET_BAND_DB`. A reflector much brighter than the clicked target, or quiet background much weaker, is not target-like. If no positive click lies inside the slice, the result is score 0 with a reason.

**Deep-target metrics.**

| Metric | Definition | Better |
|---|---|---|
| `leak` | share of mask pixels that are not target-like | lower |
| `miss` | share of ring pixels that are target-like | lower |
| `contrast_db` | `20·log10(median env in mask / median env in ring)`, reported only | — |
| `score` | `(1 − leak) · (1 − miss)` | higher |

Leak and miss pixels are kept as boolean maps so the driver can find their largest regions.

*Superseded first design (kept for the record):* `leak` / `miss` were defined against the ring's 75th and the mask's 25th envelope percentiles, and the score had a contrast term. It failed Requirement 1.3 — see `tasks.md` Findings.

**Fault metrics** (`target_type = "fault"`). For each row in the mask's vertical extent: present if any mask pixel; centre = mean column. `continuity` = share of consecutive row pairs that are both present with `|Δcentre| ≤ CONTINUITY_TOL_COLS`; `fragments` = number of 8-connected components. `score = continuity / fragments`. Leak / miss maps are computed as for deep targets, so the same corrective-point rule applies.

**Declared constants** (module top, each with its reason; returned in every result). Chosen from these definitions and checked only on constructed scenes (`tests/test_qc_service_pbt.py`), not on the demo volumes:

| Constant | Value | Reason |
|---|---|---|
| `SEED_HALF` | 2 | 5 × 5 native pixels around a click: enough samples for a stable median, small enough to stay inside a target several traces wide |
| `TARGET_BAND_DB` | 6.0 | Within a factor of 2 in envelope amplitude of the clicked area counts as the same kind of reflector |
| `GUARD_PX` | 2 | Skips the envelope halo next to the mask edge |
| `RING_PX` | 4 | 4 native pixels (8 ms vertically, 4 traces laterally) of local background beyond the guard |
| `SCORE_RESOLUTION` | 0.01 | Score differences below this carry no meaning: on 3,000 constructed scenes the largest amount by which a "mask + background band" outscored the exact mask was 0.0089. Equal to the loop's `MIN_GAIN` |
| `CONTINUITY_TOL_COLS` | 1 | A fault may step one trace per sample row |

Resolution limit: an error narrower than `GUARD_PX` lies inside the guard band and is not seen. The property tests state this explicitly (left-out bands wider than the guard).

These values are chosen from the definitions above before any run and are not tuned on the demo volume. If a value turns out to be unworkable, the change, the reason and the before / after output go into `tasks.md`; the old numbers are not quietly replaced.

## Loop (`refine_service.py`)

```
run(slice2d, view_image, prompts, target_type, segment_fn, truth=None)
  emb = embed(view_image)                         # once
  rounds = []
  for r in 1..MAX_ROUNDS:
      mask = segment_fn(prompts)                  # SAM predict → native-grid bool
      # QC reference = the interpreter's positive clicks only; corrective points never move it
      if mask empty: record round, stop "empty_mask"
      q = qc.score(slice2d, mask, target_type)
      record round r: prompts, q, Δ vs previous, truth overlap (if truth), mask
      if r > 1 and q.score < best.score + MIN_GAIN: stop "no_gain"     # best stays the earlier round
      best = round r                                                    # only reached with a gain >= MIN_GAIN
      if r == MAX_ROUNDS: stop "max_rounds"
      region, sign = larger of largest(q.leak_map), largest(q.miss_map)
      if region.size < MIN_REGION_PX: stop "nothing_to_fix"
      prompts += (interior_point(region), 1 if sign == miss else 0)
  best = the round kept by the rule above (a later round must beat it by >= MIN_GAIN)
```

| Constant | Value | Reason |
|---|---|---|
| `MAX_ROUNDS` | 3 | Product decision (MVP Requirement 4.2); one embed, so cost is ~3 decoder passes |
| `MIN_GAIN` | 0.01 (= `qc_service.SCORE_RESOLUTION`) | Smaller score changes are below the score's stated resolution |
| `MIN_REGION_PX` | 12 | Smaller regions are a few pixels of envelope noise, not a correctable error |

`interior_point` reuses the distance-transform-peak rule of `propagation_service.mask_to_points`, so a corrective point never lands on a region's edge.

`segment_fn` is a parameter. Production passes a closure over `sam_service.predict_mask_np` and the cached embedding; tests pass deterministic stubs (for example a disk that grows when given a positive point and shrinks when given a negative one), so the loop logic is tested without a GPU.

**Truth overlap.** If `truth/<target>_mask.npy` exists, each round's native mask is compared to the truth slice with `validation_service.validate_segmentation`. The result is stored per round under `truth_reference`. Nothing in the loop reads it.

## Coordinates

The request carries points as normalised slice coordinates `[nx, ny]` (`nx = col / cols`, `ny = row / rows`), as the UI already stores them (`p.nx`, `p.ny`). The server converts them to pixels of the rendered image with the render scale (`x = nx · cols · sx`, `y = ny · rows · sy`), the same mapping `/api/npy/{vol}/embed` returns. Corrective points are created in native-grid `(row, col)` and stored in both forms.

## Persistence

```sql
CREATE TABLE IF NOT EXISTS refine_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volume TEXT, direction TEXT, slice_index INTEGER, mode TEXT, target_type TEXT,
    best_round INTEGER, stop_reason TEXT, constants TEXT,          -- JSON
    created_at REAL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS refine_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES refine_runs(id),
    round INTEGER, prompts TEXT, metrics TEXT, score REAL, delta REAL,
    truth_reference TEXT,                                          -- JSON or NULL
    mask_shape TEXT, mask_rle TEXT                                 -- run-length encoded native mask
);
```

Masks are stored run-length encoded (a 256 × 48 mask is a few hundred bytes), so `GET /api/refine/{run_id}` can return the same masks as the original response.

## API

`POST /api/npy/{vol}/refine`

```json
{ "direction": "inline", "index": 20, "mode": "raw", "target_type": "deep_target",
  "points": [[0.30, 0.91]], "labels": [1], "max_rounds": 3, "write_mask": true }
```

Response: `{run_id, best_round, stop_reason, constants, grid_shape, rounds: [{round, prompts:[{nx, ny, row, col, label, source: "user"|"correction"}], metrics:{contrast_db, leak, miss, score, ...}, score, delta, truth_reference|null, mask: [[0|1]...]}]}`.

`GET /api/refine/{run_id}` returns the same object. Errors: 400 invalid input, 404 unknown volume or run, 503 SAM weights missing.

## UI (`refine-panel.js`)

- Checkbox **Auto-refine (≤3 rounds)** next to `▶ SAM`, on by default for NPY volumes. When on, `runSAMInference` posts to `/refine` with the current slice's picks; otherwise it keeps the single-prediction path.
- Panel (bottom-left of the section view, collapsible, like the survey map): one row per round — `Round`, `QC score`, `Δ`, `Correction` (`+` / `−` with position), `★` on the best round, and a separate `Truth IoU (reference)` column when available. Stop reason below the table, in English ("Stopped: score did not improve", "Stopped: nothing left to fix", "Stopped: 3 rounds").
- Clicking a row draws that round's mask and its prompts; corrective points are drawn as hollow diamonds (green `+`, red `−`) so they differ from the user's filled squares. The best round is shown by default.
- The survey map footprint refreshes after the best mask is written.

## Testing

| Level | What | Where |
|---|---|---|
| Unit | QC on constructed slices: a bright block and its exact mask scores higher than a mask with added background, a mask missing part of the block, an empty or full mask; fault continuity drops with a gap and with a fragment | `tests/test_qc_service.py` |
| Property-based (`hypothesis`) | For random block slices and random masks: adding background pixels never increases the score; score in `[0, 1]`; deterministic | `tests/test_qc_service_pbt.py` |
| Unit, stub segmenter | Loop: correction sign follows leak vs miss, max 3 rounds, `no_gain` / `nothing_to_fix` / `empty_mask` stops, best round kept when a later round is worse, embed called once, truth never read by the driver (stub that raises if touched) | `tests/test_refine_service.py` |
| API, SAM stubbed | Request validation, normalised-coordinate mapping, SQLite round trip (`GET` equals `POST` response), 503 without weights, best mask written to `sam_mask` | `tests/test_refine_api.py` |
| GPU end-to-end | Real SAM on the synthetic volume: run completes, log replays, `measure_refine.py` prints a table | `scripts/test_refine_e2e.py`, `scripts/measure_refine.py` |
| Browser | Click → Auto-refine → panel shows rounds → round selection redraws mask | headless Chrome run, as for S2 / S13 |

## Risks

- **The label-free score may disagree with truth IoU.** That is a real finding, not a bug to hide: `measure_refine.py` reports both, and the README says which one the loop optimises.
- **SAM may ignore a single corrective point** on low-contrast slices; then the loop stops with `no_gain` after round 2. The panel must make that look intentional ("score did not improve"), not like a failure.
- **Time slices** have no time axis for the envelope; QC falls back to `|amplitude|` and labels it. The demo uses inlines.
