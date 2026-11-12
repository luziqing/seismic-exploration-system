"""Survey-map footprint of a volume mask: voxels per trace as (nIL, nXL), via service and API."""
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import server  # noqa: E402
import volume_mask_service as vms  # noqa: E402

SHAPE = (6, 8, 20)  # nIL, nXL, nSamples — all different to expose axis mix-ups


@pytest.fixture()
def vol(tmp_path, monkeypatch):
    d = tmp_path / "npy" / "vol"
    d.mkdir(parents=True)
    np.save(d / "amplitude.npy", np.zeros(SHAPE, dtype=np.float32))
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    return d


def _write_inline(d, il, rows, cols):
    m = np.zeros((SHAPE[2], SHAPE[1]), dtype=np.float32)  # inline image: (nSamples, nXL)
    m[rows[0]:rows[1], cols[0]:cols[1]] = 1
    vms.write_slice_mask(str(d), "sam_mask", "inline", il, m)


def test_footprint_counts_voxels_per_trace(vol):
    _write_inline(vol, 2, rows=(5, 9), cols=(1, 4))     # 4 samples on XL 1..3
    _write_inline(vol, 4, rows=(0, 10), cols=(6, 8))    # 10 samples on XL 6..7
    fp = vms.mask_footprint(str(vol), "sam_mask")
    assert fp.shape == (SHAPE[0], SHAPE[1]) and fp.dtype == np.float32
    expected = np.zeros(SHAPE[:2], dtype=np.float32)
    expected[2, 1:4] = 4
    expected[4, 6:8] = 10
    np.testing.assert_array_equal(fp, expected)


def test_footprint_endpoint_binary_contract(vol):
    _write_inline(vol, 3, rows=(2, 5), cols=(0, 2))
    c = TestClient(server.app)
    r = c.get("/api/npy/vol/mask/sam_mask/footprint")
    assert r.status_code == 200
    assert (int(r.headers["X-Rows"]), int(r.headers["X-Cols"])) == SHAPE[:2]
    fp = np.frombuffer(r.content, dtype=np.float32).reshape(SHAPE[:2])
    assert fp[3, 0] == 3 and fp[3, 1] == 3 and fp.sum() == 6


@pytest.mark.parametrize("path,code", [
    ("/api/npy/vol/mask/none_yet/footprint", 404),
    ("/api/npy/vol/mask/bad%20name/footprint", 400),
    ("/api/npy/missing/mask/sam_mask/footprint", 404),
])
def test_footprint_errors(vol, path, code):
    assert TestClient(server.app).get(path).status_code == code
