#!/usr/bin/env python
"""Cross-slice propagation e2e (real SAM3/GPU): click 1 point on inline seed slice -> propagate -> compare with 3D ground truth.
Requires running server first: python src/server.py
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
import requests

BASE = os.environ.get("SAM3_URL", "http://127.0.0.1:9339")  # avoid localhost: Windows tries IPv6 first and adds ~2 s delay
ROOT = Path(__file__).resolve().parent.parent
VOLNAME = os.environ.get("SAM3_TEST_VOLUME", "synthetic_deep_v1")
VOL = ROOT / "data" / "npy" / VOLNAME
MASK = "sam_prop_test"
SEED_IL = 20


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def seed_by_click():
    """Seed exactly as the browser does since B1: server-rendered embed + click inside the target."""
    truth = np.load(VOL / "truth" / "deep_target_mask.npy", mmap_mode="r")
    gt = np.asarray(truth[SEED_IL]).T.astype(bool)
    rows, cols = np.nonzero(gt)
    k = len(rows) // 2
    r0, c0 = int(np.median(rows)), int(np.median(cols))
    if not gt[r0, c0]:
        r0, c0 = int(rows[k]), int(cols[k])
    emb = requests.post(f"{BASE}/api/npy/{VOLNAME}/embed",
                        json={"direction": "inline", "index": SEED_IL}, timeout=600).json()
    sx, sy = emb["scale"]
    out = requests.post(f"{BASE}/api/predict", json={"embedding_id": emb["embedding_id"],
                        "points": [[(c0 + 0.5) * sx, (r0 + 0.5) * sy]], "labels": [1]}, timeout=600).json()
    w = requests.post(f"{BASE}/api/npy/{VOLNAME}/mask", json={
        "direction": "inline", "index": SEED_IL, "mask": out["mask"], "mask_name": MASK,
        "mode": "replace", "score": out["scores"][0]}, timeout=60)
    assert w.status_code == 200, w.text
    assert w.json()["slice_voxels"] > 0, "empty seed from the UI embed path (regression of bug B1)"
    print(f"seed inline {SEED_IL}: score={out['scores'][0]:.3f} voxels={w.json()['slice_voxels']}")


def report(res, truth):
    print(f"  propagation box: {res['box']}  written: {res['written_indices']}  voxels: {res['total_voxels']}")
    for s in res["slices"]:
        print(f"    inline {s['index']:>2}  voxels={s['voxels']:>5} iou_prev={s['iou_prev']:.2f} "
              f"score={s['score']:.2f} written={s['written']} stop={s['stopped']}")
    vm = np.load(VOL / "masks" / f"{MASK}.npy", mmap_mode="r")
    idx = sorted(set(res["written_indices"]) | {SEED_IL})
    per = [round(iou(np.asarray(vm[i]), np.asarray(truth[i])), 3) for i in idx]
    p3 = np.zeros(vm.shape, bool); g3 = np.zeros(vm.shape, bool)
    p3[idx] = vm[idx]; g3[idx] = truth[idx]
    print(f"  per-slice IoU {dict(zip(idx, per))}  3D IoU={iou(p3, g3):.3f}")
    return vm


def main():
    truth = np.load(VOL / "truth" / "deep_target_mask.npy", mmap_mode="r")
    seed_by_click()

    print("\n[default range] max_il=5 max_xl=5 max_vertical=30")
    t = time.time()
    r = requests.post(f"{BASE}/api/npy/{VOLNAME}/propagate", json={
        "direction": "inline", "index": SEED_IL, "mask_name": MASK}, timeout=900)
    assert r.status_code == 200, r.text
    res = r.json(); print(f"  elapsed {time.time() - t:.1f}s")
    vm = report(res, truth)
    ii = np.nonzero(np.asarray(vm).any(axis=(1, 2)))[0]
    assert ii.min() >= SEED_IL - 5 and ii.max() <= SEED_IL + 5, f"exceeded ±5: {ii.min()}..{ii.max()}"
    assert len(res["written_indices"]) > 0, "no slices were propagated"
    xx = np.nonzero(np.asarray(vm).any(axis=(0, 2)))[0]
    ss = np.nonzero(np.asarray(vm).any(axis=(0, 1)))[0]
    b = res["box"]
    assert xx.min() >= b["xl"][0] and xx.max() <= b["xl"][1]
    assert ss.min() >= b["s"][0] and ss.max() <= b["s"][1]

    print("\n[tighter range] max_il=2 max_xl=1 max_vertical=5 (re-propagate on the same mask)")
    seed_by_click()
    r = requests.post(f"{BASE}/api/npy/{VOLNAME}/propagate", json={
        "direction": "inline", "index": SEED_IL, "mask_name": MASK,
        "max_il": 2, "max_xl": 1, "max_vertical": 5}, timeout=900)
    assert r.status_code == 200, r.text
    res2 = r.json(); report(res2, truth)
    assert set(res2["written_indices"]) <= {SEED_IL + d for d in (-2, -1, 1, 2)}

    print("\n[error handling]")
    assert requests.post(f"{BASE}/api/npy/{VOLNAME}/propagate", json={
        "direction": "inline", "index": 0, "mask_name": MASK}, timeout=60).status_code == 400  # empty seed
    assert requests.post(f"{BASE}/api/npy/{VOLNAME}/propagate", json={
        "direction": "inline", "index": SEED_IL, "mask_name": MASK, "max_il": -1}, timeout=60).status_code == 400
    print("OK: propagation pipeline normal, range limit active")
    return 0


if __name__ == "__main__":
    sys.exit(main())
