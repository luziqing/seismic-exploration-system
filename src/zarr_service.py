"""
Zarr seismic volume storage

Converts SGY to Zarr (.zarr) and provides:
  - O(1) inline slice reads
  - O(1) crossline slice reads (stored twice)
  - fast time-slice reads
  - LZ4 compression
  - full metadata (IL/XL ranges, sample interval, etc.)

Compatible with the Zarr v3 API.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("sam3-server")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ZARR_DIR = DATA_DIR / "zarr"

# Zarr v3 API detection
try:
    import zarr
    _ZARR_VERSION = int(zarr.__version__.split(".")[0])
except Exception:
    _ZARR_VERSION = 2

if _ZARR_VERSION < 3:
    logger.warning("Found Zarr v%d; this project needs Zarr v3+. Upgrade with: pip install 'zarr>=3.0'", _ZARR_VERSION)


def _ensure_zarr_dir():
    ZARR_DIR.mkdir(parents=True, exist_ok=True)


def sgy_to_zarr(sgy_path: str, zarr_name: Optional[str] = None,
                il_byte: int = 0, xl_byte: int = 0) -> dict:
    """
    Convert an SGY/SEG-Y file to Zarr.

    il_byte/xl_byte: custom trace-header byte offsets (0 = segyio default)
    Returns: {zarr_path, il_range, xl_range, n_samples, dt_us, shape}
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

    logger.info("Starting SGY -> Zarr conversion: %s -> %s", sgy_path, zarr_path)

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

        # Zarr v3: use LocalStore + open_group
        store = zarr.storage.LocalStore(str(zarr_path))
        root = zarr.open_group(store=store, mode="w")

        # Main store: IL × XL × Samples, one chunk per IL
        amplitude = root.create_array(
            "amplitude",
            shape=(n_il, n_xl, n_samp),
            chunks=(1, n_xl, n_samp),
            dtype="float32",
            compressors=zarr.codecs.BloscCodec(cname="lz4", clevel=3),
        )

        # Transposed copy: XL × IL × Samples, one chunk per XL
        amplitude_xl = root.create_array(
            "amplitude_xl",
            shape=(n_xl, n_il, n_samp),
            chunks=(1, n_il, n_samp),
            dtype="float32",
            compressors=zarr.codecs.BloscCodec(cname="lz4", clevel=3),
        )

        # Write IL by IL
        for i, il_val in enumerate(ilines):
            il_data = np.array(f.iline[int(il_val)], dtype=np.float32)
            amplitude[i, :, :] = il_data
            amplitude_xl[:, i, :] = il_data
            if (i + 1) % 50 == 0:
                logger.info("Zarr write progress: %d/%d IL", i + 1, n_il)

        # Metadata
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

    # File size
    total_size = sum(f.stat().st_size for f in zarr_path.rglob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)

    logger.info(
        "Zarr conversion done: %s  shape=(%d,%d,%d)  size=%.1f MB",
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
    """Read inline il_index, shape=(nXL, nSamples)"""
    import zarr
    root = zarr.open_group(str(zarr_path), mode="r")
    return np.array(root["amplitude"][il_index, :, :])


def read_crossline(zarr_path: str, xl_index: int) -> np.ndarray:
    """Read crossline xl_index, shape=(nIL, nSamples)"""
    import zarr
    root = zarr.open_group(str(zarr_path), mode="r")
    return np.array(root["amplitude_xl"][xl_index, :, :])


def read_timeslice(zarr_path: str, sample_index: int) -> np.ndarray:
    """Read time slice sample_index, shape=(nIL, nXL)"""
    import zarr
    root = zarr.open_group(str(zarr_path), mode="r")
    return np.array(root["amplitude"][:, :, sample_index])


def get_zarr_metadata(zarr_path: str) -> dict:
    """Read Zarr metadata"""
    import zarr
    root = zarr.open_group(str(zarr_path), mode="r")
    return dict(root.attrs)


def list_zarr_volumes() -> list[dict]:
    """List all Zarr volumes in data/zarr/"""
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
                volumes.append({"name": p.name, "path": str(p), "error": "Cannot read metadata"})
    return volumes


def find_zarr_for_sgy(sgy_filename: str) -> Optional[str]:
    """Find the Zarr path for an SGY file"""
    _ensure_zarr_dir()
    zarr_name = Path(sgy_filename).stem + ".zarr"
    zarr_path = ZARR_DIR / zarr_name
    if zarr_path.exists():
        return str(zarr_path)
    return None
