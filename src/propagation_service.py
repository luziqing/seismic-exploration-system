"""
跨切片传播 — 用相邻切片的 mask 自动生成下一张切片的点提示, 逐张推理并写入体 mask

传播方向 = 种子切片所在的方向:
  inline    -> 沿 IL 轴前后逐张传播
  crossline -> 沿 XL 轴前后逐张传播
  timeslice -> 沿采样(纵向)轴前后逐张传播

范围限制 (传播盒, 体素索引空间), 由三个半宽参数控制:
  max_il / max_xl / max_vertical
  * 传播轴上:   种子索引 ± 对应半宽 (步数上限, 默认 IL/XL 为 5)
  * 其他两轴:   种子 mask 的包围盒向外扩 对应半宽 (限制 mask 的横向/纵向外扩)
每张切片的结果会被裁剪到传播盒内, 再写入体 mask。

停止条件: mask 为空 / 与上一张的 IoU 低于 min_iou (防止漂移) / 到达传播盒边界。
"""

import logging
import os
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

import sam_service
import volume_mask_service as vms

logger = logging.getLogger("sam3-server")

IMG_LONG_SIDE = 1024   # 送入 SAM 的图像长边 (像素)
MAX_POINTS = 3         # 每张切片最多自动生成的正向点数


# ── 切片读取 / 渲染 ───────────────────────────────────────────

def read_amp_slice(npy_dir: Path, direction: str, index: int) -> np.ndarray:
    vol = np.load(str(npy_dir / "amplitude.npy"), mmap_mode="r")
    return np.array(vms._slice_view(vol, direction, index), dtype=np.float32)


def render_slice_image(slice2d: np.ndarray, long_side: int = IMG_LONG_SIDE):
    """灰度渲染 (2-98 百分位拉伸) 并等比放大到长边 long_side。返回 (PIL RGB, sy, sx)"""
    lo, hi = np.percentile(slice2d, [2, 98])
    g = (np.clip((slice2d - lo) / (hi - lo + 1e-9), 0, 1) * 255).astype(np.uint8)
    rows, cols = g.shape
    f = max(1, int(round(long_side / max(rows, cols))))
    img = Image.fromarray(g).resize((cols * f, rows * f), Image.BILINEAR).convert("RGB")
    return img, float(f), float(f)


# ── 传播盒 ────────────────────────────────────────────────────

def _bbox2d(m: np.ndarray):
    r = np.flatnonzero(m.any(axis=1))
    c = np.flatnonzero(m.any(axis=0))
    return int(r[0]), int(r[-1]), int(c[0]), int(c[-1])


def build_box(direction: str, index: int, seed: np.ndarray, vol_shape, max_il: int, max_xl: int,
              max_vertical: int) -> dict:
    """返回体素索引空间的闭区间盒 {'il':(lo,hi),'xl':(lo,hi),'s':(lo,hi)}"""
    n_il, n_xl, n_s = vol_shape
    r0, r1, c0, c1 = _bbox2d(seed)

    def clip(lo, hi, n):
        return (max(0, int(lo)), min(n - 1, int(hi)))

    if direction == "inline":      # seed 行=sample 列=xl
        return {"il": clip(index - max_il, index + max_il, n_il),
                "xl": clip(c0 - max_xl, c1 + max_xl, n_xl),
                "s": clip(r0 - max_vertical, r1 + max_vertical, n_s)}
    if direction == "crossline":   # seed 行=sample 列=il
        return {"il": clip(c0 - max_il, c1 + max_il, n_il),
                "xl": clip(index - max_xl, index + max_xl, n_xl),
                "s": clip(r0 - max_vertical, r1 + max_vertical, n_s)}
    # timeslice: seed 行=il 列=xl
    return {"il": clip(r0 - max_il, r1 + max_il, n_il),
            "xl": clip(c0 - max_xl, c1 + max_xl, n_xl),
            "s": clip(index - max_vertical, index + max_vertical, n_s)}


def axis_range(direction: str, box: dict) -> tuple[int, int]:
    return box[{"inline": "il", "crossline": "xl", "timeslice": "s"}[direction]]


def box_mask_2d(direction: str, grid_shape, box: dict) -> np.ndarray:
    """传播盒在某切片(切片图像朝向)上的 2D 允许区域"""
    rows, cols = grid_shape
    m = np.zeros((rows, cols), dtype=bool)
    if direction == "inline":
        m[box["s"][0]:box["s"][1] + 1, box["xl"][0]:box["xl"][1] + 1] = True
    elif direction == "crossline":
        m[box["s"][0]:box["s"][1] + 1, box["il"][0]:box["il"][1] + 1] = True
    else:
        m[box["il"][0]:box["il"][1] + 1, box["xl"][0]:box["xl"][1] + 1] = True
    return m


# ── 点提示生成 ────────────────────────────────────────────────

def mask_to_points(mask: np.ndarray, max_points: int = MAX_POINTS) -> list[tuple[int, int]]:
    """
    从 mask 生成正向点 (row, col): 取最大连通域, 第一个点为距离变换最大处(最内部),
    其余点在距离变换 >= 一半峰值的像素中贪心取离已选点最远者, 保证点都落在 mask 内部。
    """
    lab, n = ndimage.label(mask)
    if n == 0:
        return []
    sizes = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
    comp = lab == (int(np.argmax(sizes)) + 1)
    dt = ndimage.distance_transform_edt(comp)
    peak = dt.max()
    first = np.unravel_index(int(np.argmax(dt)), dt.shape)
    pts = [(int(first[0]), int(first[1]))]
    cand = np.argwhere(dt >= max(1.0, 0.5 * peak))
    while len(pts) < max_points and len(cand):
        d = np.min([np.hypot(cand[:, 0] - p[0], cand[:, 1] - p[1]) for p in pts], axis=0)
        k = int(np.argmax(d))
        if d[k] < 2.0:
            break
        pts.append((int(cand[k][0]), int(cand[k][1])))
    return pts


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    u = np.count_nonzero(a | b)
    return float(np.count_nonzero(a & b) / u) if u else 0.0


# ── 单张推理 ──────────────────────────────────────────────────

def _infer_slice(npy_dir: Path, direction: str, index: int, prev_mask: np.ndarray):
    """用 prev_mask 生成点提示, 在 index 切片上跑 SAM。返回 (原生网格 bool mask, score, 点列表)"""
    amp = read_amp_slice(npy_dir, direction, index)
    img, sy, sx = render_slice_image(amp)
    pts_rc = mask_to_points(prev_mask)
    if not pts_rc:
        return np.zeros(prev_mask.shape, dtype=bool), 0.0, []
    pts_xy = [[(c + 0.5) * sx, (r + 0.5) * sy] for r, c in pts_rc]

    fd, tmp = tempfile.mkstemp(suffix=".png", prefix="prop_")
    os.close(fd)
    emb_id = None
    try:
        img.save(tmp, "PNG")
        emb = sam_service.embed_image(tmp)
        emb_id = emb["embedding_id"]
        out = sam_service.predict_mask_np(emb_id, pts_xy, [1] * len(pts_xy))
    finally:
        if emb_id is not None:
            sam_service.drop_embedding(emb_id)
        try:
            os.remove(tmp)
        except OSError:
            pass
    native = vms.resample_mask_to_grid(out["mask"], amp.shape)
    score = float(out["scores"][0]) if out.get("scores") else 0.0
    return native, score, [{"row": r, "col": c, "label": 1} for r, c in pts_rc]


# ── 对外入口 ──────────────────────────────────────────────────

def propagate(npy_dir: str, mask_name: str, direction: str, index: int,
              max_il: int = 5, max_xl: int = 5, max_vertical: int = 30,
              min_iou: float = 0.1) -> dict:
    """
    以体 mask 中 (direction, index) 切片为种子, 向两侧逐张传播。
    返回传播盒、逐张结果与体 mask 汇总。
    """
    if direction not in vms.DIRECTIONS:
        raise ValueError(f"未知方向: {direction}")
    for name, v in (("max_il", max_il), ("max_xl", max_xl), ("max_vertical", max_vertical)):
        if not isinstance(v, int) or v < 0:
            raise ValueError(f"{name} 必须是非负整数")
    if not 0.0 <= min_iou <= 1.0:
        raise ValueError("min_iou 必须在 [0,1]")

    d = Path(npy_dir)
    vol_shape = vms._vol_shape(d)
    n_axis = vms.slice_max_index(direction, vol_shape)
    if not 0 <= index < n_axis:
        raise IndexError(f"{direction} 索引 {index} 超出范围 [0, {n_axis - 1}]")

    mask_vol = vms.read_mask_volume(npy_dir, mask_name)
    seed = np.array(vms._slice_view(mask_vol, direction, index), dtype=bool)
    del mask_vol
    if not seed.any():
        raise ValueError(f"种子切片 {direction}:{index} 在 mask '{mask_name}' 中为空, 请先对该切片运行 SAM")

    box = build_box(direction, index, seed, vol_shape, max_il, max_xl, max_vertical)
    lo, hi = axis_range(direction, box)
    grid = vms.slice_grid_shape(direction, vol_shape)
    allowed = box_mask_2d(direction, grid, box)

    results = []
    for step_dir, rng in ((+1, range(index + 1, hi + 1)), (-1, range(index - 1, lo - 1, -1))):
        prev = seed
        reason = "box_limit"
        for i in rng:
            native, score, pts = _infer_slice(d, direction, i, prev)
            cur = native & allowed
            vox = int(cur.sum())
            ov = _iou(cur, prev)
            if vox == 0:
                results.append({"index": i, "side": step_dir, "voxels": 0, "score": score, "iou_prev": 0.0,
                                "written": False, "stopped": "empty"})
                reason = "empty"
                break
            if ov < min_iou:
                results.append({"index": i, "side": step_dir, "voxels": vox, "score": score, "iou_prev": ov,
                                "written": False, "stopped": "low_iou"})
                reason = "low_iou"
                break
            vms.write_slice_mask(npy_dir, mask_name, direction, i, cur.astype(np.float32),
                                 mode="replace", score=score,
                                 points=[{**p, "source": f"propagated_from_{i - step_dir}"} for p in pts])
            results.append({"index": i, "side": step_dir, "voxels": vox, "score": score, "iou_prev": ov,
                            "written": True, "stopped": None})
            prev = cur
        logger.info("传播 %s 方向 %+d 结束: %s", direction, step_dir, reason)

    info = vms.get_mask_info(npy_dir, mask_name)
    written = sorted(r["index"] for r in results if r["written"])
    return {"direction": direction, "seed_index": index, "box": {k: list(v) for k, v in box.items()},
            "limits": {"max_il": max_il, "max_xl": max_xl, "max_vertical": max_vertical, "min_iou": min_iou},
            "slices": results, "written_indices": written,
            "total_voxels": info.get("voxel_count", 0)}
