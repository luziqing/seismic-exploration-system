"""scripts/measure_refine.py with a stub segmenter (no GPU): click rule, report structure, determinism."""
import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
_spec = importlib.util.spec_from_file_location("measure_refine", ROOT / "scripts" / "measure_refine.py")
mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mr)

NPY = ROOT / "data" / "npy"


def test_click_is_inside_the_truth():
    t = np.zeros((40, 20), bool)
    t[10:20, 5:15] = True
    c = mr.click_for(t)
    assert t[int(c["row"]), int(c["col"])] and c["label"] == 1


def test_run_case_with_exact_segmenter_keeps_round_one():
    rng = np.random.default_rng(0)
    raw = rng.normal(0, 0.01, (64, 32)).astype(np.float32)
    truth = np.zeros_like(raw, bool)
    truth[20:30, 8:24] = True
    raw[20:30, 8:24] += np.sin(np.arange(10) * 1.2)[:, None]
    res = mr.run_case(raw, raw, truth, lambda v, s: ((lambda p, l: truth), lambda: None))
    assert res["iou_round1"] == 1.0 and res["best_round"] == 1
    s = mr.summarise([res, res])
    assert s["n"] == 2 and s["mean_iou_round1"] == 1.0 and s["unchanged"] == 2


def test_measure_on_demo_volumes_is_deterministic_with_stub():
    if not (NPY / "synthetic_deep_v1" / "amplitude.npy").exists():
        import pytest
        pytest.skip("demo volumes not generated")

    def factory(view, grid_shape):
        thr = np.abs(view) > np.percentile(np.abs(view), 90)          # deterministic, view-dependent stub
        return (lambda p, l: thr), (lambda: None)

    a = mr.report(mr.measure(NPY, factory))
    b = mr.report(mr.measure(NPY, factory))
    assert a == b and "Cases where the kept round" in a
