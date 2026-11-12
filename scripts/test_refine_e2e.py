#!/usr/bin/env python
"""
GPU end-to-end check of the refine loop through the live server (scope E6, qc-refine-loop Wave 5).

POST /api/npy/{vol}/refine with real SAM3 on the clean volume (one click at the truth interior point,
the measure_refine.py click rule), then GET /api/refine/{run_id} and check the replay equals the
response. Also checks that the noisy volume stops with qc_unreliable. Writes no volume mask.

Start the server first: python src/server.py
"""
import os
import sys
from pathlib import Path

import numpy as np
import requests

BASE = os.environ.get("SAM3_URL", "http://127.0.0.1:9339")   # not localhost: Windows tries IPv6 first (~2 s)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from propagation_service import mask_to_points  # noqa: E402

CASES = (("synthetic_deep_v1_clean", 23, None), ("synthetic_deep_v1", 20, "qc_unreliable"))


def click(vol: str, il: int) -> list[float]:
    truth = np.load(ROOT / "data" / "npy" / vol / "truth" / "deep_target_mask.npy", mmap_mode="r")
    t = np.asarray(truth[il]).T.astype(bool)
    (r, c), = mask_to_points(t, 1)
    rows, cols = t.shape
    return [(c + 0.5) / cols, (r + 0.5) / rows]


def main() -> int:
    try:
        s = requests.get(f"{BASE}/api/status", timeout=10).json()
    except requests.ConnectionError:
        print(f"No server at {BASE}. Start it first: python src/server.py", file=sys.stderr)
        return 2
    print(f"server: gpu={s.get('gpu_name')} weights={s.get('weights_exists')}")
    failures = 0
    for vol, il, expect_stop in CASES:
        body = {"direction": "inline", "index": il, "mode": "raw", "target_type": "deep_target",
                "points": [click(vol, il)], "labels": [1], "write_mask": False}
        r = requests.post(f"{BASE}/api/npy/{vol}/refine", json=body, timeout=300)
        if r.status_code != 200:
            print(f"FAIL {vol} il {il}: HTTP {r.status_code} {r.text[:200]}")
            failures += 1
            continue
        run = r.json()
        rounds = " ".join(f"r{x['round']} {x['score']:.3f}/{(x['truth_reference'] or {}).get('iou', float('nan')):.3f}"
                          for x in run["rounds"])
        print(f"{vol} il {il}: run {run['run_id']}  {rounds}  stop={run['stop_reason']} best=r{run['best_round']}")
        ok = bool(run["rounds"]) and any(any(row) for row in run["rounds"][run["best_round"] - 1]["mask"])
        if expect_stop and run["stop_reason"] != expect_stop:
            print(f"  FAIL expected stop {expect_stop}")
            ok = False
        g = requests.get(f"{BASE}/api/refine/{run['run_id']}", timeout=30)
        rep = g.json() if g.status_code == 200 else {}
        same = (rep.get("best_round") == run["best_round"] and rep.get("stop_reason") == run["stop_reason"]
                and [x["mask"] for x in rep.get("rounds", [])] == [x["mask"] for x in run["rounds"]]
                and [round(x["score"], 6) for x in rep.get("rounds", [])] == [round(x["score"], 6) for x in run["rounds"]])
        print(f"  replay via GET: {'identical' if same else 'DIFFERS'}")
        if not (ok and same):
            failures += 1
    print("PASS" if failures == 0 else f"FAIL ({failures})")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
