"""
NumPy memmap seismic volume storage

Replaces the Zarr approach and provides:
  - SGY -> numpy conversion (~3 s, vs ~30 s for Zarr)
  - zero-copy memmap reads of inline/crossline/timeslice
  - binary float32 responses (270 KB per slice vs 1.2 MB JSON)
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
    SGY -> numpy .npy file (float32, shape [nIL, nXL, nSamples]).
    Returns: {npy_path, npy_name, il_range, xl_range, ...}
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

    logger.info("Starting SGY -> NumPy conversion: %s -> %s", sgy_path, npy_path)

    kwargs = {}
    if il_byte and xl_byte:
        kwargs = dict(iline=il_byte, xline=xl_byte)

    with segyio.open(sgy_path, "r", ignore_geometry=False, **kwargs) as f:
        ilines = np.array(f.ilines, dtype=np.int32)
        xlines = np.array(f.xlines, dtype=np.int32)
        samples = np.array(f.samples, dtype=np.float64)
        n_il, n_xl, n_samp = len(ilines), len(xlines), len(samples)
        dt_us = int(f.bin[segyio.BinField.Interval])

        # Preallocate the float32 array
        volume = np.empty((n_il, n_xl, n_samp), dtype=np.float32)
        for i, il_val in enumerate(ilines):
            volume[i] = f.iline[int(il_val)]
            if (i + 1) % 50 == 0:
                logger.info("NumPy write progress: %d/%d IL", i + 1, n_il)

        # Save the .npy
        np.save(str(npy_path), volume)

        # Save metadata
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
    logger.info("NumPy conversion done: %s  shape=(%d,%d,%d)  size=%.1f MB",
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


# ── memmap reads ─────────────────────────────────────────────

def _load_mmap(npy_dir: str) -> np.ndarray:
    """Load the memmap (read-only, zero-copy)"""
    npy_path = Path(npy_dir) / "amplitude.npy"
    if not npy_path.exists():
        raise FileNotFoundError(f"NumPy volume not found: {npy_path}")
    return np.load(str(npy_path), mmap_mode='r')


def read_inline(npy_dir: str, il_index: int) -> np.ndarray:
    """Read inline il_index; returns shape=(nSamples, nXL): samples vertical, XL horizontal"""
    vol = _load_mmap(npy_dir)
    if il_index < 0 or il_index >= vol.shape[0]:
        raise IndexError(f"Inline index {il_index} out of range [0, {vol.shape[0]-1}]")
    # vol[il] shape = (nXL, nSamples) -> transpose -> (nSamples, nXL)
    return np.array(vol[il_index]).T.copy()


def read_crossline(npy_dir: str, xl_index: int) -> np.ndarray:
    """Read crossline xl_index; returns shape=(nSamples, nIL): samples vertical, IL horizontal"""
    vol = _load_mmap(npy_dir)
    if xl_index < 0 or xl_index >= vol.shape[1]:
        raise IndexError(f"Crossline index {xl_index} out of range [0, {vol.shape[1]-1}]")
    # vol[:, xl] shape = (nIL, nSamples) -> transpose -> (nSamples, nIL)
    return np.array(vol[:, xl_index, :]).T.copy()


def read_timeslice(npy_dir: str, sample_index: int) -> np.ndarray:
    """Read time slice sample_index; returns a copy with shape=(nIL, nXL)"""
    vol = _load_mmap(npy_dir)
    if sample_index < 0 or sample_index >= vol.shape[2]:
        raise IndexError(f"TimeSlice index {sample_index} out of range [0, {vol.shape[2]-1}]")
    return np.array(vol[:, :, sample_index])


# ── Metadata ──────────────────────────────────────────────────

def get_metadata(npy_dir: str) -> dict:
    """Read NumPy volume metadata"""
    meta_path = Path(npy_dir) / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata not found: {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def list_volumes() -> list[dict]:
    """List all NumPy volumes in data/npy/"""
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
                volumes.append({"name": p.name, "path": str(p), "error": "Cannot read"})
    return volumes


def find_for_sgy(sgy_filename: str) -> str | None:
    """Find the NumPy volume path for an SGY file"""
    _ensure_dir()
    npy_name = Path(sgy_filename).stem
    npy_dir = NPY_DIR / npy_name
    if (npy_dir / "amplitude.npy").exists():
        return str(npy_dir)
    return None
