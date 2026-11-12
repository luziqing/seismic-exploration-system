"""scripts/measure_lowfreq.py: AUC arithmetic and the visibility metric on constructed volumes."""
import itertools
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import measure_lowfreq as M  # noqa: E402


def brute_auc(pos, neg):
    s = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p, n in itertools.product(pos, neg))
    return s / (len(pos) * len(neg))


@pytest.mark.parametrize("seed", range(5))
def test_auc_matches_pairwise_definition_with_ties(seed):
    rng = np.random.default_rng(seed)
    pos = rng.integers(0, 6, 17).astype(float)   # small integer range: many ties
    neg = rng.integers(0, 6, 23).astype(float)
    assert M.auc(pos, neg) == pytest.approx(brute_auc(pos, neg))


def test_auc_extremes():
    assert M.auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert M.auc(np.array([1.0, 2.0]), np.array([3.0, 4.0])) == 0.0
    assert M.auc(np.array([1.0, 1.0]), np.array([1.0])) == 0.5


def _volume(target_amp, horizon_amp=3.0):
    """(nIL, nXL, nS) with a target block of given amplitude in samples 20..29 of traces [2:5, 2:5]."""
    vol = np.full((8, 8, 40), 0.1, dtype=np.float32)
    target = np.zeros(vol.shape, dtype=bool)
    target[2:5, 2:5, 20:30] = True
    vol[target] = target_amp
    horizon = np.zeros(vol.shape, dtype=bool)
    horizon[6:, :, 25] = True                     # a bright horizon crossing the window in inlines 6-7
    vol[horizon] = horizon_amp
    return vol, target, horizon


def test_visibility_separates_a_strong_target_and_reports_counts():
    vol, target, horizon = _volume(0.5)
    r = M.visibility(vol, target, horizon)
    assert r["window_samples"] == [20, 29] and r["n_target_traces"] == 9
    a, n = r["all_background"], r["background_without_horizon"]
    assert a["n_traces"] == 64 - 9 and n["n_traces"] == 64 - 9 - 16
    assert n["auc"] == 1.0 and n["tbr_db"] == pytest.approx(20 * np.log10(0.5 / 0.1))
    assert a["auc"] < n["auc"]                     # bright horizon traces in the background lower the AUC


def test_visibility_is_neutral_without_a_target():
    vol, target, horizon = _volume(0.1)            # "target" traces identical to background
    n = M.visibility(vol, target, horizon)["background_without_horizon"]
    assert n["auc"] == 0.5 and n["tbr_db"] == pytest.approx(0.0, abs=1e-9)


def test_control_does_not_see_a_target_that_is_not_there():
    vol, target, _ = _volume(0.5, horizon_amp=0.1)   # homogeneous background apart from the real target
    c = M.control(vol, target)
    assert c["n_traces"] == 9 and c["auc"] == 0.5


def test_condition_volume_matches_slice_filter():
    rng = np.random.default_rng(0)
    vol = rng.standard_normal((3, 4, 64)).astype(np.float32)
    out = M.condition_volume(vol, 2000)
    np.testing.assert_allclose(out[1], M.lowfreq_service.condition_slice(vol[1].T, dt_us=2000).T, atol=1e-6)
