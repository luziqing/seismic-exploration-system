"""
OpenVDS 地震数据体读取服务

支持:
  - 本地 .vds / .vdso 文件
  - 云端 VDS (S3 / Azure Blob)
  - Inline / Crossline / TimeSlice 快速切片读取
  - VDS → Zarr 转换

OpenVDS 文档: https://osdu.pages.opengroup.org/platform/domain-data-mgmt-services/seismic/open-vds/getting-started.html

依赖: pip install openvds  (需要 Python 3.7–3.11)
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("sam3-server")

# ── 可选导入 ────────────────────────────────────────────────────
try:
    import openvds
    _HAS_OPENVDS = True
except ImportError:
    _HAS_OPENVDS = False
    logger.warning("openvds 未安装, VDS 功能不可用。安装: pip install openvds")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VDS_DIR = DATA_DIR / "vds"

# VDS 维度顺序: sample=0, crossline=1, inline=2
SAMPLE_DIM, CROSSLINE_DIM, INLINE_DIM = 0, 1, 2


def is_available() -> bool:
    """检查 openvds 是否可用"""
    return _HAS_OPENVDS


def _ensure_vds_dir():
    VDS_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# VDS 文件打开 & 上下文管理
# ══════════════════════════════════════════════════════════════════

def open_vds(vds_path: str, connection_string: str = "") -> tuple:
    """
    打开 VDS 文件, 返回 (handle, access_manager, layout)。

    参数:
        vds_path: 本地路径或云 URL (s3://... 或 azure://...)
        connection_string: 云端连接字符串 (本地文件留空)
            S3: "AccessKeyId=xxx;SecretKey=xxx;Region=us-east-1"
            Azure: "DefaultEndpointsProtocol=https;AccountName=xxx;AccountKey=xxx;EndpointSuffix=core.windows.net"

    返回:
        (handle, manager, layout) 三元组
    """
    _check_openvds()

    vds_path = str(vds_path)
    logger.info("打开 VDS: %s", vds_path)

    try:
        handle = openvds.open(vds_path, connection_string)
    except RuntimeError as e:
        raise RuntimeError(f"无法打开 VDS 文件: {vds_path}\n{e}") from e

    manager = openvds.getAccessManager(handle)
    layout = manager.volumeDataLayout

    return handle, manager, layout


def close_vds(handle) -> None:
    """关闭 VDS 句柄"""
    if handle is not None:
        handle.close()


def _check_openvds():
    if not _HAS_OPENVDS:
        raise ImportError(
            "openvds 未安装, 无法使用 VDS 功能。"
            "请运行: pip install openvds"
        )


# ══════════════════════════════════════════════════════════════════
# 切片读取
# ══════════════════════════════════════════════════════════════════

def _read_slice(
    manager,
    layout,
    voxel_min: tuple,
    voxel_max: tuple,
    channel: int = 0,
    lod: int = 0,
) -> np.ndarray:
    """
    读取一个数据切片 (底层, 异步请求→等待→返回 numpy 数组)。

    voxel_min / voxel_max: 三维 tuple (sample, crossline, inline)
    """
    # 使用 OpenVDS 自动分配缓冲区的方式 (阻塞直到数据就绪)
    request = manager.requestVolumeSubset(
        dimensionsND=openvds.DimensionsND.Dimensions_012,
        min=voxel_min,
        max=voxel_max,
        lod=lod,
        channel=channel,
    )
    # request.data 返回一维 numpy 数组, 需要 reshape
    ns = voxel_max[0] - voxel_min[0]
    nxl = voxel_max[1] - voxel_min[1]
    nil = voxel_max[2] - voxel_min[2]

    raw = np.asarray(request.data, dtype=np.float32)
    # VDS 数据布局: [sample, crossline, inline]
    return raw.reshape((ns, nxl, nil))


def read_inline(
    vds_path: str,
    il_index: int,
    connection_string: str = "",
    channel: int = 0,
    lod: int = 0,
) -> np.ndarray:
    """
    读取一条 Inline 切片。

    参数:
        vds_path: VDS 文件路径
        il_index: Inline 的零基索引 (0 ~ nInlines-1)
        connection_string: 云端连接字符串
        channel: 数据通道 (默认 0)
        lod: 细节级别 (默认 0 = 全分辨率)

    返回:
        numpy 数组 shape=(nCrossline, nSample)  — 与 Zarr 服务一致
    """
    _check_openvds()

    handle, manager, layout = open_vds(vds_path, connection_string)
    try:
        n_sample = layout.getDimensionNumSamples(SAMPLE_DIM)
        n_xl = layout.getDimensionNumSamples(CROSSLINE_DIM)

        voxel_min = (0, 0, il_index)
        voxel_max = (n_sample, n_xl, il_index + 1)

        data_3d = _read_slice(manager, layout, voxel_min, voxel_max, channel, lod)
        # data_3d shape: (nSample, nCrossline, 1) → squeeze → (nSample, nCrossline)
        # 转置为 (nCrossline, nSample) 以匹配现有约定
        data_2d = data_3d[:, :, 0]         # (nSample, nCrossline)
        return data_2d.T                   # (nCrossline, nSample)
    finally:
        close_vds(handle)


def read_crossline(
    vds_path: str,
    xl_index: int,
    connection_string: str = "",
    channel: int = 0,
    lod: int = 0,
) -> np.ndarray:
    """
    读取一条 Crossline 切片。

    参数:
        vds_path: VDS 文件路径
        xl_index: Crossline 的零基索引 (0 ~ nCrosslines-1)

    返回:
        numpy 数组 shape=(nInline, nSample)
    """
    _check_openvds()

    handle, manager, layout = open_vds(vds_path, connection_string)
    try:
        n_sample = layout.getDimensionNumSamples(SAMPLE_DIM)
        n_il = layout.getDimensionNumSamples(INLINE_DIM)

        voxel_min = (0, xl_index, 0)
        voxel_max = (n_sample, xl_index + 1, n_il)

        data_3d = _read_slice(manager, layout, voxel_min, voxel_max, channel, lod)
        # data_3d shape: (nSample, 1, nInline) → squeeze → (nSample, nInline)
        data_2d = data_3d[:, 0, :]          # (nSample, nInline)
        return data_2d.T                    # (nInline, nSample)
    finally:
        close_vds(handle)


def read_timeslice(
    vds_path: str,
    sample_index: int,
    connection_string: str = "",
    channel: int = 0,
    lod: int = 0,
) -> np.ndarray:
    """
    读取一个时间切片 (沿 sample 维度)。

    参数:
        vds_path: VDS 文件路径
        sample_index: 采样点零基索引 (0 ~ nSamples-1)

    返回:
        numpy 数组 shape=(nInline, nCrossline)
    """
    _check_openvds()

    handle, manager, layout = open_vds(vds_path, connection_string)
    try:
        n_xl = layout.getDimensionNumSamples(CROSSLINE_DIM)
        n_il = layout.getDimensionNumSamples(INLINE_DIM)

        voxel_min = (sample_index, 0, 0)
        voxel_max = (sample_index + 1, n_xl, n_il)

        data_3d = _read_slice(manager, layout, voxel_min, voxel_max, channel, lod)
        # data_3d shape: (1, nCrossline, nInline) → squeeze → (nCrossline, nInline)
        data_2d = data_3d[0, :, :]          # (nCrossline, nInline)
        return data_2d.T                    # (nInline, nCrossline)
    finally:
        close_vds(handle)


# ══════════════════════════════════════════════════════════════════
# 元数据读取
# ══════════════════════════════════════════════════════════════════

def get_vds_metadata(vds_path: str, connection_string: str = "") -> dict:
    """
    读取 VDS 文件的完整元数据。

    返回:
        {
            n_inlines, n_crosslines, n_samples,
            il_range, xl_range, sample_range,
            il_names, xl_names, sample_names,
            format, channels, ...
        }
    """
    _check_openvds()

    handle, manager, layout = open_vds(vds_path, connection_string)
    try:
        # 维度大小
        n_sample = layout.getDimensionNumSamples(SAMPLE_DIM)
        n_xl = layout.getDimensionNumSamples(CROSSLINE_DIM)
        n_il = layout.getDimensionNumSamples(INLINE_DIM)

        # 轴描述符
        inline_axis = layout.getAxisDescriptor(INLINE_DIM)
        crossline_axis = layout.getAxisDescriptor(CROSSLINE_DIM)
        sample_axis = layout.getAxisDescriptor(SAMPLE_DIM)

        # Inline 号 (支持非零起始和负步长)
        il_coords = [
            inline_axis.sampleIndexToCoordinate(i)
            for i in range(n_il)
        ]
        xl_coords = [
            crossline_axis.sampleIndexToCoordinate(i)
            for i in range(n_xl)
        ]
        sample_coords = [
            sample_axis.sampleIndexToCoordinate(i)
            for i in range(n_sample)
        ]

        # 通道信息
        channel_count = layout.channelCount
        channels = []
        for c in range(channel_count):
            fmt = layout.getChannelFormat(c)
            channels.append({
                "index": c,
                "name": layout.getChannelName(c),
                "unit": layout.getChannelUnit(c),
                "format": str(fmt),
                "value_range": [
                    layout.getChannelValueRangeMin(c),
                    layout.getChannelValueRangeMax(c),
                ],
            })

        # 估算采样间隔 (从坐标差值)
        dt_sample = None
        if n_sample >= 2:
            dt_sample = sample_coords[1] - sample_coords[0]

        return {
            "n_inlines": n_il,
            "n_crosslines": n_xl,
            "n_samples": n_sample,
            "il_range": [int(il_coords[0]), int(il_coords[-1])],
            "xl_range": [int(xl_coords[0]), int(xl_coords[-1])],
            "sample_range": [float(sample_coords[0]), float(sample_coords[-1])],
            "il_coords": il_coords,
            "xl_coords": xl_coords,
            "sample_coords": sample_coords,
            "sample_interval": dt_sample,
            "channels": channels,
            "axis_names": {
                "sample": sample_axis.name,
                "crossline": crossline_axis.name,
                "inline": inline_axis.name,
            },
            "axis_units": {
                "sample": sample_axis.unit,
                "crossline": crossline_axis.unit,
                "inline": inline_axis.unit,
            },
        }
    finally:
        close_vds(handle)


# ══════════════════════════════════════════════════════════════════
# VDS 卷列表
# ══════════════════════════════════════════════════════════════════

def list_vds_volumes() -> list[dict]:
    """列出 data/vds/ 中所有 VDS 文件"""
    _ensure_vds_dir()
    volumes = []
    for p in sorted(VDS_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() in (".vds", ".vdso"):
            try:
                meta = get_vds_metadata(str(p))
                volumes.append({
                    "name": p.name,
                    "path": str(p),
                    "n_inlines": meta["n_inlines"],
                    "n_crosslines": meta["n_crosslines"],
                    "n_samples": meta["n_samples"],
                    "il_range": meta["il_range"],
                    "xl_range": meta["xl_range"],
                })
            except Exception as e:
                volumes.append({
                    "name": p.name,
                    "path": str(p),
                    "error": str(e),
                })
    return volumes


# ══════════════════════════════════════════════════════════════════
# VDS → Zarr 转换 (可选, 用于统一存储)
# ══════════════════════════════════════════════════════════════════

def vds_to_zarr(
    vds_path: str,
    zarr_name: Optional[str] = None,
    connection_string: str = "",
    channel: int = 0,
    lod: int = 0,
) -> dict:
    """
    将 VDS 文件转换为 Zarr 格式 (兼容现有流程)。

    逐 Inline 读取并写入 IL-chunked + XL-chunked 双存储 Zarr。

    参数:
        vds_path: VDS 文件路径
        zarr_name: 输出 Zarr 名称 (默认: {stem}.zarr)
        connection_string: 云端连接字符串
        channel: 数据通道
        lod: 细节级别

    返回:
        {zarr_path, zarr_name, il_range, xl_range, n_inlines, n_crosslines, n_samples, shape, size_mb}
    """
    import zarr
    import zarr.storage

    _check_openvds()

    vds_path = str(vds_path)
    if zarr_name is None:
        zarr_name = Path(vds_path).stem + ".zarr"
    if not zarr_name.endswith(".zarr"):
        zarr_name += ".zarr"

    from zarr_service import ZARR_DIR, _ensure_zarr_dir as _ensure_zarr
    _ensure_zarr()

    zarr_path = ZARR_DIR / zarr_name

    logger.info("开始 VDS -> Zarr 转换: %s -> %s", vds_path, zarr_path)

    handle, manager, layout = open_vds(vds_path, connection_string)
    try:
        n_sample = layout.getDimensionNumSamples(SAMPLE_DIM)
        n_xl = layout.getDimensionNumSamples(CROSSLINE_DIM)
        n_il = layout.getDimensionNumSamples(INLINE_DIM)

        inline_axis = layout.getAxisDescriptor(INLINE_DIM)
        crossline_axis = layout.getAxisDescriptor(CROSSLINE_DIM)

        il_coords = [int(inline_axis.sampleIndexToCoordinate(i)) for i in range(n_il)]
        xl_coords = [int(crossline_axis.sampleIndexToCoordinate(i)) for i in range(n_xl)]

        # Zarr v3 store
        store = zarr.storage.LocalStore(str(zarr_path))
        root = zarr.open_group(store=store, mode="w")

        amplitude = root.create_array(
            "amplitude",
            shape=(n_il, n_xl, n_sample),
            chunks=(1, n_xl, n_sample),
            dtype="float32",
            compressors=zarr.codecs.BloscCodec(cname="lz4", clevel=3),
        )
        amplitude_xl = root.create_array(
            "amplitude_xl",
            shape=(n_xl, n_il, n_sample),
            chunks=(1, n_il, n_sample),
            dtype="float32",
            compressors=zarr.codecs.BloscCodec(cname="lz4", clevel=3),
        )

        # 逐 IL 读取并写入
        for i in range(n_il):
            voxel_min = (0, 0, i)
            voxel_max = (n_sample, n_xl, i + 1)
            data_3d = _read_slice(manager, layout, voxel_min, voxel_max, channel, lod)
            # data_3d: (nSample, nCrossline, 1) → (nCrossline, nSample)
            il_data = data_3d[:, :, 0].T.astype(np.float32)

            amplitude[i, :, :] = il_data
            amplitude_xl[:, i, :] = il_data

            if (i + 1) % 50 == 0:
                logger.info("VDS->Zarr 写入进度: %d/%d IL", i + 1, n_il)

        # 元数据
        root.attrs["source_file"] = vds_path
        root.attrs["source_format"] = "vds"
        root.attrs["il_range"] = [il_coords[0], il_coords[-1]]
        root.attrs["xl_range"] = [xl_coords[0], xl_coords[-1]]
        root.attrs["ilines"] = il_coords
        root.attrs["xlines"] = xl_coords
        root.attrs["n_inlines"] = n_il
        root.attrs["n_crosslines"] = n_xl
        root.attrs["n_samples"] = n_sample
        root.attrs["format_version"] = "2.0"

    finally:
        close_vds(handle)

    # 统计大小
    total_size = sum(f.stat().st_size for f in zarr_path.rglob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)

    logger.info(
        "VDS->Zarr 转换完成: %s  shape=(%d,%d,%d)  size=%.1f MB",
        zarr_name, n_il, n_xl, n_sample, size_mb,
    )

    return {
        "zarr_path": str(zarr_path),
        "zarr_name": zarr_name,
        "il_range": [il_coords[0], il_coords[-1]],
        "xl_range": [xl_coords[0], xl_coords[-1]],
        "n_inlines": n_il,
        "n_crosslines": n_xl,
        "n_samples": n_sample,
        "shape": [n_il, n_xl, n_sample],
        "size_mb": round(size_mb, 1),
    }
