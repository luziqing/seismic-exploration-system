"""propagation_service: point-prompt generation, propagation box, step/expansion limits, stop conditions (SAM stubbed, no GPU required)"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import propagation_service as ps  # noqa: E402
import volume_mask_service as vms  # noqa: E402

SHAPE = (30, 16, 40)  # nIL, nXL, nS


@pytest.fixture()
def vol_dir(tmp_path):
    d = tmp_path / "vol"
    d.mkdir()
    np.save(d / "amplitude.npy", np.random.default_rng(0).normal(size=SHAPE).astype(np.float32))
    return d


def _seed_inline(vol_dir, il=15, rows=(10, 20), cols=(4, 10)):
    m = np.zeros((SHAPE[2], SHAPE[1]), dtype=np.float32)
    m[rows[0]:rows[1], cols[0]:cols[1]] = 1
    vms.write_slice_mask(str(vol_dir), "m", "inline", il, m)
    return m


def test_mask_to_points_inside_mask_and_spread():
    m = np.zeros((60, 80), dtype=bool)
    m[10:50, 10:70] = True
    m[0:3, 0:3] = True  # small noisy connected component, should be ignored
    pts = ps.mask_to_points(m)
    assert 1 <= len(pts) <= ps.MAX_POINTS
    assert all(m[r, c] for r, c in pts)
    assert all(r >= 10 and c >= 10 for r, c in pts)
    assert len(set(pts)) == len(pts)
    assert ps.mask_to_points(np.zeros((5, 5), dtype=bool)) == []


def test_build_box_propagation_axis_and_margins():
    seed = np.zeros((40, 16), dtype=bool)
    seed[10:20, 4:10] = True
    b = ps.build_box("inline", 15, seed, SHAPE, max_il=5, max_xl=2, max_vertical=3)
    assert b == {"il": (10, 20), "xl": (2, 11), "s": (7, 22)}
    b = ps.build_box("inline", 2, seed, SHAPE, 5, 100, 100)  # clipped when out of bounds
    assert b["il"] == (0, 7) and b["xl"] == (0, 15) and b["s"] == (0, 39)
    # crossline: seed rows=sample cols=il
    b = ps.build_box("crossline", 8, seed, SHAPE, max_il=1, max_xl=4, max_vertical=0)
    assert b == {"il": (3, 10), "xl": (4, 12), "s": (10, 19)}


def test_box_mask_2d_orientation():
    box = {"il": (2, 4), "xl": (5, 6), "s": (10, 12)}
    a = ps.box_mask_2d("inline", (40, 16), box)      # rows=s cols=xl
    assert a.sum() == 3 * 2 and a[10:13, 5:7].all()
    a = ps.box_mask_2d("crossline", (40, 30), box)   # rows=s cols=il
    assert a.sum() == 3 * 3 and a[10:13, 2:5].all()
    a = ps.box_mask_2d("timeslice", (30, 16), box)   # rows=il cols=xl
    assert a.sum() == 3 * 2 and a[2:5, 5:7].all()


def _stub(monkeypatch, fn):
    monkeypatch.setattr(ps, "_infer_slice", lambda d, direction, i, prev: fn(i, prev))


def test_default_limit_five_each_side_and_clip_to_box(vol_dir, monkeypatch):
    _seed_inline(vol_dir)
    # stub: always return a mask larger than seed (+8 cols), should be clipped by propagation box (xl margin 2)
    def grow(i, prev):
        out = np.zeros(prev.shape, dtype=bool)
        out[8:22, 0:16] = True
        return out, 0.9, [{"row": 15, "col": 6, "label": 1}]
    _stub(monkeypatch, grow)
    r = ps.propagate(str(vol_dir), "m", "inline", 15, max_il=5, max_xl=2, max_vertical=3, min_iou=0.0)
    assert r["written_indices"] == list(range(10, 15)) + list(range(16, 21))  # ±5, excluding seed
    assert r["box"] == {"il": [10, 20], "xl": [2, 11], "s": [7, 22]}
    vol = np.asarray(vms.read_mask_volume(str(vol_dir), "m"))
    ii, xx, ss = np.nonzero(vol)
    assert ii.min() == 10 and ii.max() == 20
    assert xx.min() >= 2 and xx.max() <= 11   # horizontal expansion limited
    assert ss.min() >= 7 and ss.max() <= 22   # vertical expansion limited
    assert not vol[9].any() and not vol[21].any()


def test_zero_range_propagates_nothing(vol_dir, monkeypatch):
    _seed_inline(vol_dir)
    _stub(monkeypatch, lambda i, prev: pytest.fail("should not be called"))
    r = ps.propagate(str(vol_dir), "m", "inline", 15, max_il=0)
    assert r["written_indices"] == [] and r["slices"] == []


def test_stop_on_empty_and_low_iou(vol_dir, monkeypatch):
    seed = _seed_inline(vol_dir)
    seed_b = seed.astype(bool)

    def fn(i, prev):
        if i == 17:   # 2nd slice on + side is empty -> stop; 18+ not processed
            return np.zeros(prev.shape, dtype=bool), 0.0, []
        if i == 13:   # 2nd slice on - side has zero overlap with previous -> low_iou
            out = np.zeros(prev.shape, dtype=bool); out[30:38, 12:16] = True
            return out, 0.5, []
        return seed_b.copy(), 0.8, []
    _stub(monkeypatch, fn)
    r = ps.propagate(str(vol_dir), "m", "inline", 15, max_il=5, max_xl=10, max_vertical=30, min_iou=0.2)
    assert r["written_indices"] == [14, 16]
    stopped = {s["index"]: s["stopped"] for s in r["slices"] if s["stopped"]}
    assert stopped == {17: "empty", 13: "low_iou"}
    assert [s["index"] for s in r["slices"]] == [16, 17, 14, 13]


def test_empty_seed_and_bad_args(vol_dir):
    vms.write_slice_mask(str(vol_dir), "m", "inline", 3, np.zeros((40, 16), dtype=np.float32))
    with pytest.raises(ValueError, match="is empty"):
        ps.propagate(str(vol_dir), "m", "inline", 15)
    _seed_inline(vol_dir)
    with pytest.raises(ValueError):
        ps.propagate(str(vol_dir), "m", "inline", 15, max_il=-1)
    with pytest.raises(ValueError):
        ps.propagate(str(vol_dir), "m", "diagonal", 15)
    with pytest.raises(IndexError):
        ps.propagate(str(vol_dir), "m", "inline", 999)
