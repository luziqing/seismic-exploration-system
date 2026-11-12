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
