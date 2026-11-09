"""
NumPy memmap 地震数据体存储

替代 Zarr 方案，提供:
  - SGY → numpy 转换 (~3s，vs Zarr ~30s)
  - memmap 零拷贝读取 inline/crossline/timeslice
  - 二进制 float32 响应 (270KB/切片 vs JSON 1.2MB)
"""

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger("sam3-server")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NPY_DIR = DATA_DIR / "npy"


def _ensure_dir():
    NPY_DIR.mkdir(parents=True, exist_ok=True)


def sgy_to_npy(sgy_path: str, npy_name: str = None,
               il_byte: int = 0, xl_byte: int = 0) -> dict:
    """
    SGY → numpy .npy 文件 (float32, shape [nIL, nXL, nSamples])。
    返回: {npy_path, npy_name, il_range, xl_range, ...}
    """
    import segyio

    _ensure_dir()
    sgy_path = str(sgy_path)
    if npy_name is None:
        npy_name = Path(sgy_path).stem
    npy_dir = NPY_DIR / npy_name
    npy_dir.mkdir(parents=True, exist_ok=True)

    npy_path = npy_dir / "amplitude.npy"
    meta_path = npy_dir / "meta.json"

    logger.info("开始 SGY -> NumPy 转换: %s -> %s", sgy_path, npy_path)

    kwargs = {}
    if il_byte and xl_byte:
        kwargs = dict(iline=il_byte, xline=xl_byte)

    with segyio.open(sgy_path, "r", ignore_geometry=False, **kwargs) as f:
        ilines = np.array(f.ilines, dtype=np.int32)
        xlines = np.array(f.xlines, dtype=np.int32)
        samples = np.array(f.samples, dtype=np.float64)
        n_il, n_xl, n_samp = len(ilines), len(xlines), len(samples)
        dt_us = int(f.bin[segyio.BinField.Interval])

        # 预分配 float32 数组
        volume = np.empty((n_il, n_xl, n_samp), dtype=np.float32)
        for i, il_val in enumerate(ilines):
            volume[i] = f.iline[int(il_val)]
            if (i + 1) % 50 == 0:
                logger.info("NumPy 写入进度: %d/%d IL", i + 1, n_il)

        # 保存 .npy
        np.save(str(npy_path), volume)

        # 保存元数据
        meta = {
            "source_file": sgy_path,
            "il_range": [int(ilines[0]), int(ilines[-1])],
            "xl_range": [int(xlines[0]), int(xlines[-1])],
            "ilines": ilines.tolist(),
            "xlines": xlines.tolist(),
            "samples": samples.tolist(),
            "n_inlines": n_il,
            "n_crosslines": n_xl,
            "n_samples": n_samp,
            "dt_us": dt_us,
            "shape": [n_il, n_xl, n_samp],
        }
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    size_mb = npy_path.stat().st_size / (1024 * 1024)
    logger.info("NumPy 转换完成: %s  shape=(%d,%d,%d)  size=%.1f MB",
                npy_name, n_il, n_xl, n_samp, size_mb)

    return {
        "npy_path": str(npy_path),
        "npy_name": npy_name,
        "il_range": [int(ilines[0]), int(ilines[-1])],
        "xl_range": [int(xlines[0]), int(xlines[-1])],
        "n_inlines": n_il,
        "n_crosslines": n_xl,
        "n_samples": n_samp,
        "dt_us": dt_us,
        "shape": [n_il, n_xl, n_samp],
        "size_mb": round(size_mb, 1),
    }


# ── memmap 读取 ──────────────────────────────────────────────

def _load_mmap(npy_dir: str) -> np.ndarray:
    """加载 memmap (只读, 零拷贝)"""
    npy_path = Path(npy_dir) / "amplitude.npy"
    if not npy_path.exists():
        raise FileNotFoundError(f"NumPy 卷不存在: {npy_path}")
    return np.load(str(npy_path), mmap_mode='r')


def read_inline(npy_dir: str, il_index: int) -> np.ndarray:
    """读取第 il_index 条 Inline, 返回 shape=(nSamples, nXL) — sample 纵轴, XL 横轴"""
    vol = _load_mmap(npy_dir)
    if il_index < 0 or il_index >= vol.shape[0]:
        raise IndexError(f"Inline 索引 {il_index} 超出范围 [0, {vol.shape[0]-1}]")
    # vol[il] shape = (nXL, nSamples) → 转置 → (nSamples, nXL)
    return np.array(vol[il_index]).T.copy()


def read_crossline(npy_dir: str, xl_index: int) -> np.ndarray:
    """读取第 xl_index 条 Crossline, 返回 shape=(nSamples, nIL) — sample 纵轴, IL 横轴"""
    vol = _load_mmap(npy_dir)
    if xl_index < 0 or xl_index >= vol.shape[1]:
        raise IndexError(f"Crossline 索引 {xl_index} 超出范围 [0, {vol.shape[1]-1}]")
    # vol[:, xl] shape = (nIL, nSamples) → 转置 → (nSamples, nIL)
    return np.array(vol[:, xl_index, :]).T.copy()


def read_timeslice(npy_dir: str, sample_index: int) -> np.ndarray:
    """读取第 sample_index 个时间切片, 返回 shape=(nIL, nXL) 的副本"""
    vol = _load_mmap(npy_dir)
    if sample_index < 0 or sample_index >= vol.shape[2]:
        raise IndexError(f"TimeSlice 索引 {sample_index} 超出范围 [0, {vol.shape[2]-1}]")
    return np.array(vol[:, :, sample_index])


# ── 元数据 ────────────────────────────────────────────────────

def get_metadata(npy_dir: str) -> dict:
    """读取 NumPy 卷元数据"""
    meta_path = Path(npy_dir) / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"元数据不存在: {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def list_volumes() -> list[dict]:
    """列出 data/npy/ 中所有 NumPy 卷"""
    _ensure_dir()
    volumes = []
    for p in sorted(NPY_DIR.iterdir()):
        if p.is_dir() and (p / "amplitude.npy").exists():
            try:
                meta = get_metadata(str(p))
                size_mb = (p / "amplitude.npy").stat().st_size / (1024 * 1024)
                volumes.append({
                    "name": p.name,
                    "path": str(p),
                    "il_range": meta.get("il_range", []),
                    "xl_range": meta.get("xl_range", []),
                    "n_inlines": meta.get("n_inlines", 0),
                    "n_crosslines": meta.get("n_crosslines", 0),
                    "n_samples": meta.get("n_samples", 0),
                    "size_mb": round(size_mb, 1),
                })
            except Exception:
                volumes.append({"name": p.name, "path": str(p), "error": "无法读取"})
    return volumes


def find_for_sgy(sgy_filename: str) -> str | None:
    """查找某 SGY 文件对应的 NumPy 卷路径"""
    _ensure_dir()
    npy_name = Path(sgy_filename).stem
    npy_dir = NPY_DIR / npy_name
    if (npy_dir / "amplitude.npy").exists():
        return str(npy_dir)
    return None
