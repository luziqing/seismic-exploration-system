"""refine_service: the loop with deterministic stub segmenters, no GPU (spec qc-refine-loop, Requirement 3)."""
import inspect
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import refine_service as rs  # noqa: E402

ROWS, COLS, DT = 128, 40, 0.002
C0, W = 10, 14


def ricker(f, center):
    t = (np.arange(ROWS) - center) * DT
    a = (np.pi * f * t) ** 2
    return (1.0 - 2.0 * a) * np.exp(-a)


def _scene(amp=1.0):
    rng = np.random.default_rng(0)
    s = rng.normal(0.0, 0.05, (ROWS, COLS))
    s[:, C0:C0 + W] += amp * ricker(10.0, 80)[:, None]
    exact = np.zeros((ROWS, COLS), bool)
    env = np.abs(__import__("scipy.signal", fromlist=["hilbert"]).hilbert(amp * ricker(10.0, 80)))
    rows = np.flatnonzero(env >= env.max() * 0.5)
    exact[rows[0]:rows[-1] + 1, C0:C0 + W] = True
    return s.astype(np.float32), exact


USER = [{"row": 80, "col": C0 + W // 2, "label": 1}]


class Recorder:
    """Stub segmenter: returns masks from a list, one per call, and records the prompts it was given."""
    def __init__(self, masks):
        self.masks, self.calls = list(masks), []

    def __call__(self, points, labels):
        self.calls.append((list(points), list(labels)))
        return self.masks[min(len(self.calls), len(self.masks)) - 1]


def test_leaky_first_round_gets_a_negative_correction_inside_the_leak():
    s, exact = _scene()
    leaky = exact.copy()
    leaky[96:116, C0:C0 + W] = True                     # mask runs 20 rows down into background
    seg = Recorder([leaky, exact, exact])
    out = rs.run(s, USER, seg)
    corr = out["rounds"][0]["correction"]
    assert corr["label"] == 0 and corr["kind"] == "leak" and corr["row"] >= 96
    assert seg.calls[1][1] == [1, 0]                    # round 2 = user point + negative correction
    assert out["rounds"][1]["prompts"][-1]["source"] == "correction"
    assert out["best_round"] == 2 and out["rounds"][1]["score"] > out["rounds"][0]["score"]


def test_partial_first_round_gets_a_positive_correction_in_the_missed_part():
    s, exact = _scene()
    partial = exact.copy()
    partial[:, C0 + 7:] = False                         # right half of the target missing
    out = rs.run(s, USER, Recorder([partial, exact]))
    corr = out["rounds"][0]["correction"]
    assert corr["label"] == 1 and corr["kind"] == "miss" and corr["col"] >= C0 + 7


def test_round_limit_and_one_segment_call_per_round():
    s, exact = _scene()
    masks = []
    for k in (40, 25, 10):                              # each round a little better, never perfect
        m = exact.copy()
        m[96:96 + k, C0:C0 + W] = True
        masks.append(m)
    seg = Recorder(masks)
    out = rs.run(s, USER, seg)
    assert len(out["rounds"]) == rs.MAX_ROUNDS == len(seg.calls)
    assert out["stop_reason"] == "max_rounds" and out["best_round"] == 3


def test_no_gain_stops_and_keeps_the_earlier_best_round():
    s, exact = _scene()
    leaky, worse = exact.copy(), exact.copy()
    leaky[96:106, C0:C0 + W] = True                     # fixable leak in round 1
    worse[96:126, C0:C0 + W] = True                     # round 2 leaks even more
    out = rs.run(s, USER, Recorder([leaky, worse]))
    assert out["stop_reason"] == "no_gain" and out["best_round"] == 1 and len(out["rounds"]) == 2
    assert out["rounds"][1]["delta"] < 0


def test_a_later_round_must_beat_the_best_by_min_gain():
    s, exact = _scene()
    leaky = exact.copy()
    leaky[96:106, C0:C0 + W] = True
    out = rs.run(s, USER, Recorder([leaky, leaky]))      # identical second round: gain 0 < MIN_GAIN
    assert out["best_round"] == 1 and out["stop_reason"] == "no_gain"


def test_nothing_to_fix_stops_after_round_one():
    s, exact = _scene()
    seg = Recorder([exact])
    out = rs.run(s, USER, seg)
    assert out["stop_reason"] == "nothing_to_fix" and len(seg.calls) == 1
    assert out["rounds"][0]["correction"] is None and out["best_round"] == 1


def test_empty_mask_stops():
    s, _ = _scene()
    out = rs.run(s, USER, Recorder([np.zeros((ROWS, COLS), bool)]))
    assert out["stop_reason"] == "empty_mask" and out["rounds"][0]["score"] == 0.0


def test_unreliable_qc_stops_without_corrections():
    s, exact = _scene(amp=0.04)                         # target below the noise level
    seg = Recorder([exact, exact])
    out = rs.run(s, USER, seg)
    assert out["stop_reason"] == "qc_unreliable" and len(seg.calls) == 1
    assert out["rounds"][0]["metrics"]["reliable"] is False and "too weak" in out["stop_message"]


def test_qc_reference_is_the_user_click_not_the_corrections():
    s, exact = _scene()
    partial = exact.copy()
    partial[:, C0 + 7:] = False
    out = rs.run(s, USER, Recorder([partial, exact]))
    ref1 = out["rounds"][0]["metrics"]["reference_envelope"]
    ref2 = out["rounds"][1]["metrics"]["reference_envelope"]
    assert ref1 == ref2                                 # a positive correction does not move the reference


def test_run_never_receives_truth_and_attach_truth_reports_it():
    assert "truth" not in inspect.signature(rs.run).parameters
    s, exact = _scene()
    leaky = exact.copy()
    leaky[96:116, C0:C0 + W] = True
    out = rs.attach_truth(rs.run(s, USER, Recorder([leaky, exact, exact])), exact)
    assert out["rounds"][0]["truth_reference"]["iou"] < 1.0
    assert out["rounds"][1]["truth_reference"]["iou"] == pytest.approx(1.0)
    assert rs.attach_truth(rs.run(s, USER, Recorder([exact])), None)["rounds"][0]["truth_reference"] is None


@pytest.mark.parametrize("points,max_rounds", [
    ([], 3), ([{"row": 80, "col": 17, "label": 0}], 3), (USER, 0), (USER, 4),
])
def test_invalid_input(points, max_rounds):
    s, exact = _scene()
    with pytest.raises(ValueError):
        rs.run(s, points, Recorder([exact]), max_rounds=max_rounds)


def test_segmenter_shape_is_checked():
    s, _ = _scene()
    with pytest.raises(ValueError):
        rs.run(s, USER, Recorder([np.ones((5, 5), bool)]))
