# Measurements

Every number in this file is printed by a script in `scripts/` and can be re-run. If a number here and the script disagree, the script is right and this file is stale.

## Deep-target visibility: raw vs low-frequency, noisy vs clean (H1, H2)

**Command:** `python scripts/measure_lowfreq.py` (add `--json out.json` for the full record). No randomness; reruns print byte-identical results.

**Data:** the two synthetic volumes from `scripts/generate_synthetic_seismic.py`, seed 20261108, 48 × 48 × 256 samples at 2 ms.

| Volume | SNR | `amplitude.npy` SHA-256 (first 12) |
|---|---|---|
| `synthetic_deep_v1` (noisy) | 6 dB | `a4207283aa92` |
| `synthetic_deep_v1_clean` (clean) | 30 dB | `0653bb84c9b2` |

**Metric** (declared in the script before the first run, not tuned afterwards):

- Time window: the samples where the ground-truth deep-target mask is set (samples 215–255).
- Target traces: the 348 traces that contain the deep target. Background: all other 1,956 traces, and separately the 1,086 of them with no horizon crossing the window.
- Per trace: RMS amplitude inside the window.
- **TBR** (target-to-background ratio) = 20·log10(median RMS of target traces / median RMS of background traces).
- **AUC** = probability that a random target trace has a higher RMS than a random background trace (ties count ½). 0.5 means the two cannot be told apart, 1.0 means every target trace stands out.
- **Control**: the same footprint shifted by 24 inlines, where there is no target. A view that invented a target would push this AUC up.
- Low-frequency view: `src/lowfreq_service.py` with its declared defaults (full weight ≤ 14 Hz, cosine taper to 0.05 at ≥ 30 Hz), the same filter as the app's `?mode=lowfreq`.

**Results** (2026-11-12):

| Volume | View | TBR, all background | AUC, all background | TBR, no horizon in window | AUC, no horizon in window | Control AUC |
|---|---|---|---|---|---|---|
| noisy (6 dB) | raw | −0.11 dB | 0.437 | 1.19 dB | 0.762 | 0.234 |
| noisy (6 dB) | low-freq | 5.29 dB | 0.927 | 6.87 dB | 0.972 | 0.328 |
| clean (30 dB) | raw | 2.12 dB | 0.515 | 4.11 dB | 0.926 | 0.234 |
| clean (30 dB) | low-freq | 8.64 dB | 1.000 | 10.78 dB | 1.000 | 0.239 |

**What this shows, on this synthetic model only:**

- H1: in the noisy volume, the deep target cannot be separated from the background by trace energy in the raw view (AUC 0.437 against all background). In the low-frequency view it can, for most traces (AUC 0.927).
- H2: at the same view, the clean volume separates better than the noisy one (raw 0.515 vs 0.437; low-freq 1.000 vs 0.927).
- The two effects add up: low-freq + clean is the only combination with complete separation (AUC 1.000).
- The control stays below 0.5 in every view, so the filter does not make a target appear where there is none. It is not exactly 0.5 because the background is not uniform across the survey (horizons dip and the fault offsets them); the script does not break this down further.

**What it does not show:**

- **The result is built into the model.** The generator puts the deep target at 10 Hz and the horizons at 32 Hz, and the filter keeps ≤ 14 Hz. The measurement confirms that the pipeline behaves as designed. It is not evidence that real deep targets are separable this way.
- It measures trace energy, not segmentation quality. Whether SAM segments the target better on the low-frequency view is a separate question that this script does not answer.
- One seed and one model. No claim about other noise levels, frequencies or geometries.

Wording for README and video: say "on our synthetic model, the low-frequency view separates the deep target from the background (AUC 0.44 → 0.93 on the noisy volume, script: `scripts/measure_lowfreq.py`)", and state that the model was built with a low-frequency target. Do not present these numbers as accuracy or as results on field data.

## SAM3 + QC refine loop: which view SAM segments, 1 round vs loop (H3)

**Command:** `python scripts/measure_refine.py` (add `--json out.json` for every round). Needs `data/weights/sam3.pt` and a GPU. Two reruns on the RTX 4090 D dev machine (11-13) printed byte-identical text and JSON (SHA-256 of the JSON `9d81809abb33…`). Other GPUs or drivers may differ in the last digits.

**Protocol** (declared in the script before the first run; run once, not tuned):

- Same two volumes as above; all 19 inlines (11–29) whose ground-truth deep-target slice is non-empty.
- Click rule: one include click at the interior point of the truth slice (the pixel farthest from its edge). This simulates an interpreter clicking the middle of the target. No exclude clicks.
- SAM segments either the raw or the low-frequency image. QC always runs on the raw slice (decision A). Same code path as `POST /api/npy/{vol}/refine`, `MAX_ROUNDS` 3, `MIN_GAIN` 0.01.
- "Round 1" = plain SAM. "Kept" = the round the loop keeps (highest QC score). Truth IoU is attached after the loop and never seen by it.

**Results** (2026-11-13, 19 inlines per row):

| Volume | SAM view | IoU round 1 (mean / median) | IoU kept (mean / median) | Loop kept a later round | Kept IoU higher / lower / same than round 1 | Stop reasons |
|---|---|---|---|---|---|---|
| noisy | raw | 0.432 / 0.458 | 0.435 / 0.458 | 1 | 1 / 0 / 18 | `qc_unreliable` 18, `max_rounds` 1 |
| noisy | low-freq | 0.057 / 0.067 | 0.057 / 0.067 | 0 | 0 / 0 / 19 | `qc_unreliable` 16, `empty_mask` 2, `no_gain` 1 |
| clean | raw | 0.798 / 0.876 | **0.814 / 0.894** | 12 | **9 / 3 / 7** | `no_gain` 16, `max_rounds` 3 |
| clean | low-freq | 0.885 / 0.909 | 0.796 / 0.908 | 5 | 1 / 4 / 14 | `no_gain` 17, `max_rounds` 2 |

The script lists every inline and round. Cases where the kept round has *lower* truth IoU than round 1: clean/raw inlines 16 (0.888 → 0.877), 28 (0.892 → 0.458) and 29 (0.884 → 0.542); clean/low-freq inlines 26–29.

**What this shows, on this synthetic model only:**

- **SAM should segment the raw view.** On the noisy volume, SAM with one click reaches IoU 0.43 on raw and 0.06 on low-freq. The low-frequency view separates the target by energy (section above) but does not help SAM. On the clean volume, low-freq gives a better round 1 (0.885 vs 0.798), but the raw-view QC then misjudges the low-freq masks and the loop makes them worse (1 better, 4 worse). So the UI sends SAM and the loop the raw slice, whatever view is displayed.
- **The loop helps on the clean volume, raw view:** mean IoU 0.798 → 0.814, median 0.876 → 0.894; better in 9 of 19 inlines, worse in 3, unchanged in 7. The largest gains are slices where the first click gave a poor mask (inline 18: 0.597 → 0.915; inline 23: 0.570 → 0.863).
- **The gate does its job on the noisy volume:** the loop stopped with `qc_unreliable` on 18 of 19 inlines. Inline 27 sat exactly at the gate limit (target-like fraction 0.500 ≤ 0.5) and ran 3 rounds (0.312 → 0.372).
- The loop never keeps a round with a lower **QC score** than an earlier one. That is a statement about QC, not truth: in 3 of 19 clean/raw cases the QC preferred a later round that was worse against truth, and inlines 28 and 29 lost a lot (to 0.46 and 0.54). This is a known limitation of the label-free QC (guard band and envelope reference), recorded, not redesigned (scope §0 rule 1).

**What it does not show:** one click rule, one seed, one synthetic model, inline slices only. No claim about field data, other click positions, or crossline / time slices.

**UI defaults set from this run:** SAM and the refine loop segment the **raw** slice; **Auto-refine on** for NPY volumes. On the noisy volume the panel shows the gate's message instead of rounds.

Wording for README and video: "on the clean synthetic volume, the label-free QC loop raised the mean IoU of a one-click SAM mask from 0.80 to 0.81 (median 0.88 → 0.89), improving 9 of 19 slices and worsening 3 (script: `scripts/measure_refine.py`)". Say that the loop declines to run on the noisy volume, and why. Do not say the loop "always improves" or "never gets worse".
