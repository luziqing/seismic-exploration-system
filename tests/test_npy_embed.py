"""POST /api/npy/{vol}/embed (bug B1): the server renders the slice itself for SAM — grey, no overlays,
uniform integer upscale — and reports the scale so the browser can place point prompts. SAM is stubbed."""
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import sam_service  # noqa: E402
import server  # noqa: E402

SHAPE = (6, 8, 128)  # nIL, nXL, nSamples


@pytest.fixture()
def client(tmp_path, monkeypatch):
    d = tmp_path / "npy" / "vol"
    d.mkdir(parents=True)
    rng = np.random.default_rng(1)
    np.save(d / "amplitude.npy", rng.standard_normal(SHAPE).astype(np.float32))
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server, "UPLOAD_DIR", uploads)
    seen = {}

    def fake_embed(path):
        with Image.open(path) as im:
            seen["image"] = np.asarray(im.convert("RGB")).copy()
            seen["size"] = im.size
        return {"embedding_id": "stub", "image_size": list(seen["size"])}

    monkeypatch.setattr(sam_service, "embed_image", fake_embed)
    return TestClient(server.app), seen


@pytest.mark.parametrize("direction,index,grid", [
    ("inline", 2, (128, 8)), ("crossline", 3, (128, 6)), ("timeslice", 40, (6, 8)),
])
def test_embed_renders_clean_grey_slice(client, direction, index, grid):
    c, seen = client
    r = c.post("/api/npy/vol/embed", json={"direction": direction, "index": index})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["embedding_id"] == "stub" and tuple(body["grid_shape"]) == grid
    sx, sy = body["scale"]
    assert sx == sy and sx == int(sx) and sx >= 1                     # uniform integer upscale
    w, h = body["image_size"]
    assert (h, w) == (grid[0] * sy, grid[1] * sx)                      # image covers the grid exactly
    img = seen["image"]
    assert (img[..., 0] == img[..., 1]).all() and (img[..., 1] == img[..., 2]).all()  # grey: no colour map, no markers


def test_embed_lowfreq_differs_from_raw(client):
    c, seen = client
    c.post("/api/npy/vol/embed", json={"direction": "inline", "index": 1, "mode": "raw"})
    raw = seen["image"].copy()
    c.post("/api/npy/vol/embed", json={"direction": "inline", "index": 1, "mode": "lowfreq"})
    assert seen["image"].shape == raw.shape and not np.array_equal(seen["image"], raw)


@pytest.mark.parametrize("payload,code", [
    ({"direction": "inline", "index": 99}, 400),
    ({"direction": "inline", "index": -1}, 400),
    ({"direction": "sideways", "index": 0}, 400),
    ({"direction": "inline", "index": 0, "mode": "bogus"}, 400),
])
def test_embed_errors(client, payload, code):
    c, _ = client
    assert c.post("/api/npy/vol/embed", json=payload).status_code == code


def test_embed_unknown_volume(client):
    c, _ = client
    assert c.post("/api/npy/missing/embed", json={"direction": "inline", "index": 0}).status_code == 404


def test_embed_missing_weights_is_503(client, monkeypatch):
    c, _ = client

    def no_weights(path):
        raise RuntimeError("weights file not found: data/weights/sam3.pt")

    monkeypatch.setattr(sam_service, "embed_image", no_weights)
    r = c.post("/api/npy/vol/embed", json={"direction": "inline", "index": 0})
    assert r.status_code == 503 and "weights" in r.json()["detail"]
