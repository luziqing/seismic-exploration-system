#!/usr/bin/env python
"""SAM3 local GPU inference + 3D volume mask back-projection smoke test.

Flow: multiple inlines from synthetic volume -> /api/embed -> /api/predict -> /api/npy/<vol>/mask (back-project and write voxels)
      -> read back volume mask, compute IoU against truth/deep_target_mask.npy on written slices, and print il/xl/time bbox.
Requires running server first: python src/server.py
"""
import io
import os
import sys
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image

BASE = os.environ.get("SAM3_URL", "http://127.0.0.1:9339")  # avoid localhost: Windows tries IPv6 first and adds ~2 s delay
ROOT = Path(__file__).resolve().parent.parent
VOLNAME = os.environ.get("SAM3_TEST_VOLUME", "synthetic_deep_v1")
VOL = ROOT / "data" / "npy" / VOLNAME
MASK_NAME = "sam_e2e_test"
SCALE = 4  # 256x48 is too small; upscale before sending to SAM
INLINES = [12, 16, 20, 24, 28]


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def main():
    amp = np.load(VOL / "amplitude.npy", mmap_mode="r")
    truth = np.load(VOL / "truth" / "deep_target_mask.npy", mmap_mode="r")
    s = requests.get(f"{BASE}/api/status", timeout=10).json()
    print(f"GPU: {s['gpu_name']}, model_loaded(before)={s['model_loaded']}")

    written = []
    for n, il in enumerate(INLINES):
        sl = np.asarray(amp[il]).T            # (samples, xl)
        gt = np.asarray(truth[il]).T.astype(bool)
        if not gt.any():
            continue
        lo, hi = np.percentile(sl, [2, 98])
        g = (np.clip((sl - lo) / (hi - lo + 1e-9), 0, 1) * 255).astype(np.uint8)
        img = Image.fromarray(g).resize((g.shape[1] * SCALE * 4, g.shape[0] * SCALE), Image.BILINEAR).convert("RGB")
        gt_big = np.array(Image.fromarray(gt.astype(np.uint8) * 255).resize(img.size, Image.NEAREST)) > 127
        buf = io.BytesIO(); img.save(buf, "PNG")

        t = time.time()
        r = requests.post(f"{BASE}/api/embed", files={"file": ("slice.png", buf.getvalue(), "image/png")}, timeout=600)
        assert r.status_code == 200, f"embed HTTP {r.status_code}: {r.text[:300]}"
        emb = r.json()
        t_emb = time.time() - t

        ys, xs = np.nonzero(gt_big)
        k = len(ys) // 2
        py, px = int(np.median(ys)), int(np.median(xs))
        if not gt_big[py, px]:
            py, px = int(ys[k]), int(xs[k])
        t = time.time()
        r = requests.post(f"{BASE}/api/predict", json={"embedding_id": emb["embedding_id"],
                          "points": [[px, py]], "labels": [1]}, timeout=600)
        assert r.status_code == 200, f"predict HTTP {r.status_code}: {r.text[:300]}"
        out = r.json()
        t_pred = time.time() - t

        r = requests.post(f"{BASE}/api/npy/{VOLNAME}/mask", json={
            "direction": "inline", "index": il, "mask": out["mask"], "mask_name": MASK_NAME,
            "mode": "replace", "score": out["scores"][0], "points": [{"x": px, "y": py, "label": 1}]}, timeout=60)
        assert r.status_code == 200, f"mask HTTP {r.status_code}: {r.text[:300]}"
        w = r.json()
        written.append(il)
        print(f"inline {il}: embed {t_emb:.1f}s predict {t_pred:.1f}s score={out['scores'][0]:.3f} "
              f"src_mask={w['src_mask_shape']} -> grid={w['grid_shape']} voxels={w['slice_voxels']}")

    assert written, "no testable inlines"
    info = requests.get(f"{BASE}/api/npy/{VOLNAME}/mask/{MASK_NAME}/info", timeout=30).json()
    print(f"volume mask: voxels={info['voxel_count']} slices={len(info['slices'])}")
    print(f"  bbox index : {info['bbox_index']}")
    print(f"  bbox coords: {info['bbox_coords']}")
    print(f"  centroid   : {info['centroid_coords']}")

    vol_mask = np.load(VOL / "masks" / f"{MASK_NAME}.npy", mmap_mode="r")
    assert vol_mask.shape == amp.shape and vol_mask.dtype == np.bool_
    pred3d = np.zeros(amp.shape, dtype=bool); gt3d = np.zeros(amp.shape, dtype=bool)
    pred3d[written] = vol_mask[written]; gt3d[written] = truth[written]
    per = [iou(np.asarray(vol_mask[i]), np.asarray(truth[i])) for i in written]
    print(f"per-slice IoU: {[round(x, 3) for x in per]}")
    print(f"3D IoU (over {len(written)} inferred inlines): {iou(pred3d, gt3d):.3f}")

    # read back a single inline mask slice via API and verify it matches disk volume
    r = requests.get(f"{BASE}/api/npy/{VOLNAME}/mask/{MASK_NAME}/slice/inline/{written[0]}", timeout=30)
    back = np.frombuffer(r.content, dtype=np.float32).reshape(int(r.headers["X-Rows"]), int(r.headers["X-Cols"]))
    assert np.array_equal(back > 0.5, np.asarray(vol_mask[written[0]]).T)
    assert info["voxel_count"] > 0
    print("OK: SAM inference -> 3D volume mask back-projection pipeline OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
