"""
Label-free quality control of one 2-D segmentation mask on one seismic slice (scope S4,
spec .kiro/specs/qc-refine-loop/).

Every metric is computed from the slice itself (its envelope); no ground truth is read here.
All thresholds are declared constants below, chosen from their definitions before any run and
not tuned on the demo volume. They are returned with every result.

Orientation: inline / crossline slices are (samples, traces), time is axis 0. Time slices have no
time axis, so the envelope falls back to |amplitude| and the result says so.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.signal import hilbert

# ── Declared constants (reason in the comment; see design.md) ────────────────
RING_PX = 4                 # 8 ms vertically / 4 traces laterally: local background, small next to the 41-sample target window
BG_PERCENTILE = 75          # a mask pixel weaker than 3/4 of the ring looks like background ("leak")
TARGET_PERCENTILE = 25      # a ring pixel stronger than the weakest 1/4 of the mask looks like target ("miss")
CONTRAST_REF_DB = 6.0       # contrast at which the contrast term saturates: envelope amplitude doubled
CONTINUITY_TOL_COLS = 1     # a fault may step one trace per sample row

TARGET_TYPES = ("deep_target", "fault")
DIRECTIONS_WITH_TIME_AXIS = ("inline", "crossline")


def constants() -> dict:
    return {"RING_PX": RING_PX, "BG_PERCENTILE": BG_PERCENTILE, "TARGET_PERCENTILE": TARGET_PERCENTILE,
            "CONTRAST_REF_DB": CONTRAST_REF_DB, "CONTINUITY_TOL_COLS": CONTINUITY_TOL_COLS}


def envelope(slice2d: np.ndarray, direction: str = "inline") -> tuple[np.ndarray, str]:
    """Instantaneous amplitude along time for inline / crossline; |amplitude| for time slices."""
    a = np.asarray(slice2d, dtype=np.float64)
    if direction in DIRECTIONS_WITH_TIME_AXIS and a.shape[0] >= 2:
        return np.abs(hilbert(a, axis=0)), "hilbert"
    return np.abs(a), "abs"


def ring_of(mask: np.ndarray, width: int = RING_PX) -> np.ndarray:
    """Pixels within `width` (chessboard distance) of the mask but outside it."""
    if not mask.any():
        return np.zeros_like(mask)
    grown = ndimage.binary_dilation(mask, structure=np.ones((3, 3), bool), iterations=width)
    return grown & ~mask


def _empty_result(reason: str, kind: str, target_type: str, shape) -> dict:
    z = np.zeros(shape, dtype=bool)
    return {"score": 0.0, "reason": reason, "target_type": target_type, "envelope": kind,
            "contrast_db": None, "leak": None, "miss": None, "mask_pixels": 0, "ring_pixels": 0,
            "leak_map": z, "miss_map": z, "constants": constants()}


def score_mask(slice2d: np.ndarray, mask: np.ndarray, target_type: str = "deep_target",
               direction: str = "inline") -> dict:
    """
    QC of `mask` on `slice2d` (same shape). Returns scalar metrics, the composite `score` in [0, 1],
    and boolean `leak_map` / `miss_map` for the refinement driver. Deterministic.
    """
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Unknown target_type: {target_type!r} (expected one of {TARGET_TYPES})")
    s = np.asarray(slice2d)
    m = np.asarray(mask, dtype=bool)
    if s.ndim != 2 or s.shape != m.shape:
        raise ValueError(f"slice and mask must be 2-D with the same shape, got {s.shape} and {m.shape}")
    if not np.isfinite(s).all():
        raise ValueError("slice contains NaN or Inf")

    env, kind = envelope(s, direction)
    if not m.any():
        return _empty_result("empty mask", kind, target_type, m.shape)
    ring = ring_of(m)
    if not ring.any():
        return _empty_result("mask leaves no ring (covers the slice)", kind, target_type, m.shape)

    env_in, env_ring = env[m], env[ring]
    m_in, m_ring = float(np.median(env_in)), float(np.median(env_ring))
    p_ring = float(np.percentile(env_ring, BG_PERCENTILE))
    p_in = float(np.percentile(env_in, TARGET_PERCENTILE))
    leak_map = m & (env <= p_ring)
    miss_map = ring & (env >= p_in)
    leak = float(leak_map.sum() / m.sum())
    miss = float(miss_map.sum() / ring.sum())
    if m_ring > 0 and m_in > 0:
        contrast_db = float(20.0 * np.log10(m_in / m_ring))
        contrast_term = float(np.clip(contrast_db / CONTRAST_REF_DB, 0.0, 1.0))
    else:   # silent ring (all-zero background) or silent mask: ratio undefined, keep JSON finite
        contrast_db = None
        contrast_term = 1.0 if m_in > m_ring else 0.0

    out = {"target_type": target_type, "envelope": kind, "reason": None,
           "contrast_db": contrast_db, "leak": leak, "miss": miss,
           "mask_pixels": int(m.sum()), "ring_pixels": int(ring.sum()),
           "median_env_mask": m_in, "median_env_ring": m_ring,
           "leak_map": leak_map, "miss_map": miss_map, "constants": constants()}

    if target_type == "fault":
        f = fault_continuity(m)
        out.update(f)
        out["score"] = float(f["continuity"] / max(1, f["fragments"]))
    else:
        out["score"] = contrast_term * (1.0 - leak) * (1.0 - miss)
    return out


def fault_continuity(mask: np.ndarray) -> dict:
    """
    Continuity of a near-vertical fault mask on an inline / crossline slice (rows = samples).
    continuity = share of consecutive row pairs in the mask's vertical extent that are both present and
    whose column centres differ by at most CONTINUITY_TOL_COLS; fragments = 8-connected components.
    """
    m = np.asarray(mask, dtype=bool)
    rows = np.flatnonzero(m.any(axis=1))
    _, n_frag = ndimage.label(m, structure=np.ones((3, 3), bool))
    if rows.size < 2:
        return {"continuity": 0.0, "fragments": int(n_frag), "rows_present": int(rows.size), "rows_spanned": int(rows.size)}
    cols = np.arange(m.shape[1])
    good = 0
    pairs = rows[-1] - rows[0]
    for r in range(rows[0], rows[-1]):
        a, b = m[r], m[r + 1]
        if a.any() and b.any() and abs(cols[a].mean() - cols[b].mean()) <= CONTINUITY_TOL_COLS:
            good += 1
    return {"continuity": float(good / pairs), "fragments": int(n_frag),
            "rows_present": int(rows.size), "rows_spanned": int(pairs + 1)}


def largest_region(region_map: np.ndarray) -> np.ndarray:
    """The largest 8-connected component of a boolean map (empty map if none); ties: lowest label."""
    lab, n = ndimage.label(np.asarray(region_map, bool), structure=np.ones((3, 3), bool))
    if n == 0:
        return np.zeros_like(region_map, dtype=bool)
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    return lab == (int(np.argmax(sizes)) + 1)


def public(result: dict) -> dict:
    """Result without the boolean maps, for JSON responses and logs."""
    return {k: v for k, v in result.items() if k not in ("leak_map", "miss_map")}
