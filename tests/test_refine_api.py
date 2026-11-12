"""POST /api/npy/{vol}/refine and GET /api/refine/{run_id} with SAM stubbed (spec qc-refine-loop, Requirement 4)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from scipy.signal import hilbert

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import database  # noqa: E402
import sam_service  # noqa: E402
import server  # noqa: E402

N_IL, N_XL, N_S, DT = 6, 40, 128, 0.002
C0, W, IL = 10, 14, 3


def ricker(f, center):
    t = (np.arange(N_S) - center) * DT
    a = (np.pi * f * t) ** 2
    return (1.0 - 2.0 * a) * np.exp(-a)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    d = tmp_path / "npy" / "vol"
    (d / "truth").mkdir(parents=True)
    rng = np.random.default_rng(0)
    vol = rng.normal(0.0, 0.05, (N_IL, N_XL, N_S))
    vol[:, C0:C0 + W, :] += ricker(10.0, 80)[None, None, :]
    np.save(d / "amplitude.npy", vol.astype(np.float32))
    e = np.abs(hilbert(ricker(10.0, 80)))
    rows = np.flatnonzero(e >= e.max() * 0.5)
    truth = np.zeros((N_IL, N_XL, N_S), bool)
    truth[:, C0:C0 + W, rows[0]:rows[-1] + 1] = True
    np.save(d / "truth" / "deep_target_mask.npy", truth)
    (d / "meta.json").write_text(json.dumps({"dt_us": 2000}), encoding="utf-8")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "db" / "test.db")
    database.init_db()

    exact = truth[IL].T                                   # (N_S, N_XL)
    leaky = exact.copy()
    leaky[rows[-1] + 1:rows[-1] + 21, C0:C0 + W] = True    # round 1 leaks 20 samples into background
    state = {"embeds": 0, "calls": [], "size": None, "dropped": []}

    def fake_embed(path):
        state["embeds"] += 1
        with Image.open(path) as im:
            state["size"] = im.size
        return {"embedding_id": "e1", "image_size": list(im.size)}

    def fake_predict(eid, points, labels):
        state["calls"].append((points, labels))
        m = exact if 0 in labels else leaky                 # a negative correction fixes the leak
        w, h = state["size"]
        img = Image.fromarray(m.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)
        return {"mask": (np.asarray(img) > 127).astype(np.float32), "scores": [0.9]}

    monkeypatch.setattr(sam_service, "embed_image", fake_embed)
    monkeypatch.setattr(sam_service, "predict_mask_np", fake_predict)
    monkeypatch.setattr(sam_service, "drop_embedding", lambda eid: state["dropped"].append(eid))
    return TestClient(server.app), d, state, exact


def _body(**kw):
    b = {"direction": "inline", "index": IL, "points": [[(C0 + W / 2) / N_XL, 80.5 / N_S]], "labels": [1]}
    b.update(kw)
    return b


def test_refine_runs_corrects_stores_and_writes_mask(env):
    c, d, state, exact = env
    r = c.post("/api/npy/vol/refine", json=_body())
    assert r.status_code == 200, r.text
    run = r.json()
    assert state["embeds"] == 1 and state["dropped"] == ["e1"]              # one embed for all rounds
    assert len(run["rounds"]) >= 2 and run["rounds"][0]["correction"]["label"] == 0
    assert run["best_round"] >= 2 and run["rounds"][1]["score"] > run["rounds"][0]["score"]
    assert run["rounds"][1]["truth_reference"]["iou"] == pytest.approx(1.0)
    assert run["rounds"][0]["truth_reference"]["iou"] < 1.0
    assert np.array(run["rounds"][run["best_round"] - 1]["mask"], dtype=bool).shape == (N_S, N_XL)
    # user click maps to the clicked pixel of the rendered image
    (px, py), = state["calls"][0][0]
    w, h = state["size"]
    assert px == pytest.approx((C0 + W / 2) / N_XL * w, abs=w / N_XL) and py == pytest.approx(80.5 / N_S * h, abs=h / N_S)
    # best mask written to the volume mask with provenance
    vm = np.load(d / "masks" / "sam_mask.npy")
    np.testing.assert_array_equal(vm[IL].T, exact)
    meta = json.loads((d / "masks" / "sam_mask.json").read_text(encoding="utf-8"))
    assert meta["slices"][f"inline:{IL}"]["points"][0]["source"].startswith(f"refine_run_{run['run_id']}_round_")


def test_get_replays_the_same_run(env):
    c, _, _, _ = env
    run = c.post("/api/npy/vol/refine", json=_body()).json()
    again = c.get(f"/api/refine/{run['run_id']}")
    assert again.status_code == 200 and again.json() == run


def test_lowfreq_view_segments_but_qc_uses_raw(env, monkeypatch):
    c, _, state, _ = env
    r = c.post("/api/npy/vol/refine", json=_body(mode="lowfreq"))
    assert r.status_code == 200 and r.json()["mode"] == "lowfreq"
    raw_r = c.post("/api/npy/vol/refine", json=_body(mode="raw")).json()
    # QC reference is computed on the raw slice in both cases, so round-1 metrics match
    assert r.json()["rounds"][0]["metrics"]["reference_envelope"] == raw_r["rounds"][0]["metrics"]["reference_envelope"]


def test_write_mask_false_leaves_volume_mask_alone(env):
    c, d, _, _ = env
    assert c.post("/api/npy/vol/refine", json=_body(write_mask=False)).status_code == 200
    assert not (d / "masks" / "sam_mask.npy").exists()


@pytest.mark.parametrize("patch,code", [
    ({"points": []}, 400), ({"labels": [1, 0]}, 400), ({"points": [[1.5, 0.2]]}, 400),
    ({"labels": [2]}, 400), ({"labels": [0]}, 400), ({"index": 99}, 400), ({"index": -1}, 400),
    ({"direction": "sideways"}, 400), ({"mode": "bogus"}, 400), ({"target_type": "horizon"}, 400),
    ({"max_rounds": 9}, 400),
])
def test_validation(env, patch, code):
    c, _, _, _ = env
    assert c.post("/api/npy/vol/refine", json=_body(**patch)).status_code == code


def test_unknown_volume_and_run(env):
    c, _, _, _ = env
    assert c.post("/api/npy/missing/refine", json=_body()).status_code == 404
    assert c.get("/api/refine/999999").status_code == 404


def test_missing_weights_is_503(env, monkeypatch):
    c, _, _, _ = env

    def no_weights(path):
        raise RuntimeError("weights file not found: data/weights/sam3.pt")

    monkeypatch.setattr(sam_service, "embed_image", no_weights)
    r = c.post("/api/npy/vol/refine", json=_body())
    assert r.status_code == 503 and "weights" in r.json()["detail"]


def test_rle_round_trip():
    rng = np.random.default_rng(3)
    for shape in ((1, 1), (7, 5), (128, 40)):
        for p in (0.0, 0.3, 1.0):
            m = rng.random(shape) < p
            np.testing.assert_array_equal(database.rle_to_mask(database.mask_to_rle(m), shape), m)
