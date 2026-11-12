#!/usr/bin/env python
"""
端到端测试：模拟前端完整流程（基于合成 NPY 卷，无需专有数据 / GPU）

流程：
 1. 页面与静态资源可访问
 2. /api/status 懒加载（model_loaded=False）
 3. 列出 NPY 卷 -> 读取 meta
 4. 三个方向切片读取（inline / crossline / timeslice），校验二进制 float32 与 shape 头
 5. 导航：inline 0 -> 1 -> 2，shape 一致、内容不同
 6. 越界 / 负数索引 / 不存在的卷 的错误码
 7. 拾取会话：创建 -> 添加点 -> 读取 -> 撤销 -> 清空
 8. 校验：用真值 mask 对比自身，Dice/IoU 应为 1
用法：先启动 python src/server.py，再运行本脚本（或 pytest）。
"""
import os
import sys

import numpy as np
import requests

BASE_URL = os.environ.get("SAM3_URL", "http://localhost:9339")
VOLUME = os.environ.get("SAM3_TEST_VOLUME", "synthetic_deep_v1")
T = 15


def get(path, **kw):
    return requests.get(f"{BASE_URL}{path}", timeout=T, **kw)


def read_slice(direction, index):
    r = get(f"/api/npy/{VOLUME}/slice/{direction}/{index}")
    assert r.status_code == 200, f"{direction}/{index} -> HTTP {r.status_code}: {r.text[:200]}"
    rows, cols = int(r.headers["X-Rows"]), int(r.headers["X-Cols"])
    arr = np.frombuffer(r.content, dtype=np.float32)
    assert arr.size == rows * cols, f"字节数与 shape 不符: {arr.size} != {rows}x{cols}"
    assert np.isfinite(arr).all(), "切片含 NaN/Inf"
    return arr.reshape(rows, cols)


def test_frontend_assets():
    r = get("/")
    assert r.status_code == 200 and "html" in r.headers["content-type"]
    for js in ("app.js", "canvas.js", "sam-client.js", "storage.js"):
        assert get(f"/static/js/{js}").status_code == 200, js
    assert get("/static/css/app.css").status_code == 200


def test_server_status_lazy():
    s = get("/api/status").json()
    print(f"  status: {s}")
    assert s["model_loaded"] is False, "懒加载：启动时模型不应已加载"


def test_volume_listing_and_meta():
    vols = get("/api/npy/list").json()["volumes"]
    assert VOLUME in [v["name"] for v in vols]
    meta = get(f"/api/npy/{VOLUME}/meta").json()
    print(f"  meta keys: {sorted(meta)[:8]}")
    assert meta


def test_three_directions():
    vol = next(v for v in get("/api/npy/list").json()["volumes"] if v["name"] == VOLUME)
    n_il, n_xl, n_t = vol["n_inlines"], vol["n_crosslines"], vol["n_samples"]
    il = read_slice("inline", n_il // 2)
    xl = read_slice("crossline", n_xl // 2)
    ts = read_slice("timeslice", n_t // 2)
    print(f"  inline{il.shape} crossline{xl.shape} timeslice{ts.shape}")
    assert il.ndim == xl.ndim == ts.ndim == 2
    assert il.std() > 0, "inline 切片为常数"


def test_navigation():
    a, b, c = (read_slice("inline", i) for i in (0, 1, 2))
    assert a.shape == b.shape == c.shape
    assert not np.array_equal(a, b) and not np.array_equal(b, c), "相邻切片不应完全相同"
    # 同一切片重复读取应确定
    assert np.array_equal(a, read_slice("inline", 0))


def test_error_codes():
    n_il = next(v for v in get("/api/npy/list").json()["volumes"] if v["name"] == VOLUME)["n_inlines"]
    assert get(f"/api/npy/{VOLUME}/slice/inline/{n_il + 1000}").status_code in (400, 500)
    assert get(f"/api/npy/{VOLUME}/slice/inline/-1").status_code in (400, 404, 422)
    assert get("/api/npy/no_such_volume/slice/inline/0").status_code == 404
    assert get("/api/npy/no_such_volume/meta").status_code == 404


def test_pick_session_flow():
    sid = requests.post(f"{BASE_URL}/api/db/session", params={"slice_id": 999999}, timeout=T).json()["session_id"]
    base = f"{BASE_URL}/api/db/session/{sid}/points"
    requests.delete(base, timeout=T)  # 保证干净起点
    pts = [
        {"il": 1, "xl": 5, "depth": 100, "px_x": 10.0, "px_y": 20.0, "label": 1},
        {"il": 1, "xl": 6, "depth": 110, "px_x": 12.0, "px_y": 22.0, "label": 0},
    ]
    assert requests.post(base, json={"session_id": sid, "points": pts}, timeout=T).json()["added"] == 2
    assert len(requests.get(base, timeout=T).json()["points"]) == 2
    assert requests.delete(f"{base}/last", timeout=T).json()["deleted"] is True
    assert len(requests.get(base, timeout=T).json()["points"]) == 1
    assert requests.delete(base, timeout=T).json()["cleared"] is True
    assert requests.get(base, timeout=T).json()["points"] == []


def test_validation_flow():
    sid = requests.post(f"{BASE_URL}/api/db/session", params={"slice_id": 999999}, timeout=T).json()["session_id"]
    mask = [[0, 1, 1], [0, 1, 0], [0, 0, 0]]
    r = requests.post(
        f"{BASE_URL}/api/db/session/{sid}/validation",
        json={"predicted_mask": mask, "ground_truth_mask": mask},
        timeout=T,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    print(f"  validation keys: {sorted(out)}")
    print(f"  metrics: {out['metrics']}")
    for k in ("dice", "iou"):
        assert k in out["metrics"], f"metrics 缺少 {k}"
        assert abs(out["metrics"][k] - 1.0) < 1e-6, f"{k}={out['metrics'][k]}"
    # 形状不一致应 400
    bad = requests.post(
        f"{BASE_URL}/api/db/session/{sid}/validation",
        json={"predicted_mask": mask, "ground_truth_mask": [[1, 0]]},
        timeout=T,
    )
    assert bad.status_code == 400


TESTS = [
    test_frontend_assets,
    test_server_status_lazy,
    test_volume_listing_and_meta,
    test_three_directions,
    test_navigation,
    test_error_codes,
    test_pick_session_flow,
    test_validation_flow,
]


def main():
    failed = 0
    for t in TESTS:
        print(f"[{t.__name__}]")
        try:
            t()
            print("  ✓ pass")
        except requests.exceptions.ConnectionError:
            print("✗ 服务器未运行，请先启动: python src/server.py")
            return 2
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ FAIL: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
