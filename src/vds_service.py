"""
OpenVDS seismic volume reader service

Supports:
  - local .vds / .vdso files
  - cloud VDS (S3 / Azure Blob)
  - fast inline / crossline / time-slice reads
  - VDS -> Zarr conversion

OpenVDS docs: https://osdu.pages.opengroup.org/platform/domain-data-mgmt-services/seismic/open-vds/getting-started.html

Requires: pip install openvds  (needs Python 3.7–3.11)
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("sam3-server")

# ── Optional import ───────────────────────────────────────────
try:
    import openvds
    _HAS_OPENVDS = True
except ImportError:
    _HAS_OPENVDS = False
    logger.warning("openvds is not installed; VDS features are unavailable. Install with: pip install openvds")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VDS_DIR = DATA_DIR / "vds"

# VDS dimension order: sample=0, crossline=1, inline=2
SAMPLE_DIM, CROSSLINE_DIM, INLINE_DIM = 0, 1, 2


def is_available() -> bool:
    """Check whether openvds is available"""
    return _HAS_OPENVDS


def _ensure_vds_dir():
    VDS_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# Opening VDS files & context management
# ══════════════════════════════════════════════════════════════════

def open_vds(vds_path: str, connection_string: str = "") -> tuple:
    """
    Open a VDS file; returns (handle, access_manager, layout).

    Args:
        vds_path: local path or cloud URL (s3://... or azure://...)
        connection_string: cloud connection string (empty for local files)
            S3: "AccessKeyId=xxx;SecretKey=xxx;Region=us-east-1"
            Azure: "DefaultEndpointsProtocol=https;AccountName=xxx;AccountKey=xxx;EndpointSuffix=core.windows.net"

    Returns:
        (handle, manager, layout) tuple
    """
    _check_openvds()

    vds_path = str(vds_path)
    logger.info("Opening VDS: %s", vds_path)

    try:
        handle = openvds.open(vds_path, connection_string)
    except RuntimeError as e:
        raise RuntimeError(f"Cannot open VDS file: {vds_path}\n{e}") from e

    manager = openvds.getAccessManager(handle)
    layout = manager.volumeDataLayout

    return handle, manager, layout


def close_vds(handle) -> None:
    """Close the VDS handle"""
    if handle is not None:
        handle.close()


def _check_openvds():
    if not _HAS_OPENVDS:
        raise ImportError(
            "openvds is not installed, so VDS features are unavailable. "
            "Run: pip install openvds"
        )


# ══════════════════════════════════════════════════════════════════
# Slice reading
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
    Read one data slice (low level: async request -> wait -> return numpy array).

    voxel_min / voxel_max: 3-D tuples (sample, crossline, inline)
    """
    # Let OpenVDS allocate the buffer (blocks until the data is ready)
    request = manager.requestVolumeSubset(
        dimensionsND=openvds.DimensionsND.Dimensions_012,
        min=voxel_min,
        max=voxel_max,
        lod=lod,
        channel=channel,
    )
    # request.data returns a 1-D numpy array that needs a reshape
    ns = voxel_max[0] - voxel_min[0]
    nxl = voxel_max[1] - voxel_min[1]
    nil = voxel_max[2] - voxel_min[2]

    raw = np.asarray(request.data, dtype=np.float32)
    # VDS data layout: [sample, crossline, inline]
    return raw.reshape((ns, nxl, nil))


def read_inline(
    vds_path: str,
    il_index: int,
    connection_string: str = "",
    channel: int = 0,
    lod: int = 0,
) -> np.ndarray:
    """
    Read one inline slice.

    Args:
        vds_path: VDS file path
        il_index: zero-based inline index (0 ~ nInlines-1)
        connection_string: cloud connection string
        channel: data channel (default 0)
        lod: level of detail (default 0 = full resolution)

    Returns:
        numpy array shape=(nCrossline, nSample), same as the Zarr service
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
        # Transpose to (nCrossline, nSample) to match the existing convention
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
    Read one crossline slice.

    Args:
        vds_path: VDS file path
        xl_index: zero-based crossline index (0 ~ nCrosslines-1)

    Returns:
        numpy array shape=(nInline, nSample)
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
    Read one time slice (along the sample axis).

    Args:
        vds_path: VDS file path
        sample_index: zero-based sample index (0 ~ nSamples-1)

    Returns:
        numpy array shape=(nInline, nCrossline)
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
# Metadata reading
# ══════════════════════════════════════════════════════════════════

def get_vds_metadata(vds_path: str, connection_string: str = "") -> dict:
    """
    Read the full metadata of a VDS file.

    Returns:
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
        # Dimension sizes
        n_sample = layout.getDimensionNumSamples(SAMPLE_DIM)
        n_xl = layout.getDimensionNumSamples(CROSSLINE_DIM)
        n_il = layout.getDimensionNumSamples(INLINE_DIM)

        # Axis descriptors
        inline_axis = layout.getAxisDescriptor(INLINE_DIM)
        crossline_axis = layout.getAxisDescriptor(CROSSLINE_DIM)
        sample_axis = layout.getAxisDescriptor(SAMPLE_DIM)

        # Inline numbers (non-zero start and negative step supported)
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

        # Channel info
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

        # Estimate the sample interval (from coordinate differences)
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
# VDS volume list
# ══════════════════════════════════════════════════════════════════

def list_vds_volumes() -> list[dict]:
    """List all VDS files in data/vds/"""
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
# VDS -> Zarr conversion (optional, for uniform storage)
# ══════════════════════════════════════════════════════════════════

def vds_to_zarr(
    vds_path: str,
    zarr_name: Optional[str] = None,
    connection_string: str = "",
    channel: int = 0,
    lod: int = 0,
) -> dict:
    """
    Convert a VDS file to Zarr (compatible with the existing flow).

    Reads inline by inline and writes a dual-store Zarr (IL-chunked + XL-chunked).

    Args:
        vds_path: VDS file path
        zarr_name: output Zarr name (default: {stem}.zarr)
        connection_string: cloud connection string
        channel: data channel
        lod: level of detail

    Returns:
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

    logger.info("Starting VDS -> Zarr conversion: %s -> %s", vds_path, zarr_path)

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

        # Read and write IL by IL
        for i in range(n_il):
            voxel_min = (0, 0, i)
            voxel_max = (n_sample, n_xl, i + 1)
            data_3d = _read_slice(manager, layout, voxel_min, voxel_max, channel, lod)
            # data_3d: (nSample, nCrossline, 1) → (nCrossline, nSample)
            il_data = data_3d[:, :, 0].T.astype(np.float32)

            amplitude[i, :, :] = il_data
            amplitude_xl[:, i, :] = il_data

            if (i + 1) % 50 == 0:
                logger.info("VDS->Zarr write progress: %d/%d IL", i + 1, n_il)

        # Metadata
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

    # Size
    total_size = sum(f.stat().st_size for f in zarr_path.rglob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)

    logger.info(
        "VDS->Zarr conversion done: %s  shape=(%d,%d,%d)  size=%.1f MB",
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
