"""
Tests for lowfreq_service: low-frequency spectral conditioning on 2D seismic slices.
"""

import sys
from pathlib import Path

# Ensure src/ is on the import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import pytest

from lowfreq_service import (
    DEFAULT_DT_US,
    DEFAULT_F_PASS_HZ,
    DEFAULT_F_STOP_HZ,
    compute_spectral_weights,
    condition_slice,
    get_filter_metadata,
)


class TestLowFreqService:
    def test_filter_metadata(self):
        meta = get_filter_metadata()
        assert "default_dt_us" in meta
        assert "default_f_pass_hz" in meta
        assert "default_f_stop_hz" in meta
        assert meta["default_f_pass_hz"] < meta["default_f_stop_hz"]

    def test_spectral_weights_shape_and_range(self):
        n_samples = 256
        freqs, weights = compute_spectral_weights(n_samples, dt_us=2000)
        assert len(freqs) == n_samples // 2 + 1
        assert len(weights) == len(freqs)
        # Low frequency should be 1.0
        assert weights[0] == 1.0
        # Stopband should be at floor
        assert weights[-1] <= 0.05 + 1e-6
        # All weights within [floor, 1.0]
        assert np.all(weights >= 0.05 - 1e-6)
        assert np.all(weights <= 1.0 + 1e-6)

    def test_spectral_weights_invalid_args(self):
        with pytest.raises(ValueError):
            compute_spectral_weights(0)
        with pytest.raises(ValueError):
            compute_spectral_weights(100, dt_us=-10)
        with pytest.raises(ValueError):
            compute_spectral_weights(100, f_pass_hz=50.0, f_stop_hz=30.0)

    def test_condition_slice_shape_preservation(self):
        rng = np.random.default_rng(42)
        slice_2d = rng.standard_normal((256, 48)).astype(np.float32)
        conditioned = condition_slice(slice_2d, dt_us=2000)

        assert conditioned.shape == (256, 48)
        assert conditioned.dtype == np.float32
        assert np.all(np.isfinite(conditioned))

    def test_condition_slice_immutability(self):
        slice_2d = np.ones((128, 32), dtype=np.float32)
        slice_copy = slice_2d.copy()
        _ = condition_slice(slice_2d)

        assert np.array_equal(slice_2d, slice_copy)

    def test_condition_slice_spectral_filtering(self):
        n_t, n_x = 256, 16
        dt_us = 2000
        t = np.arange(n_t) * (dt_us * 1e-6)

        # 10 Hz target + 32 Hz shallow
        sig_10 = np.sin(2 * np.pi * 10.0 * t)[:, None]
        sig_32 = np.sin(2 * np.pi * 32.0 * t)[:, None]
        raw = np.tile(sig_10 + sig_32, (1, n_x)).astype(np.float32)

        out = condition_slice(raw, dt_us=dt_us)

        freqs = np.fft.rfftfreq(n_t, d=dt_us * 1e-6)
        i_10 = np.argmin(np.abs(freqs - 10.0))
        i_32 = np.argmin(np.abs(freqs - 32.0))

        spec_raw = np.abs(np.fft.rfft(raw[:, 0]))
        spec_out = np.abs(np.fft.rfft(out[:, 0]))

        # 10 Hz preserved (ratio ~ 1.0)
        assert (spec_out[i_10] / spec_raw[i_10]) > 0.95
        # 32 Hz attenuated (ratio <= 0.10)
        assert (spec_out[i_32] / spec_raw[i_32]) < 0.10

    def test_condition_slice_transposed_axis(self):
        rng = np.random.default_rng(123)
        slice_2d = rng.standard_normal((32, 256)).astype(np.float32)
        out = condition_slice(slice_2d, dt_us=2000, time_axis=1)

        assert out.shape == (32, 256)
        assert out.dtype == np.float32

    def test_condition_slice_validation_errors(self):
        # 1D array
        with pytest.raises(ValueError):
            condition_slice(np.ones(10))
        # 3D array
        with pytest.raises(ValueError):
            condition_slice(np.ones((10, 10, 10)))
        # Non-finite values
        with pytest.raises(ValueError):
            bad_slice = np.ones((10, 10), dtype=np.float32)
            bad_slice[0, 0] = np.nan
            condition_slice(bad_slice)
        # Invalid time_axis
        with pytest.raises(ValueError):
            condition_slice(np.ones((10, 10)), time_axis=2)
