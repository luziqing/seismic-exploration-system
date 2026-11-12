#!/usr/bin/env python
"""
Measure how visible the weak deep target is in the synthetic volumes: raw vs low-frequency view,
noisy vs clean volume (scope S3). This script is the only source of H1 / H2 numbers.

Metric (declared before measuring, no tuning):
  * Time window  = samples where the ground-truth deep-target mask is set in any trace.
  * Target traces     = traces whose deep-target mask is set somewhere.
    Background traces = traces with no deep-target voxel.
  * Per trace: RMS amplitude inside the time window.
  * TBR_dB = 20·log10( median RMS of target traces / median RMS of background traces )
  * AUC    = P(RMS of a random target trace > RMS of a random background trace), ties count ½.
             0.5 = indistinguishable, 1.0 = every target trace stands out.
Low-frequency view = src/lowfreq_service.condition_slice with its declared defaults, applied along
time to every trace (same filter as the app's ?mode=lowfreq). The stored volumes are only read.

Caveats: synthetic data only; the background window contains the fourth horizon on the far side
of the fault, as a real section would. This is a visibility measure for the demo model, not a
benchmark of interpretation accuracy.

Usage:  python scripts/measure_lowfreq.py [--json out.json]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import lowfreq_service  # noqa: E402

VOLUMES = (("noisy", "synthetic_deep_v1"), ("clean", "synthetic_deep_v1_clean"))
MODES = ("raw", "lowfreq")


def condition_volume(vol: np.ndarray, dt_us: int) -> np.ndarray:
    n_il, n_xl, n_s = vol.shape
    traces = np.asarray(vol, dtype=np.float32).reshape(n_il * n_xl, n_s)
    return lowfreq_service.condition_slice(traces, dt_us=dt_us, time_axis=1).reshape(vol.shape)


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Mann-Whitney AUC with ties counted as one half (exact, no sampling)."""
    allv = np.concatenate([pos, neg])
    order = np.argsort(allv, kind="mergesort")
    ranks = np.empty(len(allv), dtype=np.float64)
    sorted_v = allv[order]
    i = 0
    while i < len(allv):                       # average ranks over ties
        j = i
        while j + 1 < len(allv) and sorted_v[j + 1] == sorted_v[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    r_pos = ranks[:len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def visibility(vol: np.ndarray, target: np.ndarray, horizon: np.ndarray) -> dict:
    """Target-vs-background metrics for one volume (any view) and its truth masks."""
    window = np.flatnonzero(target.any(axis=(0, 1)))
    is_target = target.any(axis=2)                                   # (nIL, nXL)
    has_horizon = horizon[:, :, window].any(axis=2)                   # a horizon crosses the window
    rms = np.sqrt(np.mean(vol[:, :, window].astype(np.float64) ** 2, axis=2))
    pos = rms[is_target]
    out = {"window_samples": [int(window[0]), int(window[-1])], "n_target_traces": int(pos.size)}
    for key, bg_sel in (("all_background", ~is_target), ("background_without_horizon", ~is_target & ~has_horizon)):
        neg = rms[bg_sel]
        out[key] = {
            "n_traces": int(neg.size),
            "median_rms_target": float(np.median(pos)),
            "median_rms_background": float(np.median(neg)),
            "tbr_db": float(20.0 * np.log10(np.median(pos) / np.median(neg))),
            "auc": auc(pos, neg),
        }
    return out


def control(vol: np.ndarray, target: np.ndarray) -> dict:
    """Negative control: the target's footprint shifted by half the inlines, over the same time window,
    compared with background traces that contain neither the real nor the shifted footprint.
    A view that manufactures a target would push this AUC towards 1; no real target is there."""
    window = np.flatnonzero(target.any(axis=(0, 1)))
    fp = target.any(axis=2)
    shifted = np.roll(fp, fp.shape[0] // 2, axis=0) & ~fp
    rms = np.sqrt(np.mean(vol[:, :, window].astype(np.float64) ** 2, axis=2))
    pos, neg = rms[shifted], rms[~fp & ~shifted]
    return {"n_traces": int(pos.size), "tbr_db": float(20.0 * np.log10(np.median(pos) / np.median(neg))),
            "auc": auc(pos, neg)}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def measure(npy_root: Path) -> dict:
    out = {"filter": lowfreq_service.get_filter_metadata(), "volumes": {}}
    for label, name in VOLUMES:
        d = npy_root / name
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        vol = np.load(d / "amplitude.npy", mmap_mode="r")
        target = np.load(d / "truth" / "deep_target_mask.npy")
        horizon = np.load(d / "truth" / "horizon_mask.npy")
        views = {"raw": np.asarray(vol, dtype=np.float32), "lowfreq": condition_volume(vol, int(meta["dt_us"]))}
        out["volumes"][label] = {
            "name": name, "seed": meta.get("seed"), "snr_db": meta.get("snr_db"),
            "amplitude_sha256": sha256(d / "amplitude.npy"),
            "views": {m: {**visibility(views[m], target, horizon), "control_shifted_footprint": control(views[m], target)}
                      for m in MODES},
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--npy-root", type=Path, default=ROOT / "data" / "npy")
    ap.add_argument("--json", type=Path, help="also write the results to this JSON file")
    args = ap.parse_args()
    for _, name in VOLUMES:
        if not (args.npy_root / name / "amplitude.npy").exists():
            print(f"Missing {name}. Generate it first: python scripts/generate_synthetic_seismic.py"
                  f"{' --clean' if name.endswith('_clean') else ''}", file=sys.stderr)
            return 2
    res = measure(args.npy_root)

    f = res["filter"]
    print(f"Deep-target visibility — low-frequency filter: pass <= {f['default_f_pass_hz']} Hz, "
          f"stop >= {f['default_f_stop_hz']} Hz, floor {f['default_attenuation_floor']}")
    any_v = next(iter(res["volumes"].values()))["views"]["raw"]
    print(f"Window: samples {any_v['window_samples'][0]}-{any_v['window_samples'][1]}; {any_v['n_target_traces']} target traces; "
          f"background: {any_v['all_background']['n_traces']} traces (all), "
          f"{any_v['background_without_horizon']['n_traces']} with no horizon in the window\n")
    print(f"{'volume':8s} {'SNR':>6s} {'view':8s} | {'all background':^16s} | {'no horizon in window':^20s} | {'control':^7s} | seed / amplitude sha256")
    print(f"{'':24s} | {'TBR dB':>8s} {'AUC':>6s} | {'TBR dB':>9s} {'AUC':>9s} | {'AUC':>7s} |")
    for label, v in res["volumes"].items():
        for m in MODES:
            a, n = v["views"][m]["all_background"], v["views"][m]["background_without_horizon"]
            c = v["views"][m]["control_shifted_footprint"]
            print(f"{label:8s} {v['snr_db']:>4.0f}dB {m:8s} | {a['tbr_db']:>8.2f} {a['auc']:>6.3f} | "
                  f"{n['tbr_db']:>9.2f} {n['auc']:>9.3f} | {c['auc']:>7.3f} | {v['seed']} / {v['amplitude_sha256'][:12]}")
    print("\nTBR = target-to-background RMS ratio in the target time window; AUC 0.5 = indistinguishable, 1.0 = separable."
          "\ncontrol = same footprint shifted by half the inlines where no target exists (should stay at or below 0.5).")
    if args.json:
        args.json.write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nwritten {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
