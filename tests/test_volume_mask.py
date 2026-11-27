"""volume_mask_service: slice mask -> 3D voxel mask back-projection (uses small temp volume, never touches data/)"""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import volume_mask_service as vms  # noqa: E402

SHAPE = (6, 8, 20)  # nIL, nXL, nSamples (deliberately unequal to expose axis confusion)


@pytest.fixture()
def vol_dir(tmp_path):
    d = tmp_path / "vol"
    d.mkdir()
    np.save(d / "amplitude.npy", np.zeros(SHAPE, dtype=np.float32))
    return d


def _truth():
    t = np.zeros(SHAPE, dtype=bool)
    t[1:4, 2:6, 5:15] = True
    return t


def _slice_img(t, direction, i):
    if direction == "inline":
        return t[i].T
    if direction == "crossline":
        return t[:, i, :].T
    return t[:, :, i]


def _upscale(m, fy, fx):
    img = Image.fromarray(m.astype(np.uint8) * 255).resize((m.shape[1] * fx, m.shape[0] * fy), Image.BILINEAR)
    return (np.asarray(img) / 255.0).astype(np.float32)


@pytest.mark.parametrize("direction,idx", [("inline", 2), ("crossline", 3), ("timeslice", 10)])
def test_roundtrip_upscaled_mask_lands_in_right_voxels(vol_dir, direction, idx):
    t = _truth()
    big = _upscale(_slice_img(t, direction, idx), 7, 5)  # simulate upscaled frontend SAM output
    r = vms.write_slice_mask(str(vol_dir), "m", direction, idx, big)
    vol = vms.read_mask_volume(str(vol_dir), "m")
    expected = np.zeros(SHAPE, dtype=bool)
    if direction == "inline":
        expected[idx] = t[idx]
    elif direction == "crossline":
        expected[:, idx, :] = t[:, idx, :]
    else:
        expected[:, :, idx] = t[:, :, idx]
    assert np.array_equal(np.asarray(vol), expected)
    assert r["total_voxels"] == int(expected.sum()) > 0


def test_downscaled_mask_and_replace_vs_union(vol_dir):
    t = _truth()
    a = _slice_img(t, "inline", 2)
    vms.write_slice_mask(str(vol_dir), "m", "inline", 2, a.astype(np.float32))
    other = np.zeros_like(a)
    other[0, 0] = True
    vms.write_slice_mask(str(vol_dir), "m", "inline", 2, other.astype(np.float32), mode="union")
    assert int(np.asarray(vms.read_mask_volume(str(vol_dir), "m"))[2].sum()) == int(a.sum()) + 1
    vms.write_slice_mask(str(vol_dir), "m", "inline", 2, other.astype(np.float32), mode="replace")
    assert int(np.asarray(vms.read_mask_volume(str(vol_dir), "m"))[2].sum()) == 1


def test_multi_slice_builds_3d_and_info_coords(vol_dir):
    t = _truth()
    for i in range(1, 4):
        vms.write_slice_mask(str(vol_dir), "m", "inline", i, _slice_img(t, "inline", i).astype(np.float32))
    assert np.array_equal(np.asarray(vms.read_mask_volume(str(vol_dir), "m")), t)
    meta = {"ilines": list(range(100, 106)), "xlines": list(range(200, 208)),
            "samples": [2.0 * k for k in range(20)]}
    info = vms.get_mask_info(str(vol_dir), "m", meta)
    assert info["voxel_count"] == int(t.sum())
    assert info["bbox_coords"]["min"] == {"il": 101, "xl": 202, "sample": 10.0}
    assert info["bbox_coords"]["max"] == {"il": 103, "xl": 205, "sample": 28.0}
    assert info["centroid_coords"]["il"] == pytest.approx(102.0)
    assert len(info["slices"]) == 3


def test_validation_errors(vol_dir):
    ok = np.ones((4, 4), dtype=np.float32)
    with pytest.raises(IndexError):
        vms.write_slice_mask(str(vol_dir), "m", "inline", SHAPE[0], ok)
    with pytest.raises(ValueError):
        vms.write_slice_mask(str(vol_dir), "m", "diagonal", 0, ok)
    with pytest.raises(ValueError):
        vms.write_slice_mask(str(vol_dir), "../evil", "inline", 0, ok)
    with pytest.raises(ValueError):
        vms.write_slice_mask(str(vol_dir), "m", "inline", 0, np.full((4, 4), np.nan))
    with pytest.raises(ValueError):
        vms.write_slice_mask(str(vol_dir), "m", "inline", 0, [1.0, 2.0])
