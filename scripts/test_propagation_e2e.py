#!/usr/bin/env python
"""跨切片传播端到端 (真实 SAM3/GPU): 在 inline 种子切片点 1 个点 -> 传播 -> 对比三维真值。
需先启动服务器: python src/server.py
"""
import io
import os
import sys
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image

BASE = os.environ.get("SAM3_URL", "http://127.0.0.1:9339")  # 不用 localhost: Windows 上先试 IPv6 会多等约 2 s
ROOT = Path(__file__).resolve().parent.parent
VOLNAME = os.environ.get("SAM3_TEST_VOLUME", "synthetic_deep_v1")
VOL = ROOT / "data" / "npy" / VOLNAME
MASK = "sam_prop_test"
SEED_IL = 20


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def seed_by_click():
    amp = np.load(VOL / "amplitude.npy", mmap_mode="r")
    truth = np.load(VOL / "truth" / "deep_target_mask.npy", mmap_mode="r")
    sl = np.asarray(amp[SEED_IL]).T
    gt = np.asarray(truth[SEED_IL]).T.astype(bool)
    lo, hi = np.percentile(sl, [2, 98])
    g = (np.clip((sl - lo) / (hi - lo + 1e-9), 0, 1) * 255).astype(np.uint8)
    img = Image.fromarray(g).resize((g.shape[1] * 16, g.shape[0] * 4), Image.BILINEAR).convert("RGB")
    gt_big = np.array(Image.fromarray(gt.astype(np.uint8) * 255).resize(img.size, Image.NEAREST)) > 127
    ys, xs = np.nonzero(gt_big)
    py, px = int(np.median(ys)), int(np.median(xs))
    if not gt_big[py, px]:
        py, px = int(ys[len(ys) // 2]), int(xs[len(xs) // 2])
    buf = io.BytesIO(); img.save(buf, "PNG")
    emb = requests.post(f"{BASE}/api/embed", files={"file": ("s.png", buf.getvalue(), "image/png")}, timeout=600).json()
    out = requests.post(f"{BASE}/api/predict", json={"embedding_id": emb["embedding_id"],
                        "points": [[px, py]], "labels": [1]}, timeout=600).json()
    w = requests.post(f"{BASE}/api/npy/{VOLNAME}/mask", json={
        "direction": "inline", "index": SEED_IL, "mask": out["mask"], "mask_name": MASK,
        "mode": "replace", "score": out["scores"][0]}, timeout=60)
    assert w.status_code == 200, w.text
    print(f"种子 inline {SEED_IL}: score={out['scores'][0]:.3f} voxels={w.json()['slice_voxels']}")


def report(res, truth):
    print(f"  传播盒: {res['box']}  写入: {res['written_indices']}  体素: {res['total_voxels']}")
    for s in res["slices"]:
        print(f"    inline {s['index']:>2}  voxels={s['voxels']:>5} iou_prev={s['iou_prev']:.2f} "
              f"score={s['score']:.2f} written={s['written']} stop={s['stopped']}")
    vm = np.load(VOL / "masks" / f"{MASK}.npy", mmap_mode="r")
    idx = sorted(set(res["written_indices"]) | {SEED_IL})
    per = [round(iou(np.asarray(vm[i]), np.asarray(truth[i])), 3) for i in idx]
    p3 = np.zeros(vm.shape, bool); g3 = np.zeros(vm.shape, bool)
    p3[idx] = vm[idx]; g3[idx] = truth[idx]
    print(f"  逐切片 IoU {dict(zip(idx, per))}  三维 IoU={iou(p3, g3):.3f}")
    return vm


def main():
    truth = np.load(VOL / "truth" / "deep_target_mask.npy", mmap_mode="r")
    seed_by_click()

    print("\n[默认范围] max_il=5 max_xl=5 max_vertical=30")
    t = time.time()
    r = requests.post(f"{BASE}/api/npy/{VOLNAME}/propagate", json={
        "direction": "inline", "index": SEED_IL, "mask_name": MASK}, timeout=900)
    assert r.status_code == 200, r.text
    res = r.json(); print(f"  耗时 {time.time() - t:.1f}s")
    vm = report(res, truth)
    ii = np.nonzero(np.asarray(vm).any(axis=(1, 2)))[0]
    assert ii.min() >= SEED_IL - 5 and ii.max() <= SEED_IL + 5, f"超出 ±5: {ii.min()}..{ii.max()}"
    assert len(res["written_indices"]) > 0, "未传播出任何切片"
    xx = np.nonzero(np.asarray(vm).any(axis=(0, 2)))[0]
    ss = np.nonzero(np.asarray(vm).any(axis=(0, 1)))[0]
    b = res["box"]
    assert xx.min() >= b["xl"][0] and xx.max() <= b["xl"][1]
    assert ss.min() >= b["s"][0] and ss.max() <= b["s"][1]

    print("\n[收紧范围] max_il=2 max_xl=1 max_vertical=5 (在同一 mask 上重新传播)")
    seed_by_click()
    r = requests.post(f"{BASE}/api/npy/{VOLNAME}/propagate", json={
        "direction": "inline", "index": SEED_IL, "mask_name": MASK,
        "max_il": 2, "max_xl": 1, "max_vertical": 5}, timeout=900)
    assert r.status_code == 200, r.text
    res2 = r.json(); report(res2, truth)
    assert set(res2["written_indices"]) <= {SEED_IL + d for d in (-2, -1, 1, 2)}

    print("\n[错误处理]")
    assert requests.post(f"{BASE}/api/npy/{VOLNAME}/propagate", json={
        "direction": "inline", "index": 0, "mask_name": MASK}, timeout=60).status_code == 400  # 空种子
    assert requests.post(f"{BASE}/api/npy/{VOLNAME}/propagate", json={
        "direction": "inline", "index": SEED_IL, "mask_name": MASK, "max_il": -1}, timeout=60).status_code == 400
    print("OK: 传播链路正常, 范围限制生效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
