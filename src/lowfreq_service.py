"""
Low-Frequency Conditioning Service for Seismic Slices.

Part of SamForGeophysics (Kiroween 2026 - Frankenstein category).
Applies spectral weighting along the time/depth axis of a 2D seismic slice
to emphasize weak, low-frequency deep reflectors before SAM prompting.

ELIGIBILITY & HONESTY NOTICE:
This is an image-conditioning heuristic, NOT a physical inversion.
All constants are declared heuristic defaults rather than tuned benchmarks.
The underlying raw volume stored on disk is NEVER modified.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Tuple

import numpy as np

logger = logging.getLogger("sam3-server")

# ── Declared Filter & Conditioning Constants ───────────────────────────────
# These parameters are heuristic defaults tailored for typical seismic sampling
# (e.g. dt=2ms -> Nyquist=250Hz; deep targets ~10Hz vs shallow horizons ~32Hz).
DEFAULT_DT_US: int = 2000             # Default sample interval: 2000 us (2.0 ms)
DEFAULT_F_PASS_HZ: float = 14.0        # Passband upper edge: <= 14 Hz preserved at 1.0
DEFAULT_F_STOP_HZ: float = 30.0        # Stopband lower edge: >= 30 Hz attenuated
DEFAULT_ATTENUATION_FLOOR: float = 0.05# Residual energy floor in stopband (avoids zeroing)
DEFAULT_NORMALIZATION_SCALE: float = 1.0 # Declared output gain constant


def compute_spectral_weights(
    n_samples: int,
    dt_us: int = DEFAULT_DT_US,
    f_pass_hz: float = DEFAULT_F_PASS_HZ,
    f_stop_hz: float = DEFAULT_F_STOP_HZ,
    attenuation_floor: float = DEFAULT_ATTENUATION_FLOOR,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute 1D cosine-tapered frequency weighting window.

    Parameters:
        n_samples: Length of the time series along the time axis.
        dt_us: Sampling interval in microseconds.
        f_pass_hz: Frequencies <= f_pass_hz receive full weight (1.0).
        f_stop_hz: Frequencies >= f_stop_hz receive attenuation_floor.
        attenuation_floor: Minimum transmission gain in the stopband.

    Returns:
        (freqs, weights): 1D array of frequency bins and corresponding weights.
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be positive, got {n_samples}")
    if dt_us <= 0:
        raise ValueError(f"dt_us must be positive, got {dt_us}")
    if not (0.0 <= f_pass_hz < f_stop_hz):
        raise ValueError(f"Invalid filter bands: 0 <= {f_pass_hz} < {f_stop_hz} required")

    dt_s = dt_us * 1e-6
    freqs = np.fft.rfftfreq(n_samples, d=dt_s)

    # Cosine taper between f_pass and f_stop
    weights = np.full_like(freqs, fill_value=attenuation_floor, dtype=np.float64)

    # Passband: full transmission
    pass_mask = freqs <= f_pass_hz
    weights[pass_mask] = 1.0

    # Transition band: cosine roll-off from 1.0 down to attenuation_floor
    transition_mask = (freqs > f_pass_hz) & (freqs < f_stop_hz)
    if np.any(transition_mask):
        norm_freq = (freqs[transition_mask] - f_pass_hz) / (f_stop_hz - f_pass_hz)
        cosine_roll = 0.5 * (1.0 + np.cos(np.pi * norm_freq))
        weights[transition_mask] = attenuation_floor + (1.0 - attenuation_floor) * cosine_roll

    return freqs, weights


def condition_slice(
    slice_2d: np.ndarray,
    dt_us: int = DEFAULT_DT_US,
    f_pass_hz: float = DEFAULT_F_PASS_HZ,
    f_stop_hz: float = DEFAULT_F_STOP_HZ,
    attenuation_floor: float = DEFAULT_ATTENUATION_FLOOR,
    normalization_scale: float = DEFAULT_NORMALIZATION_SCALE,
    time_axis: int = 0,
) -> np.ndarray:
    """
    Apply low-frequency spectral conditioning to a 2D seismic slice.

    Operates purely in memory. The input array is never modified in-place.

    Parameters:
        slice_2d: 2D array of shape (n_samples, n_traces) if time_axis=0,
                  or (n_traces, n_samples) if time_axis=1.
        dt_us: Sampling interval in microseconds (default 2000 us).
        f_pass_hz: Low-pass passband cutoff frequency in Hz (default 14.0 Hz).
        f_stop_hz: Low-pass stopband cutoff frequency in Hz (default 30.0 Hz).
        attenuation_floor: Minimum high-frequency transmission (default 0.05).
        normalization_scale: Multiplicative gain factor on output (default 1.0).
        time_axis: Axis index representing the time / sample dimension (default 0).

    Returns:
        Conditioned 2D array as np.float32 with identical shape to slice_2d.
    """
    if not isinstance(slice_2d, np.ndarray):
        slice_2d = np.asarray(slice_2d)

    if slice_2d.ndim != 2:
        raise ValueError(f"condition_slice expects a 2D array, got shape {slice_2d.shape}")

    if not np.all(np.isfinite(slice_2d)):
        raise ValueError("Input slice contains NaN or infinite values")

    if time_axis not in (0, 1):
        raise ValueError(f"time_axis must be 0 or 1, got {time_axis}")

    n_samples = slice_2d.shape[time_axis]
    if n_samples < 4:
        # Trivial slice or insufficient samples along time axis, return copy as float32
        return slice_2d.astype(np.float32, copy=True)

    _, weights = compute_spectral_weights(
        n_samples=n_samples,
        dt_us=dt_us,
        f_pass_hz=f_pass_hz,
        f_stop_hz=f_stop_hz,
        attenuation_floor=attenuation_floor,
    )

    # 1D Real FFT along the time axis
    spec = np.fft.rfft(slice_2d, axis=time_axis)

    # Reshape weights for broadcasting
    broadcast_shape = [1, 1]
    broadcast_shape[time_axis] = len(weights)
    weights_nd = weights.reshape(broadcast_shape)

    spec_filtered = spec * weights_nd

    # Inverse Real FFT
    filtered = np.fft.irfft(spec_filtered, n=n_samples, axis=time_axis)

    if normalization_scale != 1.0:
        filtered *= normalization_scale

    return filtered.astype(np.float32, copy=False)


SLICE_MODES = ("raw", "lowfreq")
# Timeslice conditioning filters every trace of the volume. Above this size we refuse
# rather than load a large volume into memory per request (demo volumes are ~2.4 MB).
MAX_TIMESLICE_VOLUME_BYTES: int = 256 * 1024 * 1024


@lru_cache(maxsize=2)
def _conditioned_volume(amplitude_path: str, mtime_ns: int, dt_us: int) -> np.ndarray:
    """Low-frequency conditioned copy of a whole volume, cached per file version and dt."""
    vol = np.load(amplitude_path, mmap_mode="r")
    if vol.ndim != 3:
        raise ValueError(f"Expected a 3-D volume, got shape {vol.shape}")
    nbytes = int(np.prod(vol.shape)) * 4
    if nbytes > MAX_TIMESLICE_VOLUME_BYTES:
        raise ValueError(
            f"Volume is {nbytes / 2**20:.0f} MB; low-frequency timeslices are limited to "
            f"{MAX_TIMESLICE_VOLUME_BYTES / 2**20:.0f} MB volumes")
    n_il, n_xl, n_s = vol.shape
    traces = np.asarray(vol, dtype=np.float32).reshape(n_il * n_xl, n_s)
    out = condition_slice(traces, dt_us=dt_us, time_axis=1).reshape(n_il, n_xl, n_s)
    out.setflags(write=False)
    return out


def lowfreq_timeslice(amplitude_path: str, sample_index: int, dt_us: int = DEFAULT_DT_US) -> np.ndarray:
    """
    Timeslice `sample_index` of the low-frequency conditioned volume, shape (nIL, nXL).

    A timeslice has no time axis of its own, so every trace is filtered along time first
    and the sample is taken afterwards. The file on disk is only read.
    """
    p = Path(amplitude_path)
    vol = _conditioned_volume(str(p), p.stat().st_mtime_ns, int(dt_us))
    if not 0 <= sample_index < vol.shape[2]:
        raise IndexError(f"TimeSlice index {sample_index} out of range [0, {vol.shape[2] - 1}]")
    return np.array(vol[:, :, sample_index], dtype=np.float32)


def get_filter_metadata() -> dict:
    """Return dictionary of default filter configuration constants."""
    return {
        "default_dt_us": DEFAULT_DT_US,
        "default_f_pass_hz": DEFAULT_F_PASS_HZ,
        "default_f_stop_hz": DEFAULT_F_STOP_HZ,
        "default_attenuation_floor": DEFAULT_ATTENUATION_FLOOR,
        "default_normalization_scale": DEFAULT_NORMALIZATION_SCALE,
        "description": "Cosine-tapered low-frequency spectral emphasis heuristic",
    }


if __name__ == "__main__":
    # Standalone verification script for lowfreq_service
    print("Running standalone verification for lowfreq_service...")

    n_t, n_x = 256, 48
    dt_us = 2000
    t = np.arange(n_t) * (dt_us * 1e-6)

    # Create composite signal: 10 Hz (target) + 32 Hz (shallow horizon)
    sig_10hz = 0.5 * np.sin(2 * np.pi * 10.0 * t)
    sig_32hz = 1.0 * np.sin(2 * np.pi * 32.0 * t)
    trace = sig_10hz + sig_32hz

    slice_in = np.tile(trace[:, None], (1, n_x)).astype(np.float32)
    slice_in_copy = slice_in.copy()

    # Apply conditioning
    conditioned = condition_slice(slice_in, dt_us=dt_us)

    # 1. Shape preservation
    assert conditioned.shape == slice_in.shape, f"Shape mismatch: {conditioned.shape} vs {slice_in.shape}"
    assert conditioned.dtype == np.float32, f"Dtype mismatch: {conditioned.dtype}"

    # 2. Immutability: input must not be modified
    assert np.array_equal(slice_in, slice_in_copy), "Input slice was modified in-place!"

    # 3. Spectral verification: 32 Hz should be attenuated, 10 Hz should be preserved
    spec_in = np.abs(np.fft.rfft(slice_in[:, 0]))
    spec_out = np.abs(np.fft.rfft(conditioned[:, 0]))
    freqs = np.fft.rfftfreq(n_t, d=dt_us * 1e-6)

    idx_10 = np.argmin(np.abs(freqs - 10.0))
    idx_32 = np.argmin(np.abs(freqs - 32.0))

    ratio_10 = spec_out[idx_10] / spec_in[idx_10]
    ratio_32 = spec_out[idx_32] / spec_in[idx_32]

    print(f"10 Hz retention ratio: {ratio_10:.4f} (expected ~1.00)")
    print(f"32 Hz retention ratio: {ratio_32:.4f} (expected <= {DEFAULT_ATTENUATION_FLOOR + 0.02:.2f})")

    assert ratio_10 > 0.95, f"10 Hz signal was overly attenuated: {ratio_10}"
    assert ratio_32 < 0.10, f"32 Hz signal was not sufficiently attenuated: {ratio_32}"

    # 4. Transposed axis test (time_axis = 1)
    slice_trans = slice_in.T.copy()
    cond_trans = condition_slice(slice_trans, dt_us=dt_us, time_axis=1)
    assert cond_trans.shape == slice_trans.shape
    assert np.allclose(cond_trans.T, conditioned, atol=1e-5)

    print("OK: lowfreq_service standalone verification passed!")
