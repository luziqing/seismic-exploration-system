"""No-weights mode (scope S7): browsing, low-freq and masks keep working; every SAM endpoint answers 503
with a message that says what is missing and where to get it. Uses a temporary volume, no GPU."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import database  # noqa: E402
import sam_service  # noqa: E402
import server  # noqa: E402

N_IL, N_XL, N_S = 4, 16, 64


@pytest.fixture()
def client(tmp_path, monkeypatch):
    d = tmp_path / "npy" / "vol"
    d.mkdir(parents=True)
    rng = np.random.default_rng(1)
    np.save(d / "amplitude.npy", rng.normal(0, 1, (N_IL, N_XL, N_S)).astype(np.float32))
    (d / "meta.json").write_text(json.dumps({"dt_us": 2000}), encoding="utf-8")
    (tmp_path / "uploads").mkdir()
    missing = tmp_path / "weights" / "sam3.pt"
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(server, "WEIGHTS_PATH", missing)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr(sam_service, "_model", None)          # as on a machine without weights
    monkeypatch.setattr(sam_service, "_model_path", str(missing))
    return TestClient(server.app)


def _assert_weights_503(r):
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert "weights not found" in detail and "huggingface.co/facebook/sam3" in detail and "data/weights/sam3.pt" in detail


def test_status_reports_missing_weights_and_where_to_get_them(client):
    s = client.get("/api/status").json()
    assert s["weights_exists"] is False
    assert s["weights_path"] == "data/weights/sam3.pt" and "facebook/sam3" in s["weights_source"]
    assert s["sam_device"] in ("cuda", "cpu")


def test_browse_and_lowfreq_work_without_weights(client):
    for mode in ("raw", "lowfreq"):
        r = client.get(f"/api/npy/vol/slice/inline/1?mode={mode}")
        assert r.status_code == 200 and r.headers["X-Rows"] == str(N_S)


def test_embed_and_refine_return_503(client):
    _assert_weights_503(client.post("/api/npy/vol/embed", json={"direction": "inline", "index": 1, "mode": "raw"}))
    _assert_weights_503(client.post("/api/npy/vol/refine", json={
        "direction": "inline", "index": 1, "points": [[0.5, 0.5]], "labels": [1], "write_mask": False}))


def test_propagate_returns_503_not_500(client):
    seed = np.zeros((N_S, N_XL), np.float32)
    seed[20:30, 4:10] = 1
    r = client.post("/api/npy/vol/mask", json={"direction": "inline", "index": 1, "mask": seed.tolist(),
                                               "mask_name": "sam_mask", "mode": "replace"})
    assert r.status_code == 200, r.text
    assert client.get("/api/npy/vol/mask/sam_mask/footprint").status_code == 200   # survey map still works
    _assert_weights_503(client.post("/api/npy/vol/propagate", json={"direction": "inline", "index": 1, "max_il": 1}))
