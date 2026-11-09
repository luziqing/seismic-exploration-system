#!/usr/bin/env python3
"""Deterministic, fully synthetic seismic volumes for SamForGeophysics.

No field data, no third-party dataset, no model weights. The output is
byte-reproducible for a fixed seed and is directly readable by SGSeg's
``src/npy_service.py`` and the ``/api/npy/...`` routes in ``src/server.py``.

Layout written to ``data/npy/<name>/``::

    amplitude.npy              float32, shape [nIL, nXL, nSamples]
    meta.json                  geometry + provenance, SGSeg-compatible keys
    truth/fault_mask.npy       bool, fault trace
    truth/horizon_mask.npy     bool, horizon reflectors
    truth/deep_target_mask.npy bool, weak low-frequency deep target
    preview.png                optional inline view (--preview)

Usage::

    python scripts/generate_synthetic_seismic.py
    python scripts/generate_synthetic_seismic.py --clean
    python scripts/generate_synthetic_seismic.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - environment guard
    sys.exit(
        "ERROR: NumPy is required to generate demo data.\n"
        "Install it with:  pip install 'numpy>=1.24,<2.0'"
    )

GENERATOR_VERSION = "1.0.0"
DEFAULT_SEED = 20261108
DEFAULT_N_IL = 48
DEFAULT_N_XL = 48
DEFAULT_N_SAMPLES = 256
DEFAULT_DT_US = 2000
DEFAULT_NAME = "synthetic_deep_v1"

# --- Declared model constants (seconds / Hz / relative amplitude) -----------
# These are teaching-phantom parameters, NOT measurements of any real survey.
HORIZONS_T_S = (0.10, 0.20, 0.31, 0.42)
REFLECTION_AMPLITUDES = (1.00, 0.75, 0.55, 0.40)
SHALLOW_FREQ_HZ = 32.0
DEEP_TARGET_T_S = 0.49
DEEP_TARGET_FREQ_HZ = 10.0
TARGET_AMPLITUDE = 0.10
WAVELET_HALF_LEN_S = 0.06
FAULT_THROW_S = 0.024
FAULT_T_MIN_S = 0.20
NOISY_SNR_DB = 6.0
CLEAN_SNR_DB = 30.0

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_ROOT = ROOT / "data" / "npy"


def ricker(freq_hz: float, dt_s: float) -> np.ndarray:
    """Zero-phase Ricker wavelet: (1 - 2a) * exp(-a), a = (pi*f*t)^2."""
    t = np.arange(-WAVELET_HALF_LEN_S, WAVELET_HALF_LEN_S + dt_s / 2, dt_s)
    a = (np.pi * freq_hz * t) ** 2
    return ((1.0 - 2.0 * a) * np.exp(-a)).astype(np.float32)


def add_wavelet(trace: np.ndarray, center_s: float, amp: float,
                wavelet: np.ndarray, dt_s: float) -> None:
    """Add a wavelet at ``center_s`` in place, clipping at trace boundaries."""
    center = int(round(center_s / dt_s))
    start = center - len(wavelet) // 2
    lo = max(0, start)
    hi = min(len(trace), start + len(wavelet))
    if hi > lo:
        trace[lo:hi] += amp * wavelet[lo - start:hi - start]


def horizon_time(h: int, il: int, xl: int, n_il: int, n_xl: int) -> float:
    """Base time of horizon ``h`` with gentle deterministic dip/undulation."""
    dip = 0.004 * (il / n_il - 0.5) + 0.003 * (xl / n_xl - 0.5)
    undulation = (0.006 * np.sin(2 * np.pi * xl / n_xl + 0.6 * h)
                  + 0.004 * np.sin(2 * np.pi * il / n_il + 0.3 * h))
    return HORIZONS_T_S[h] + dip + undulation


def fault_position(il: int, n_il: int, n_xl: int) -> float:
    """Crossline position of the fault plane, varying slowly with inline."""
    return 0.62 * n_xl + 5.0 * np.sin(2 * np.pi * il / n_il)


def target_inside(il: int, xl: int, n_il: int, n_xl: int) -> bool:
    """Elliptical footprint of the weak deep target."""
    c_il, c_xl = 0.42 * n_il, 0.30 * n_xl
    r_il, r_xl = 0.20 * n_il, 0.24 * n_xl
    return ((il - c_il) / r_il) ** 2 + ((xl - c_xl) / r_xl) ** 2 <= 1.0


def build_volume(seed: int, clean: bool, n_il: int, n_xl: int,
                 n_samples: int, dt_us: int) -> tuple[np.ndarray, dict, dict]:
    """Build the amplitude volume, ground-truth masks and provenance config."""
    dt_s = dt_us / 1_000_000.0
    rng = np.random.default_rng(seed)
    snr_db = CLEAN_SNR_DB if clean else NOISY_SNR_DB

    shape = (n_il, n_xl, n_samples)
    volume = np.zeros(shape, dtype=np.float32)
    fault_mask = np.zeros(shape, dtype=bool)
    horizon_mask = np.zeros(shape, dtype=bool)
    target_mask = np.zeros(shape, dtype=bool)

    shallow_w = ricker(SHALLOW_FREQ_HZ, dt_s)
    deep_w = ricker(DEEP_TARGET_FREQ_HZ, dt_s)

    for il in range(n_il):
        x_fault = fault_position(il, n_il, n_xl)
        fault_col = int(round(x_fault))
        for xl in range(n_xl):
            trace = np.zeros(n_samples, dtype=np.float32)

            for h in range(len(HORIZONS_T_S)):
                offset = FAULT_THROW_S if (h >= 1 and xl > x_fault) else 0.0
                t_h = horizon_time(h, il, xl, n_il, n_xl) + offset
                amp = REFLECTION_AMPLITUDES[h] * (
                    1.0 + 0.08 * np.sin(2 * np.pi * xl / n_xl + 0.4 * h))
                add_wavelet(trace, t_h, amp, shallow_w, dt_s)
                k = int(round(t_h / dt_s))
                horizon_mask[il, xl, max(0, k - 1):min(n_samples, k + 2)] = True

            if target_inside(il, xl, n_il, n_xl):
                amp = TARGET_AMPLITUDE * (
                    0.8 + 0.4 * np.sin(2 * np.pi * xl / n_xl))
                add_wavelet(trace, DEEP_TARGET_T_S, amp, deep_w, dt_s)
                k = int(round(DEEP_TARGET_T_S / dt_s))
                half = len(deep_w) // 2
                target_mask[il, xl,
                            max(0, k - half):min(n_samples, k + half)] = True

            volume[il, xl] = trace

        lo = max(0, fault_col - 1)
        hi = min(n_xl, fault_col + 2)
        k0 = int(FAULT_T_MIN_S / dt_s)
        fault_mask[il, lo:hi, k0:] = True

    rms = float(np.sqrt(np.mean(volume.astype(np.float64) ** 2)))
    if rms <= 0.0:
        raise RuntimeError("Synthetic reflectivity collapsed to zero amplitude")
    noise_rms = rms / (10.0 ** (snr_db / 20.0))
    volume += rng.normal(0.0, noise_rms, volume.shape).astype(np.float32)

    if not np.isfinite(volume).all():
        raise RuntimeError("Non-finite values in generated volume")

    masks = {
        "fault_mask.npy": fault_mask,
        "horizon_mask.npy": horizon_mask,
        "deep_target_mask.npy": target_mask,
    }
    cfg = {
        "seed": seed,
        "clean": clean,
        "snr_db": snr_db,
        "n_il": n_il,
        "n_xl": n_xl,
        "n_samples": n_samples,
        "dt_us": dt_us,
    }
    return volume, masks, cfg


def make_meta(cfg: dict, volume: np.ndarray, size_mb: float) -> dict:
    """Build metadata with every key required by ``src/npy_service.py``."""
    n_il, n_xl, n_samples = cfg["n_il"], cfg["n_xl"], cfg["n_samples"]
    dt_us = cfg["dt_us"]
    return {
        # --- SGSeg / npy_service.py required keys ---
        "source_file": "synthetic:scripts/generate_synthetic_seismic.py",
        "il_range": [1, n_il],
        "xl_range": [1, n_xl],
        "ilines": list(range(1, n_il + 1)),
        "xlines": list(range(1, n_xl + 1)),
        "samples": [round(k * dt_us / 1000.0, 3) for k in range(n_samples)],
        "n_inlines": n_il,
        "n_crosslines": n_xl,
        "n_samples": n_samples,
        "dt_us": dt_us,
        "shape": list(volume.shape),
        "size_mb": round(size_mb, 3),
        # --- provenance and reproducibility ---
        "synthetic": True,
        "generator": "scripts/generate_synthetic_seismic.py",
        "generator_version": GENERATOR_VERSION,
        "seed": cfg["seed"],
        "clean": cfg["clean"],
        "snr_db": cfg["snr_db"],
        "license": "MIT",
        "provenance": "docs/DATA_PROVENANCE.md",
        "frequencies_hz": {
            "shallow_horizons": SHALLOW_FREQ_HZ,
            "deep_target": DEEP_TARGET_FREQ_HZ,
        },
        "truth_masks": ["fault_mask.npy", "horizon_mask.npy",
                        "deep_target_mask.npy"],
    }


def write_outputs(out_dir: Path, name: str, volume: np.ndarray,
                  masks: dict, cfg: dict, preview: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    truth_dir = out_dir / "truth"
    truth_dir.mkdir(exist_ok=True)

    amp_path = out_dir / "amplitude.npy"
    np.save(str(amp_path), volume, allow_pickle=False)
    for filename, mask in masks.items():
        np.save(str(truth_dir / filename), mask, allow_pickle=False)

    meta = make_meta(cfg, volume, amp_path.stat().st_size / (1024 * 1024))
    (out_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    if preview:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8, 5), dpi=110)
            ax.imshow(volume[cfg["n_il"] // 2].T, aspect="auto", cmap="gray",
                      vmin=-1, vmax=1)
            ax.set_title(f"{name} — mid inline ({'clean' if cfg['clean'] else 'raw'})")
            ax.set_xlabel("crossline")
            ax.set_ylabel("sample")
            fig.tight_layout()
            fig.savefig(str(out_dir / "preview.png"))
            plt.close(fig)
        except Exception as exc:  # preview is optional, never fatal
            print(f"WARN  preview skipped: {exc}")

    print(f"OK    wrote {out_dir}")
    print(f"      shape={list(volume.shape)} dtype={volume.dtype} "
          f"seed={cfg['seed']} snr_db={cfg['snr_db']}")
    print(f"      amplitude min={volume.min():.4f} max={volume.max():.4f} "
          f"rms={float(np.sqrt(np.mean(volume.astype(np.float64) ** 2))):.4f}")


def verify(out_dir: Path) -> int:
    """Re-generate from stored metadata and assert byte-level equality."""
    amp_path = out_dir / "amplitude.npy"
    meta_path = out_dir / "meta.json"
    for p in (amp_path, meta_path):
        if not p.exists():
            print(f"FAIL  missing {p} — run the generator first")
            return 1

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    stored = np.load(str(amp_path), mmap_mode="r")
    volume, masks, cfg = build_volume(
        seed=int(meta["seed"]),
        clean=bool(meta["clean"]),
        n_il=int(meta["n_inlines"]),
        n_xl=int(meta["n_crosslines"]),
        n_samples=int(meta["n_samples"]),
        dt_us=int(meta["dt_us"]),
    )

    if volume.dtype != np.float32:
        print("FAIL  dtype is not float32")
        return 1
    if list(volume.shape) != list(stored.shape) or list(volume.shape) != meta["shape"]:
        print(f"FAIL  shape mismatch: generated={volume.shape} "
              f"stored={stored.shape} meta={meta['shape']}")
        return 1
    if not np.isfinite(volume).all():
        print("FAIL  non-finite values")
        return 1
    if not np.array_equal(volume, np.asarray(stored)):
        print("FAIL  deterministic check: regenerated bytes differ from stored")
        return 1
    if float(cfg["snr_db"]) != float(meta["snr_db"]):
        print("FAIL  SNR in meta.json does not match the generator configuration")
        return 1

    truth_dir = out_dir / "truth"
    for filename, expected in masks.items():
        p = truth_dir / filename
        if not p.exists():
            print(f"FAIL  missing ground-truth mask {p}")
            return 1
        got = np.load(str(p))
        if got.shape != expected.shape or not np.array_equal(got, expected):
            print(f"FAIL  ground-truth mask mismatch: {filename}")
            return 1

    print(f"OK    deterministic: {out_dir.name} is byte-identical for seed={meta['seed']}")
    print("OK    schema: float32, shape/meta consistent, all values finite")
    print("OK    ground truth: 3 masks present and reproducible")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic seismic demo volumes.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--name", default=None,
                        help="volume directory name (default: derived from --clean)")
    parser.add_argument("--clean", action="store_true",
                        help="low-noise variant representing a cleaner platform")
    parser.add_argument("--out", default=None,
                        help="explicit output directory (overrides --name)")
    parser.add_argument("--verify-only", action="store_true",
                        help="re-generate from meta.json and assert byte equality")
    parser.add_argument("--preview", action="store_true",
                        help="also write a PNG preview (needs matplotlib)")
    args = parser.parse_args()

    name = args.name or (DEFAULT_NAME + ("_clean" if args.clean else ""))
    out_dir = Path(args.out).resolve() if args.out else DEFAULT_OUT_ROOT / name

    if args.verify_only:
        return verify(out_dir)

    volume, masks, cfg = build_volume(
        seed=args.seed, clean=args.clean,
        n_il=DEFAULT_N_IL, n_xl=DEFAULT_N_XL,
        n_samples=DEFAULT_N_SAMPLES, dt_us=DEFAULT_DT_US)
    write_outputs(out_dir, name, volume, masks, cfg, args.preview)
    return verify(out_dir)


if __name__ == "__main__":
    sys.exit(main())
