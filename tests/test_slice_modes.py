"""Slice endpoints with ?mode=raw|lowfreq (S1): same binary contract, raw volume untouched."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import lowfreq_service  # noqa: E402
import server  # noqa: E402

SHAPE = (6, 5, 128)  # nIL, nXL, nSamples
DT_US = 2000


@pytest.fixture()
def client(tmp_path, monkeypatch):
    vol_dir = tmp_path / "npy" / "vol"
    vol_dir.mkdir(parents=True)
    t = np.arange(SHAPE[2]) * DT_US * 1e-6
    trace = 0.5 * np.sin(2 * np.pi * 8.0 * t) + 1.0 * np.sin(2 * np.pi * 60.0 * t)
    rng = np.random.default_rng(0)
    vol = (trace[None, None, :] * rng.uniform(0.5, 1.5, SHAPE[:2])[:, :, None]).astype(np.float32)
    np.save(vol_dir / "amplitude.npy", vol)
    (vol_dir / "meta.json").write_text(json.dumps({"dt_us": DT_US}), encoding="utf-8")
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    lowfreq_service._conditioned_volume.cache_clear()
    return TestClient(server.app), vol_dir, vol


def _get(c, path):
    r = c.get(path)
    assert r.status_code == 200, r.text
    rows, cols = int(r.headers["X-Rows"]), int(r.headers["X-Cols"])
    return np.frombuffer(r.content, dtype=np.float32).reshape(rows, cols)


@pytest.mark.parametrize("direction,index,expected", [
    ("inline", 2, lambda v: v[2].T),
    ("crossline", 3, lambda v: v[:, 3, :].T),
    ("timeslice", 40, lambda v: v[:, :, 40]),
])
def test_raw_default_unchanged_and_lowfreq_same_shape(client, direction, index, expected):
    c, _, vol = client
    raw_default = _get(c, f"/api/npy/vol/slice/{direction}/{index}")
    raw = _get(c, f"/api/npy/vol/slice/{direction}/{index}?mode=raw")
    low = _get(c, f"/api/npy/vol/slice/{direction}/{index}?mode=lowfreq")
    np.testing.assert_array_equal(raw_default, expected(vol))
    np.testing.assert_array_equal(raw, raw_default)
    assert low.shape == raw.shape
    assert not np.allclose(low, raw)


def test_lowfreq_matches_service_and_removes_high_band(client):
    c, _, vol = client
    low = _get(c, "/api/npy/vol/slice/inline/1?mode=lowfreq")
    np.testing.assert_allclose(low, lowfreq_service.condition_slice(vol[1].T, dt_us=DT_US), atol=1e-6)
    freqs = np.fft.rfftfreq(SHAPE[2], d=DT_US * 1e-6)
    k60 = np.argmin(np.abs(freqs - 60.0))
    k8 = np.argmin(np.abs(freqs - 8.0))
    spec_raw = np.abs(np.fft.rfft(vol[1].T[:, 0]))
    spec_low = np.abs(np.fft.rfft(low[:, 0]))
    assert spec_low[k60] < 0.1 * spec_raw[k60]
    assert spec_low[k8] > 0.95 * spec_raw[k8]


def test_lowfreq_timeslice_consistent_with_inline(client):
    """A timeslice sample must equal the same sample of the conditioned inline traces."""
    c, _, _ = client
    ts = _get(c, "/api/npy/vol/slice/timeslice/50?mode=lowfreq")  # (nIL, nXL)
    for il in range(SHAPE[0]):
        inl = _get(c, f"/api/npy/vol/slice/inline/{il}?mode=lowfreq")  # (nS, nXL)
        np.testing.assert_allclose(ts[il], inl[50], atol=1e-5)


def test_raw_volume_file_untouched(client):
    c, vol_dir, _ = client
    before = hashlib.sha256((vol_dir / "amplitude.npy").read_bytes()).hexdigest()
    for d, i in (("inline", 0), ("crossline", 0), ("timeslice", 0)):
        _get(c, f"/api/npy/vol/slice/{d}/{i}?mode=lowfreq")
    assert hashlib.sha256((vol_dir / "amplitude.npy").read_bytes()).hexdigest() == before


@pytest.mark.parametrize("path,code", [
    ("/api/npy/vol/slice/inline/0?mode=bogus", 400),
    ("/api/npy/vol/slice/inline/99?mode=lowfreq", 400),
    ("/api/npy/vol/slice/timeslice/999?mode=lowfreq", 400),
    ("/api/npy/vol/slice/crossline/-1?mode=lowfreq", 400),
    ("/api/npy/missing/slice/inline/0?mode=lowfreq", 404),
])
def test_errors(client, path, code):
    c, _, _ = client
    assert c.get(path).status_code == code


def test_timeslice_size_limit(client, monkeypatch):
    c, _, _ = client
    monkeypatch.setattr(lowfreq_service, "MAX_TIMESLICE_VOLUME_BYTES", 16)
    lowfreq_service._conditioned_volume.cache_clear()
    r = c.get("/api/npy/vol/slice/timeslice/0?mode=lowfreq")
    assert r.status_code == 400 and "limited" in r.json()["detail"]
