"""
3-D volume mask service: maps SAM 2-D slice masks back onto the seismic grid and stores them as a voxel mask

Conventions (same as npy_service):
  volume amplitude.npy:   shape = (nIL, nXL, nSamples)
  inline slice image:     (nSamples, nXL)   vertical = samples, horizontal = XL
  crossline slice image:  (nSamples, nIL)   vertical = samples, horizontal = IL
  timeslice slice image:  (nIL, nXL)        vertical = IL,      horizontal = XL

SAM returns masks in image pixel space (upscaled/downsampled, any h×w) covering the whole slice image,
so they are linearly rescaled to the native slice grid and written into the volume mask by direction.

Storage: data/npy/<vol>/masks/<mask_name>.npy (bool, same shape as the amplitude volume, memmap updated in place)
      data/npy/<vol>/masks/<mask_name>.json (source, per-slice records, voxel count)
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
        raise ValueError(f"Invalid name: {name!r} (only letters, digits, _ . - allowed)")


def _vol_shape(npy_dir: Path) -> tuple[int, int, int]:
    vol = np.load(str(npy_dir / "amplitude.npy"), mmap_mode="r")
    if vol.ndim != 3:
        raise ValueError(f"Amplitude volume must be 3D, got {vol.ndim}D")
    return tuple(int(s) for s in vol.shape)


def slice_grid_shape(direction: str, vol_shape: tuple[int, int, int]) -> tuple[int, int]:
    """Native slice grid (rows, cols)"""
    n_il, n_xl, n_s = vol_shape
    if direction == "inline":
        return (n_s, n_xl)
    if direction == "crossline":
        return (n_s, n_il)
    if direction == "timeslice":
        return (n_il, n_xl)
    raise ValueError(f"Unknown direction: {direction}")


def slice_max_index(direction: str, vol_shape: tuple[int, int, int]) -> int:
    return {"inline": vol_shape[0], "crossline": vol_shape[1], "timeslice": vol_shape[2]}[direction]


def resample_mask_to_grid(mask, grid_shape: tuple[int, int], threshold: float = 0.5) -> np.ndarray:
    """
    Rescale a 2-D mask of any size (probability / logit 0..1 / bool) to the native slice grid and binarize it.
    Floats are rescaled bilinearly before thresholding, so an N-times upscaled mask keeps its edges when shrunk back.
    """
    arr = np.asarray(mask, dtype=np.float32)
    if arr.ndim != 2 or arr.size == 0:
        raise ValueError(f"mask must be a non-empty 2D array, got shape={arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("mask contains NaN/Inf")
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
            raise ValueError(f"Existing mask volume does not match the amplitude volume: {m.shape}/{m.dtype} vs {vol_shape}")
        return m
    return np.lib.format.open_memmap(str(npy_path), mode="w+", dtype=np.bool_, shape=tuple(vol_shape))


def _slice_view(vol: np.ndarray, direction: str, index: int) -> np.ndarray:
    """Return a writable view of this slice in the volume, in slice-image orientation"""
    if direction == "inline":
        return vol[index].T        # (nXL, nS).T -> (nS, nXL)
    if direction == "crossline":
        return vol[:, index, :].T  # (nIL, nS).T -> (nS, nIL)
    return vol[:, :, index]        # (nIL, nXL)


def write_slice_mask(npy_dir: str, mask_name: str, direction: str, index: int, mask,
                     threshold: float = 0.5, mode: str = "replace",
                     score: float | None = None, points: list | None = None) -> dict:
    """
    Write one slice's 2-D mask into the volume mask.
    mode: replace = overwrite the slice;  union = merge with what is there
    """
    _check_name(mask_name)
    if direction not in DIRECTIONS:
        raise ValueError(f"Unknown direction: {direction}")
    if mode not in ("replace", "union"):
        raise ValueError(f"Unknown mode: {mode}")
    npy_dir_p = Path(npy_dir)
    vol_shape = _vol_shape(npy_dir_p)
    if not (0 <= index < slice_max_index(direction, vol_shape)):
        raise IndexError(f"{direction} index {index} out of range [0, {slice_max_index(direction, vol_shape) - 1}]")

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
        raise FileNotFoundError(f"Mask volume not found: {mask_name}")
    return np.load(str(npy_path), mmap_mode="r")


def mask_footprint(npy_dir: str, mask_name: str) -> np.ndarray:
    """Plan-view footprint of a volume mask: voxels per trace, float32 (nIL, nXL)."""
    vol = read_mask_volume(npy_dir, mask_name)
    return np.count_nonzero(vol, axis=2).astype(np.float32)


def get_mask_info(npy_dir: str, mask_name: str, volume_meta: dict | None = None) -> dict:
    """Mask volume info: metadata plus bounding box and centroid in (il, xl, sample time)"""
    _check_name(mask_name)
    _, meta_path = _paths(Path(npy_dir), mask_name)
    if not meta_path.exists():
        raise FileNotFoundError(f"Mask volume not found: {mask_name}")
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
