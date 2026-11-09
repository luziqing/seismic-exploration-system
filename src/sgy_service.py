"""
SGY/SEG-Y 处理服务 — 上传解析、NumPy 转换、切片生成

流程: SGY 上传 → 解析元数据 → 转换为 NumPy (.npy) → 从 memmap 生成切片图片
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("sam3-server")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SGY_DIR = DATA_DIR / "sgy"
IMAGES_DIR = DATA_DIR / "images"

# ── 当前 SGY/NumPy 状态 ──────────────────────────────────────
_current: dict = {
    "sgy_path": None,
    "sgy_filename": None,
    "npy_path": None,
    "ilines": [],
    "xlines": [],
    "samples": [],
    "n_inlines": 0,
    "n_crosslines": 0,
    "n_samples": 0,
    "dt_us": 0,
    "db_id": None,
}


def get_current() -> dict:
    return _current.copy()


def is_loaded() -> bool:
    return _current["sgy_path"] is not None


def upload_and_convert(save_path: str, filename: str,
                       il_byte: int = 0, xl_byte: int = 0) -> dict:
    """
    上传 SGY → 解析元数据 → 转换为 NumPy (.npy)。

    返回: {filename, il_range, xl_range, n_samples, dt_us, npy_path, ...}
    """
    import segyio
    import npy_service

    # 1. 解析 SGY 元数据 — 多种策略尝试
    ilines, xlines, samples, dt = [], [], [], 0

    strategies = []
    if il_byte and xl_byte:
        strategies.append(("custom", dict(iline=il_byte, xline=xl_byte)))
    strategies += [
        ("standard_189_193", dict(iline=189, xline=193)),
        ("alt_5_21", dict(iline=5, xline=21)),
        ("alt_21_5", dict(iline=21, xline=5)),
    ]

    for name, kwargs in strategies:
        try:
            with segyio.open(save_path, "r", ignore_geometry=False, **kwargs) as f:
                ilines = [int(x) for x in f.ilines]
                xlines = [int(x) for x in f.xlines]
                samples = [float(x) for x in f.samples]
                dt = int(f.bin[segyio.BinField.Interval])
            if ilines and len(ilines) > 1:
                logger.info("SGY 几何解析成功: strategy=%s  IL=%d~%d(%d)  XL=%d~%d(%d)",
                            name, ilines[0], ilines[-1], len(ilines),
                            xlines[0], xlines[-1], len(xlines))
                _current["il_byte"] = kwargs["iline"]
                _current["xl_byte"] = kwargs["xline"]
                break
        except Exception:
            continue

    # 所有策略失败, fallback 到无几何模式
    if not ilines:
        with segyio.open(save_path, "r", ignore_geometry=True) as f:
            samples = [float(i) for i in range(f.samples.size)]
            dt = int(f.bin[segyio.BinField.Interval])

    # 2. 更新全局状态
    _current.update({
        "sgy_path": save_path,
        "sgy_filename": filename,
        "ilines": ilines,
        "xlines": xlines,
        "samples": samples,
        "n_inlines": len(ilines),
        "n_crosslines": len(xlines),
        "n_samples": len(samples),
        "dt_us": dt,
    })

    info = {
        "filename": filename,
        "il_range": [ilines[0], ilines[-1]] if ilines else [0, 0],
        "xl_range": [xlines[0], xlines[-1]] if xlines else [0, 0],
        "n_inlines": len(ilines),
        "n_crosslines": len(xlines),
        "n_samples": len(samples),
        "dt_us": dt,
        "sample_range": [samples[0], samples[-1]] if samples else [0, 0],
    }

    # 3. 如果有几何信息, 转换为 NumPy
    if ilines:
        try:
            npy_result = npy_service.sgy_to_npy(
                save_path,
                il_byte=_current.get("il_byte", 0),
                xl_byte=_current.get("xl_byte", 0),
            )
            _current["npy_path"] = npy_result["npy_path"]
            info["npy_path"] = npy_result["npy_path"]
            info["npy_name"] = npy_result["npy_name"]
            info["npy_size_mb"] = npy_result["size_mb"]
            logger.info("NumPy 转换完成: %s (%.1f MB)", npy_result["npy_name"], npy_result["size_mb"])
        except Exception as e:
            logger.warning("NumPy 转换失败 (将使用 segyio 直接读取): %s", e)
            info["npy_error"] = str(e)

    logger.info("SGY 加载完成: %s  IL=%s  XL=%s", filename, info["il_range"], info["xl_range"])
    return info


# ── 切片生成 (优先从 Zarr 读取, fallback 到 segyio) ────────────

def generate_slices(
    inline_indices: Optional[list[int]] = None,
    crossline_indices: Optional[list[int]] = None,
    timeslice_indices: Optional[list[int]] = None,
    count_per_type: int = 5,
) -> dict:
    """生成三类切片图片, 优先从 Zarr 读取"""
    if not _current["sgy_path"]:
        raise ValueError("请先加载 SGY 文件")
    if _current["n_inlines"] == 0:
        raise ValueError("SGY 文件缺少 IL/XL 几何信息")

    ilines = np.array(_current["ilines"])
    xlines = np.array(_current["xlines"])
    samples = np.array(_current["samples"])
    n_il = _current["n_inlines"]
    n_xl = _current["n_crosslines"]
    n_samp = _current["n_samples"]

    # 自动默认索引
    if not inline_indices:
        idx = np.linspace(0, n_il - 1, count_per_type + 2, dtype=int)[1:-1]
        inline_indices = [int(ilines[i]) for i in idx]
    if not crossline_indices:
        idx = np.linspace(0, n_xl - 1, count_per_type + 2, dtype=int)[1:-1]
        crossline_indices = [int(xlines[i]) for i in idx]
    if not timeslice_indices:
        idx = np.linspace(0, n_samp - 1, count_per_type + 2, dtype=int)[1:-1]
        timeslice_indices = [int(samples[i]) for i in idx]

    generated = {"inline": [], "crossline": [], "timeslice": []}
    use_npy = _current.get("npy_path") is not None

    # ── Inline 切片 ──────────────────────────────────────────
    for il_val in inline_indices:
        name = f"IL_{il_val:04d}.png"
        save_path = IMAGES_DIR / "inline" / name
        try:
            il_idx = int(np.argmin(np.abs(ilines - il_val)))
            if use_npy:
                import npy_service
                data = npy_service.read_inline(str(Path(_current["npy_path"]).parent), il_idx)
            else:
                import segyio
                with segyio.open(_current["sgy_path"], "r", ignore_geometry=False) as f:
                    data = np.array(f.iline[il_val], dtype=np.float32)

            _render_slice(
                data.T, [xlines[0], xlines[-1], samples[-1], samples[0]],
                f"Inline {il_val}", "Crossline", "Time (ms)", save_path,
            )
            generated["inline"].append(name)
        except Exception as e:
            logger.warning("Inline %d 失败: %s", il_val, e)

    # ── Crossline 切片 ───────────────────────────────────────
    for xl_val in crossline_indices:
        name = f"XL_{xl_val:04d}.png"
        save_path = IMAGES_DIR / "crossline" / name
        try:
            xl_idx = int(np.argmin(np.abs(xlines - xl_val)))
            if use_npy:
                import npy_service
                data = npy_service.read_crossline(str(Path(_current["npy_path"]).parent), xl_idx)
            else:
                import segyio
                with segyio.open(_current["sgy_path"], "r", ignore_geometry=False) as f:
                    data = np.array(f.xline[xl_val], dtype=np.float32)

            _render_slice(
                data.T, [ilines[0], ilines[-1], samples[-1], samples[0]],
                f"Crossline {xl_val}", "Inline", "Time (ms)", save_path,
            )
            generated["crossline"].append(name)
        except Exception as e:
            logger.warning("Crossline %d 失败: %s", xl_val, e)

    # ── TimeSlice ─────────────────────────────────────────────
    for ts_val in timeslice_indices:
        name = f"TS_{ts_val:04d}ms.png"
        save_path = IMAGES_DIR / "timeslice" / name
        try:
            samp_idx = int(np.argmin(np.abs(samples - ts_val)))
            if use_npy:
                import npy_service
                data = npy_service.read_timeslice(str(Path(_current["npy_path"]).parent), samp_idx)
            else:
                import segyio
                with segyio.open(_current["sgy_path"], "r", ignore_geometry=False) as f:
                    data = np.array(f.depth_slice[samp_idx], dtype=np.float32)

            _render_slice(
                data, [xlines[0], xlines[-1], ilines[-1], ilines[0]],
                f"TimeSlice {ts_val} ms", "Crossline", "Inline", save_path,
            )
            generated["timeslice"].append(name)
        except Exception as e:
            logger.warning("TimeSlice %d 失败: %s", ts_val, e)

    total = sum(len(v) for v in generated.values())
    logger.info("切片生成完成: %d 张 (NumPy=%s)", total, use_npy)
    return {"generated": total, "slices": generated, "source": "numpy" if use_npy else "segyio"}


def list_existing_slices() -> dict:
    result = {"inline": [], "crossline": [], "timeslice": []}
    for cat in result:
        cat_dir = IMAGES_DIR / cat
        if cat_dir.exists():
            result[cat] = sorted(
                f.name for f in cat_dir.iterdir()
                if f.suffix.lower() in (".png", ".jpg", ".jpeg")
            )
    return result


def _render_slice(data, extent, title, xlabel, ylabel, save_path: Path):
    clip = np.percentile(np.abs(data), 99) or 1.0
    fig, ax = plt.subplots(figsize=(12, 8), dpi=150)
    ax.imshow(data, cmap="seismic", aspect="auto", extent=extent,
              vmin=-clip, vmax=clip, interpolation="bilinear")
    ax.set_title(title, fontsize=14)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    plt.colorbar(ax.images[0], ax=ax, label="Amplitude", shrink=0.8)
    plt.tight_layout()
    plt.savefig(str(save_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
