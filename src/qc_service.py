"""
Label-free quality control of one 2-D segmentation mask on one seismic slice (scope S4,
spec .kiro/specs/qc-refine-loop/).

Every metric is computed from the slice itself (its envelope); no ground truth is read here.
"Target-like" is defined relative to the envelope where the interpreter clicked (option C, owner
decision 2026-11-12, after the first percentile-based design failed Requirement 1.3). All thresholds
are declared constants below, checked only on constructed scenes, and returned with every result.

Orientation: inline / crossline slices are (samples, traces), time is axis 0. Time slices have no
time axis, so the envelope falls back to |amplitude| and the result says so.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.signal import hilbert

# ── Declared constants (reason in the comment; see design.md) ────────────────
# Option C (owner decision 2026-11-12): "target-like" is defined relative to the envelope where the
# interpreter clicked. Chosen from these definitions and checked only on constructed scenes
# (tests/test_qc_service_pbt.py), not on the demo volumes.
SEED_HALF = 2               # 5 x 5 native pixels around a click: stable median, stays inside a target several traces wide
TARGET_BAND_DB = 6.0        # within a factor of 2 in envelope amplitude of the clicked area = the same kind of reflector
GUARD_PX = 2                # skip the envelope halo right next to the mask edge
RING_PX = 4                 # 4 native pixels (8 ms vertically, 4 traces laterally) of local background beyond the guard
SCORE_RESOLUTION = 0.01     # score differences below this carry no meaning (largest property-test excess: 0.0089); = loop MIN_GAIN
GATE_MAX_TARGET_LIKE_FRAC = 0.5   # if most of the slice looks like the clicked area, the click singles nothing out -> unreliable
CONTINUITY_TOL_COLS = 1     # a fault may step one trace per sample row

TARGET_TYPES = ("deep_target", "fault")
DIRECTIONS_WITH_TIME_AXIS = ("inline", "crossline")
_CHESS = np.ones((3, 3), bool)


def constants() -> dict:
    return {"SEED_HALF": SEED_HALF, "TARGET_BAND_DB": TARGET_BAND_DB, "GUARD_PX": GUARD_PX,
            "RING_PX": RING_PX, "SCORE_RESOLUTION": SCORE_RESOLUTION,
            "GATE_MAX_TARGET_LIKE_FRAC": GATE_MAX_TARGET_LIKE_FRAC, "CONTINUITY_TOL_COLS": CONTINUITY_TOL_COLS}


def envelope(slice2d: np.ndarray, direction: str = "inline") -> tuple[np.ndarray, str]:
    """Instantaneous amplitude along time for inline / crossline; |amplitude| for time slices."""
    a = np.asarray(slice2d, dtype=np.float64)
    if direction in DIRECTIONS_WITH_TIME_AXIS and a.shape[0] >= 2:
        return np.abs(hilbert(a, axis=0)), "hilbert"
    return np.abs(a), "abs"


def _dilate(mask: np.ndarray, n: int) -> np.ndarray:
    return ndimage.binary_dilation(mask, structure=_CHESS, iterations=n) if n > 0 else mask.copy()


def ring_of(mask: np.ndarray, guard: int = GUARD_PX, width: int = RING_PX) -> np.ndarray:
    """Pixels between `guard` and `guard + width` (chessboard distance) outside the mask."""
    if not mask.any():
        return np.zeros_like(mask)
    return _dilate(mask, guard + width) & ~_dilate(mask, guard)


def reference_envelope(env: np.ndarray, seeds) -> float | None:
    """Median envelope in (2*SEED_HALF+1)^2 windows around the positive clicks inside the slice, or None."""
    rows, cols = env.shape
    window = np.zeros(env.shape, bool)
    for r, c in seeds or ():
        r, c = int(round(r)), int(round(c))
        if 0 <= r < rows and 0 <= c < cols:
            window[max(0, r - SEED_HALF):r + SEED_HALF + 1, max(0, c - SEED_HALF):c + SEED_HALF + 1] = True
    if not window.any():
        return None
    ref = float(np.median(env[window]))
    return ref if ref > 0 else None


def target_like(env: np.ndarray, ref: float) -> np.ndarray:
    """Pixels whose envelope is within TARGET_BAND_DB of the reference."""
    lo, hi = ref * 10.0 ** (-TARGET_BAND_DB / 20.0), ref * 10.0 ** (TARGET_BAND_DB / 20.0)
    return (env >= lo) & (env <= hi)


def _empty_result(reason: str, kind: str, target_type: str, shape) -> dict:
    z = np.zeros(shape, dtype=bool)
    return {"score": 0.0, "reason": reason, "target_type": target_type, "envelope": kind,
            "reliable": False, "target_like_fraction": None, "unreliable_reason": reason,
            "contrast_db": None, "leak": None, "miss": None, "reference_envelope": None,
            "mask_pixels": 0, "ring_pixels": 0, "leak_map": z, "miss_map": z, "constants": constants()}


def score_mask(slice2d: np.ndarray, mask: np.ndarray, seeds, target_type: str = "deep_target",
               direction: str = "inline") -> dict:
    """
    QC of `mask` on `slice2d` (same shape), relative to the interpreter's positive clicks `seeds`
    (iterable of native-grid (row, col)). Returns scalar metrics, the composite `score` in [0, 1],
    and boolean `leak_map` / `miss_map` for the refinement driver. Deterministic; reads no truth.
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
    ref = reference_envelope(env, seeds)
    if ref is None:
        return _empty_result("no positive click inside the slice", kind, target_type, m.shape)

    like = target_like(env, ref)
    tl_frac = float(like.mean())
    reliable = tl_frac <= GATE_MAX_TARGET_LIKE_FRAC
    leak_map = m & ~like
    miss_map = ring & like
    leak = float(leak_map.sum() / m.sum())
    miss = float(miss_map.sum() / ring.sum())
    m_in, m_ring = float(np.median(env[m])), float(np.median(env[ring]))
    contrast_db = float(20.0 * np.log10(m_in / m_ring)) if m_in > 0 and m_ring > 0 else None

    out = {"target_type": target_type, "envelope": kind, "reason": None,
           "reliable": reliable, "target_like_fraction": tl_frac,
           "unreliable_reason": None if reliable else (
               f"{tl_frac:.0%} of the slice looks like the clicked area (limit {GATE_MAX_TARGET_LIKE_FRAC:.0%}): "
               "the target is too weak for label-free QC on this slice"),
           "contrast_db": contrast_db, "leak": leak, "miss": miss, "reference_envelope": ref,
           "mask_pixels": int(m.sum()), "ring_pixels": int(ring.sum()),
           "median_env_mask": m_in, "median_env_ring": m_ring,
           "leak_map": leak_map, "miss_map": miss_map, "constants": constants()}

    if target_type == "fault":
        f = fault_continuity(m)
        out.update(f)
        out["score"] = float(f["continuity"] / max(1, f["fragments"]))
    else:
        out["score"] = (1.0 - leak) * (1.0 - miss)
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
