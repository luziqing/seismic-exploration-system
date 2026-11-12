"""qc_service: label-free QC on constructed slices (spec qc-refine-loop, Requirements 1-2)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import qc_service as qc  # noqa: E402

ROWS, COLS = 120, 48
DT_S = 0.002
SEED = [(64, 19)]                                 # an interior click on the block


def _block_slice(seed=0, amp=1.0, noise=0.05):
    """A 10 Hz wavelet train inside rows 50..79, cols 10..29, on weak noise. Returns slice and exact mask."""
    # the interpreter clicks at SEED
    rng = np.random.default_rng(seed)
    s = rng.normal(0.0, noise, (ROWS, COLS))
    t = np.arange(ROWS) * DT_S
    trace = amp * np.sin(2 * np.pi * 10.0 * t)
    s[50:80, 10:30] += trace[50:80, None]
    mask = np.zeros((ROWS, COLS), bool)
    mask[50:80, 10:30] = True
    return s.astype(np.float32), mask


def test_exact_mask_scores_well_and_returns_constants():
    s, m = _block_slice()
    r = qc.score_mask(s, m, SEED)
    assert r["reason"] is None and r["envelope"] == "hilbert"
    assert r["contrast_db"] > 6.0 and r["score"] > 0.5 and r["reference_envelope"] > 0
    assert r["constants"] == qc.constants()
    assert r["leak_map"].shape == m.shape and not (r["leak_map"] & ~m).any()
    assert not (r["miss_map"] & m).any()


def test_adding_background_raises_leak_and_lowers_score():
    s, m = _block_slice()
    exact = qc.score_mask(s, m, SEED)
    grown = m.copy()
    grown[80:110, 10:30] = True                   # 30 rows of plain noise below the target
    worse = qc.score_mask(s, grown, SEED)
    assert worse["leak"] > exact["leak"]
    assert worse["score"] < exact["score"]
    big = qc.largest_region(worse["leak_map"])
    rows = np.nonzero(big)[0]
    assert big.any() and (rows >= 80).mean() > 0.9        # the largest leak lies (almost all) in the added background


def test_leaving_out_target_raises_miss_and_lowers_score():
    s, m = _block_slice()
    exact = qc.score_mask(s, m, SEED)
    partial = m.copy()
    partial[:, 20:30] = False                     # only half of the target
    worse = qc.score_mask(s, partial, SEED)
    assert worse["miss"] > exact["miss"]
    assert worse["score"] < exact["score"]
    big = qc.largest_region(worse["miss_map"])
    assert big.any() and np.nonzero(big)[1].min() >= 20   # the largest miss lies in the left-out half of the target


def test_no_click_inside_slice_scores_zero_with_reason():
    s, m = _block_slice()
    for seeds in ([], None, [(-5, 3)], [(ROWS + 1, 0)]):
        r = qc.score_mask(s, m, seeds)
        assert r["score"] == 0.0 and r["reason"] == "no positive click inside the slice"


def test_growing_into_a_brighter_reflector_lowers_score():
    """The failure mode found on the demo volumes: a brighter horizon just above the target."""
    s, m = _block_slice()
    t = np.arange(ROWS) * DT_S
    s[38:46, :] += (4.0 * np.sin(2 * np.pi * 32.0 * t))[38:46, None]   # bright 32 Hz reflector 4-12 rows above the target
    exact = qc.score_mask(s, m, SEED)
    up = m.copy()
    up[36:50, 10:30] = True                                               # mask grown up into the reflector
    worse = qc.score_mask(s, up, SEED)
    assert worse["leak"] > exact["leak"] and worse["score"] < exact["score"]


@pytest.mark.parametrize("make,reason", [
    (lambda m: np.zeros_like(m), "empty mask"),
    (lambda m: np.ones_like(m), "mask leaves no ring (covers the slice)"),
])
def test_degenerate_masks_score_zero_with_reason(make, reason):
    s, m = _block_slice()
    r = qc.score_mask(s, make(m), SEED)
    assert r["score"] == 0.0 and r["reason"] == reason
    assert r["leak_map"].shape == m.shape


def test_silent_background_keeps_json_finite():
    s = np.zeros((40, 40), np.float32)
    s[10:20, 10:20] = 1.0
    m = np.zeros(s.shape, bool)
    m[10:20, 10:20] = True
    r = qc.score_mask(s, m, [(15, 15)], direction="timeslice")
    assert r["envelope"] == "abs" and r["contrast_db"] is None and r["score"] == 1.0


def test_timeslice_uses_abs_amplitude():
    s, m = _block_slice()
    assert qc.score_mask(s, m, SEED, direction="timeslice")["envelope"] == "abs"


def test_deterministic():
    s, m = _block_slice()
    a, b = qc.public(qc.score_mask(s, m, SEED)), qc.public(qc.score_mask(s.copy(), m.copy(), SEED))
    assert a == b


@pytest.mark.parametrize("args", [
    (np.zeros((5, 5)), np.zeros((5, 6), bool), "deep_target"),
    (np.zeros((5, 5)), np.zeros((5, 5), bool), "horizon"),
    (np.full((5, 5), np.nan), np.ones((5, 5), bool), "deep_target"),
])
def test_invalid_input(args):
    with pytest.raises(ValueError):
        qc.score_mask(args[0], args[1], [(0, 0)], args[2])


# ── Fault continuity ─────────────────────────────────────────────────────────

def _fault_mask():
    m = np.zeros((ROWS, COLS), bool)
    for r in range(20, 100):
        c = 20 + (r - 20) // 10                   # steps one trace every 10 rows
        m[r, c:c + 2] = True
    return m


def test_continuous_fault_scores_one():
    f = qc.fault_continuity(_fault_mask())
    assert f["continuity"] == 1.0 and f["fragments"] == 1


def test_gap_lowers_fault_score():
    m = _fault_mask()
    whole = qc.score_mask(np.ones((ROWS, COLS), np.float32), m, SEED, target_type="fault")
    m[55:65] = False
    gap = qc.score_mask(np.ones((ROWS, COLS), np.float32), m, SEED, target_type="fault")
    assert gap["continuity"] < whole["continuity"] and gap["fragments"] == 2
    assert gap["score"] < whole["score"]


def test_detached_fragment_lowers_fault_score():
    m = _fault_mask()
    whole = qc.score_mask(np.ones((ROWS, COLS), np.float32), m, SEED, target_type="fault")
    m[30:35, 40:42] = True                        # isolated blob away from the fault, same rows
    frag = qc.score_mask(np.ones((ROWS, COLS), np.float32), m, SEED, target_type="fault")
    assert frag["fragments"] == 2 and frag["score"] < whole["score"]


def test_largest_region_empty_and_ties():
    assert not qc.largest_region(np.zeros((4, 4), bool)).any()
    m = np.zeros((6, 6), bool)
    m[0, 0] = m[5, 5] = True
    r = qc.largest_region(m)
    assert r.sum() == 1 and r[0, 0]
