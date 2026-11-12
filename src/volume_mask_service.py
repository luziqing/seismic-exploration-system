"""
三维体 mask 服务 — 把 SAM 的 2D 切片 mask 回映射到地震体网格并存成体素 mask

约定 (与 npy_service 一致):
  体 amplitude.npy:      shape = (nIL, nXL, nSamples)
  inline 切片图像:        (nSamples, nXL)   纵轴 = 采样点, 横轴 = XL
  crossline 切片图像:     (nSamples, nIL)   纵轴 = 采样点, 横轴 = IL
  timeslice 切片图像:     (nIL, nXL)        纵轴 = IL,   横轴 = XL

SAM 返回的 mask 是图像像素空间 (经放大/降采样, 任意 h×w), 覆盖整张切片图像,
因此用线性缩放回到切片原生网格, 再按方向写入体 mask 对应位置。

存储: data/npy/<vol>/masks/<mask_name>.npy (bool, 与振幅体同 shape, memmap 原地更新)
      data/npy/<vol>/masks/<mask_name>.json (来源、逐切片记录、体素数)
"""

import json
import re
import time
from pathlib import Path

import numpy as np
from PIL import Image

DIRECTIONS = ("inline", "crossline", "timeslice")
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def _check_name(name: str):
    if not _NAME_RE.match(name) or name in (".", ".."):
        raise ValueError(f"非法名称: {name!r} (仅允许字母数字 _ . -)")


def _vol_shape(npy_dir: Path) -> tuple[int, int, int]:
    vol = np.load(str(npy_dir / "amplitude.npy"), mmap_mode="r")
    if vol.ndim != 3:
        raise ValueError(f"振幅体应为 3D, 实际 {vol.ndim}D")
    return tuple(int(s) for s in vol.shape)


def slice_grid_shape(direction: str, vol_shape: tuple[int, int, int]) -> tuple[int, int]:
    """切片原生网格 (rows, cols)"""
    n_il, n_xl, n_s = vol_shape
    if direction == "inline":
        return (n_s, n_xl)
    if direction == "crossline":
        return (n_s, n_il)
    if direction == "timeslice":
        return (n_il, n_xl)
    raise ValueError(f"未知方向: {direction}")


def slice_max_index(direction: str, vol_shape: tuple[int, int, int]) -> int:
    return {"inline": vol_shape[0], "crossline": vol_shape[1], "timeslice": vol_shape[2]}[direction]


def resample_mask_to_grid(mask, grid_shape: tuple[int, int], threshold: float = 0.5) -> np.ndarray:
    """
    把任意尺寸的 2D mask (概率/logit-0..1/布尔) 缩放到切片原生网格并二值化。
    先对 float 做双线性缩放再阈值, 这样放大 N 倍的 mask 回缩时不会丢边界。
    """
    arr = np.asarray(mask, dtype=np.float32)
    if arr.ndim != 2 or arr.size == 0:
        raise ValueError(f"mask 必须是非空 2D 数组, 实际 shape={arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("mask 含 NaN/Inf")
    rows, cols = grid_shape
    if arr.shape == (rows, cols):
        return arr >= threshold
    img = Image.fromarray(arr, mode="F").resize((cols, rows), Image.BILINEAR)
    return np.asarray(img) >= threshold


def _paths(npy_dir: Path, mask_name: str) -> tuple[Path, Path]:
    d = npy_dir / "masks"
    return d / f"{mask_name}.npy", d / f"{mask_name}.json"


def _open_mask_volume(npy_dir: Path, mask_name: str, vol_shape) -> np.ndarray:
    npy_path, _ = _paths(npy_dir, mask_name)
    npy_path.parent.mkdir(parents=True, exist_ok=True)
    if npy_path.exists():
        m = np.lib.format.open_memmap(str(npy_path), mode="r+")
        if tuple(m.shape) != tuple(vol_shape) or m.dtype != np.bool_:
            raise ValueError(f"已存在的 mask 体与振幅体不一致: {m.shape}/{m.dtype} vs {vol_shape}")
        return m
    return np.lib.format.open_memmap(str(npy_path), mode="w+", dtype=np.bool_, shape=tuple(vol_shape))


def _slice_view(vol: np.ndarray, direction: str, index: int) -> np.ndarray:
    """返回体中该切片的『切片图像朝向』视图 (可写)"""
    if direction == "inline":
        return vol[index].T        # (nXL, nS).T -> (nS, nXL)
    if direction == "crossline":
        return vol[:, index, :].T  # (nIL, nS).T -> (nS, nIL)
    return vol[:, :, index]        # (nIL, nXL)


def write_slice_mask(npy_dir: str, mask_name: str, direction: str, index: int, mask,
                     threshold: float = 0.5, mode: str = "replace",
                     score: float | None = None, points: list | None = None) -> dict:
    """
    把一张切片的 2D mask 写入体 mask。
    mode: replace = 覆盖该切片;  union = 与已有取并集
    """
    _check_name(mask_name)
    if direction not in DIRECTIONS:
        raise ValueError(f"未知方向: {direction}")
    if mode not in ("replace", "union"):
        raise ValueError(f"未知 mode: {mode}")
    npy_dir_p = Path(npy_dir)
    vol_shape = _vol_shape(npy_dir_p)
    if not (0 <= index < slice_max_index(direction, vol_shape)):
        raise IndexError(f"{direction} 索引 {index} 超出范围 [0, {slice_max_index(direction, vol_shape) - 1}]")

    grid = slice_grid_shape(direction, vol_shape)
    src_shape = list(np.asarray(mask).shape)
    native = resample_mask_to_grid(mask, grid, threshold)

    vol = _open_mask_volume(npy_dir_p, mask_name, vol_shape)
    view = _slice_view(vol, direction, index)
    view[...] = (view | native) if mode == "union" else native
    vol.flush()
    n_slice = int(view.sum())
    total = int(np.count_nonzero(vol))
    del vol

    _, meta_path = _paths(npy_dir_p, mask_name)
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {
        "mask_name": mask_name, "volume": npy_dir_p.name, "shape": list(vol_shape),
        "axes": ["inline", "crossline", "sample"], "source": "SAM3", "slices": {},
        "created_at": time.time(),
    }
    meta["slices"][f"{direction}:{index}"] = {
        "direction": direction, "index": index, "src_mask_shape": src_shape,
        "grid_shape": list(grid), "threshold": threshold, "mode": mode,
        "score": score, "points": points or [], "voxels": n_slice, "updated_at": time.time(),
    }
    meta["voxel_count"] = total
    meta["updated_at"] = time.time()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    return {"mask_name": mask_name, "direction": direction, "index": index,
            "src_mask_shape": src_shape, "grid_shape": list(grid),
            "slice_voxels": n_slice, "total_voxels": total,
            "slices_written": len(meta["slices"])}


def read_mask_volume(npy_dir: str, mask_name: str) -> np.ndarray:
    _check_name(mask_name)
    npy_path, _ = _paths(Path(npy_dir), mask_name)
    if not npy_path.exists():
        raise FileNotFoundError(f"mask 体不存在: {mask_name}")
    return np.load(str(npy_path), mmap_mode="r")


def get_mask_info(npy_dir: str, mask_name: str, volume_meta: dict | None = None) -> dict:
    """mask 体信息: 元数据 + 以 (il, xl, sample 时间) 表示的包围盒与质心"""
    _check_name(mask_name)
    _, meta_path = _paths(Path(npy_dir), mask_name)
    if not meta_path.exists():
        raise FileNotFoundError(f"mask 体不存在: {mask_name}")
    info = json.loads(meta_path.read_text(encoding="utf-8"))
    vol = read_mask_volume(npy_dir, mask_name)
    idx = np.argwhere(vol)
    if len(idx) == 0:
        info["bbox_index"] = None
        info["bbox_coords"] = None
        info["centroid_coords"] = None
        return info
    lo, hi = idx.min(axis=0), idx.max(axis=0)
    info["bbox_index"] = {"min": lo.tolist(), "max": hi.tolist()}
    cen = idx.mean(axis=0)
    vm = volume_meta or {}
    axes = [vm.get("ilines"), vm.get("xlines"), vm.get("samples")]
    if all(a is not None and len(a) == s for a, s in zip(axes, vol.shape)):
        def val(a, i):
            return float(np.interp(i, np.arange(len(a)), a))
        info["bbox_coords"] = {
            "min": {"il": axes[0][lo[0]], "xl": axes[1][lo[1]], "sample": axes[2][lo[2]]},
            "max": {"il": axes[0][hi[0]], "xl": axes[1][hi[1]], "sample": axes[2][hi[2]]},
        }
        info["centroid_coords"] = {"il": val(axes[0], cen[0]), "xl": val(axes[1], cen[1]),
                                   "sample": val(axes[2], cen[2])}
    else:
        info["bbox_coords"] = None
        info["centroid_coords"] = None
    return info


def list_masks(npy_dir: str) -> list[dict]:
    d = Path(npy_dir) / "masks"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            out.append({"mask_name": m["mask_name"], "voxel_count": m.get("voxel_count", 0),
                        "slices_written": len(m.get("slices", {}))})
        except Exception:
            continue
    return out
