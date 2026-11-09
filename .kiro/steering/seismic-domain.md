---
inclusion: auto
name: seismic-domain
description: Seismic interpretation domain knowledge — low-frequency deep targets, Ricker wavelets, fault continuity and horizon closure QC. Use when implementing or reviewing lowfreq_service.py, qc_service.py, the synthetic data generator, or any segmentation/QC metric.
---

# Seismic Domain Notes

## Why low frequency matters here

High frequencies attenuate faster with depth; deep reflectors therefore survive mainly in the low-frequency band, but they are weak and sit close to the noise floor. Two levers make them interpretable:

1. **Frequency emphasis** — preserve / weight the low band before building the image that SAM is prompted on.
2. **Noise floor** — a cleaner acquisition or processing platform lowers the noise so a weak deep event is not masked. In this software, "cleaner platform" is realised as a low-noise conditioning variant of the synthetic volume, not as physical hardware.

Never present this as a measured improvement without a reproducible comparison from `scripts/`.

## Synthetic model used by this project

- Reflectivity series convolved with a **Ricker wavelet** `(1 - 2·a)·exp(-a)`, `a = (π·f·t)²`.
- Shallow horizons use a higher dominant frequency; the deep target uses a **low dominant frequency** and a small amplitude, so it is genuinely hard to see in the raw (noisy) volume.
- A fault plane offsets deeper horizons by a constant throw; its lateral position varies slowly with inline.
- Ground-truth masks (`truth/fault_mask.npy`, `truth/horizon_mask.npy`, `truth/deep_target_mask.npy`) exist so metrics are honest and reproducible.

## QC metrics for the self-improving loop

- **Fault continuity**: fraction of adjacent inline columns where the detected fault trace continues within a small sample tolerance; penalise gaps and isolated fragments.
- **Horizon closure error**: when a picked horizon is traced around a loop (inline → crossline → inline → crossline), the sample-index mismatch at the closing point. Lower is better; use the same units (samples or ms) everywhere.
- Existing overlap metrics from `src/validation_service.py`: IoU, Dice, Precision, Recall against the ground-truth masks.

All thresholds must be declared as constants in code with a comment explaining the choice. Do not tune them on the demo data and then report the tuned score as a general benchmark.

## Prompt refinement loop (concept)

For round `r = 1..3`: segment → compute QC scores → add a corrective point or box prompt at the worst-scoring location → re-run. Log each round's scores. Stop early if scores stop improving. Show the round-by-round log in the UI; it is the product's visible innovation.
