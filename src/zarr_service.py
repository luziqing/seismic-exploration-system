"""
Zarr 地震数据体存储

将 SGY 转换为 Zarr 格式 (.zarr)，提供:
  - O(1) Inline 切片读取
  - O(1) Crossline 切片读取 (双存储)
  - 快速 TimeSlice 读取
  - LZ4 压缩
  - 完整元数据 (IL/XL 范围, 采样间隔等)

兼容 Zarr v3 API。
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("sam3-server")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ZARR_DIR = DATA_DIR / "zarr"

# Zarr v3 API 检测
try:
    import zarr
    _ZARR_VERSION = int(zarr.__version__.split(".")[0])
except Exception:
    _ZARR_VERSION = 2

if _ZARR_VERSION < 3:
    logger.warning("检测到 Zarr v%d，本项目需要 Zarr v3+。请升级: pip install 'zarr>=3.0'", _ZARR_VERSION)


def _ensure_zarr_dir():
    ZARR_DIR.mkdir(parents=True, exist_ok=True)


def sgy_to_zarr(sgy_path: str, zarr_name: Optional[str] = None,
                il_byte: int = 0, xl_byte: int = 0) -> dict:
    """
    将 SGY/SEG-Y 文件转换为 Zarr 格式。

    il_byte/xl_byte: 自定义道头字节偏移 (0 = 使用 segyio 默认)
    返回: {zarr_path, il_range, xl_range, n_samples, dt_us, shape}
    """
    import segyio
    import zarr
    import zarr.storage

    _ensure_zarr_dir()

    sgy_path = str(sgy_path)
    if zarr_name is None:
        zarr_name = Path(sgy_path).stem + ".zarr"
    if not zarr_name.endswith(".zarr"):
        zarr_name += ".zarr"
    zarr_path = ZARR_DIR / zarr_name

    logger.info("开始 SGY -> Zarr 转换: %s -> %s", sgy_path, zarr_path)

    kwargs = {}
    if il_byte and xl_byte:
        kwargs = dict(iline=il_byte, xline=xl_byte)

    with segyio.open(sgy_path, "r", ignore_geometry=False, **kwargs) as f:
        ilines = np.array(f.ilines, dtype=np.int32)
        xlines = np.array(f.xlines, dtype=np.int32)
        samples = np.array(f.samples, dtype=np.float64)
        n_il = len(ilines)
        n_xl = len(xlines)
        n_samp = len(samples)
        dt_us = int(f.bin[segyio.BinField.Interval])

        # Zarr v3: 使用 LocalStore + open_group
        store = zarr.storage.LocalStore(str(zarr_path))
        root = zarr.open_group(store=store, mode="w")

        # 主存储: IL × XL × Samples, 每个 IL 一块
        amplitude = root.create_array(
            "amplitude",
            shape=(n_il, n_xl, n_samp),
            chunks=(1, n_xl, n_samp),
            dtype="float32",
            compressors=zarr.codecs.BloscCodec(cname="lz4", clevel=3),
        )

        # 转置副本: XL × IL × Samples, 每个 XL 一块
        amplitude_xl = root.create_array(
            "amplitude_xl",
            shape=(n_xl, n_il, n_samp),
            chunks=(1, n_il, n_samp),
            dtype="float32",
            compressors=zarr.codecs.BloscCodec(cname="lz4", clevel=3),
        )

        # 逐 IL 写入
        for i, il_val in enumerate(ilines):
            il_data = np.array(f.iline[int(il_val)], dtype=np.float32)
            amplitude[i, :, :] = il_data
            amplitude_xl[:, i, :] = il_data
            if (i + 1) % 50 == 0:
                logger.info("Zarr 写入进度: %d/%d IL", i + 1, n_il)

        # 元数据
        root.attrs["source_file"] = str(sgy_path)
        root.attrs["il_range"] = [int(ilines[0]), int(ilines[-1])]
        root.attrs["xl_range"] = [int(xlines[0]), int(xlines[-1])]
        root.attrs["ilines"] = ilines.tolist()
        root.attrs["xlines"] = xlines.tolist()
        root.attrs["samples"] = samples.tolist()
        root.attrs["n_inlines"] = n_il
        root.attrs["n_crosslines"] = n_xl
        root.attrs["n_samples"] = n_samp
        root.attrs["dt_us"] = dt_us
        root.attrs["format_version"] = "1.0"

    # 统计文件大小
    total_size = sum(f.stat().st_size for f in zarr_path.rglob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)

    logger.info(
        "Zarr 转换完成: %s  shape=(%d,%d,%d)  size=%.1f MB",
        zarr_name, n_il, n_xl, n_samp, size_mb,
    )

    return {
        "zarr_path": str(zarr_path),
        "zarr_name": zarr_name,
        "il_range": [int(ilines[0]), int(ilines[-1])],
        "xl_range": [int(xlines[0]), int(xlines[-1])],
        "n_inlines": n_il,
        "n_crosslines": n_xl,
        "n_samples": n_samp,
        "dt_us": dt_us,
        "shape": [n_il, n_xl, n_samp],
        "size_mb": round(size_mb, 1),
    }


def read_inline(zarr_path: str, il_index: int) -> np.ndarray:
    """读取第 il_index 条 Inline, shape=(nXL, nSamples)"""
    import zarr
    root = zarr.open_group(str(zarr_path), mode="r")
    return np.array(root["amplitude"][il_index, :, :])


def read_crossline(zarr_path: str, xl_index: int) -> np.ndarray:
    """读取第 xl_index 条 Crossline, shape=(nIL, nSamples)"""
    import zarr
    root = zarr.open_group(str(zarr_path), mode="r")
    return np.array(root["amplitude_xl"][xl_index, :, :])


def read_timeslice(zarr_path: str, sample_index: int) -> np.ndarray:
    """读取第 sample_index 个时间切片, shape=(nIL, nXL)"""
    import zarr
    root = zarr.open_group(str(zarr_path), mode="r")
    return np.array(root["amplitude"][:, :, sample_index])


def get_zarr_metadata(zarr_path: str) -> dict:
    """读取 Zarr 元数据"""
    import zarr
    root = zarr.open_group(str(zarr_path), mode="r")
    return dict(root.attrs)


def list_zarr_volumes() -> list[dict]:
    """列出 data/zarr/ 中所有 Zarr 卷"""
    _ensure_zarr_dir()
    volumes = []
    for p in sorted(ZARR_DIR.iterdir()):
        if p.is_dir() and p.suffix == ".zarr":
            try:
                meta = get_zarr_metadata(str(p))
                volumes.append({
                    "name": p.name,
                    "path": str(p),
                    "il_range": meta.get("il_range", []),
                    "xl_range": meta.get("xl_range", []),
                    "n_inlines": meta.get("n_inlines", 0),
                    "n_crosslines": meta.get("n_crosslines", 0),
                    "n_samples": meta.get("n_samples", 0),
                })
            except Exception:
                volumes.append({"name": p.name, "path": str(p), "error": "无法读取元数据"})
    return volumes


def find_zarr_for_sgy(sgy_filename: str) -> Optional[str]:
    """查找某 SGY 文件对应的 Zarr 路径"""
    _ensure_zarr_dir()
    zarr_name = Path(sgy_filename).stem + ".zarr"
    zarr_path = ZARR_DIR / zarr_name
    if zarr_path.exists():
        return str(zarr_path)
    return None
