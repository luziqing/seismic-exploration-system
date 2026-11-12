"""Property-based tests for qc_service (spec qc-refine-loop, Requirement 1.3 / 1.6).

Scenes are built like the project's generator: a Ricker-wavelet target on noise, optionally with a
brighter, higher-frequency Ricker reflector a few samples above it (the situation found on the demo
volumes). The target's exact mask is its -6 dB envelope extent over its traces, the standard
definition of a wavelet's visible width. The interpreter's click is the target's centre.
derandomize=True keeps the examples identical on every run. These constructed scenes are the only
data the QC constants were checked on.

Resolution limits (by design): errors narrower than the guard band (GUARD_PX) sit inside it and are
not seen, so the left-out-target property applies to cuts wider than GUARD_PX; and score differences
below SCORE_RESOLUTION carry no meaning (the loop never acts on them), so 'never improves' means
'never improves by SCORE_RESOLUTION or more'.

History (2026-11-12): the first, percentile-based design failed the background property; design C
with hard-edged sine blocks also failed, because a block's envelope is wider than the block, so
that "exact" mask was not exact. See qc-refine-loop/tasks.md Findings."""
import sys
from pathlib import Path

import numpy as np
from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import qc_service as qc  # noqa: E402

ROWS, COLS, DT = 128, 40, 0.002
PBT = settings(max_examples=200, deadline=None, derandomize=True)


def ricker(f, center):
    t = (np.arange(ROWS) - center) * DT
    a = (np.pi * f * t) ** 2
    return (1.0 - 2.0 * a) * np.exp(-a)


@st.composite
def scene(draw, reflector=None):
    f = draw(st.floats(6.0, 16.0))
    amp = draw(st.floats(0.5, 3.0))
    w = draw(st.integers(8, 16))
    c0 = draw(st.integers(4, COLS - w - 4))
    center = draw(st.integers(60, 100))
    seed = draw(st.integers(0, 10_000))
    target = np.zeros((ROWS, COLS))
    target[:, c0:c0 + w] = amp * ricker(f, center)[:, None]
    env, _ = qc.envelope(target)
    exact = env >= env.max() * 10.0 ** (-6.0 / 20.0)
    exact[:, :c0] = False
    exact[:, c0 + w:] = False
    rows = np.flatnonzero(exact.any(axis=1))
    s = target + np.random.default_rng(seed).normal(0.0, 0.05, (ROWS, COLS))
    refl = None
    if draw(st.booleans()) if reflector is None else reflector:
        gap = draw(st.integers(3, 10))
        ratio = draw(st.floats(3.0, 6.0))              # reflector 3-6x brighter than the target
        rf = draw(st.floats(25.0, 40.0))
        r = ratio * amp * ricker(rf, rows[0] - gap - 6)
        s += r[:, None]
        renv, _ = qc.envelope(np.tile(r[:, None], (1, 2)))
        rr = np.flatnonzero(renv[:, 0] >= renv[:, 0].max() * 0.5)
        refl = (int(rr[0]), int(rr[-1]) + 1)
    click = [(center, c0 + w // 2)]
    return s.astype(np.float32), exact, click, (int(rows[0]), int(rows[-1]) + 1, c0, w), refl


@PBT
@given(scene(), st.integers(3, 8))
def test_adding_background_never_improves_the_mask(sc, depth):
    s, m, click, (r0, r1, c0, w), _ = sc
    grown = m.copy()
    grown[r1:min(ROWS, r1 + depth), c0:c0 + w] = True              # noise band below the target
    assert qc.score_mask(s, grown, click)["score"] < qc.score_mask(s, m, click)["score"] + qc.SCORE_RESOLUTION


@PBT
@given(scene(), st.data())
def test_leaving_out_more_than_the_guard_never_improves_the_mask(sc, data):
    s, m, click, (r0, r1, c0, w), _ = sc
    cut = data.draw(st.integers(qc.GUARD_PX + 1, w // 2))
    partial = m.copy()
    partial[:, c0 + w - cut:c0 + w] = False                         # right-hand traces left out; the click stays inside
    assert qc.score_mask(s, partial, click)["score"] < qc.score_mask(s, m, click)["score"] + qc.SCORE_RESOLUTION


@PBT
@given(scene(reflector=True))
def test_growing_into_a_brighter_reflector_lowers_the_score(sc):
    s, m, click, (r0, r1, c0, w), (rtop, _) = sc
    up = m.copy()
    up[rtop:r0, c0:c0 + w] = True                                   # up through the gap and the reflector
    exact, worse = qc.score_mask(s, m, click), qc.score_mask(s, up, click)
    assert worse["score"] < exact["score"] and worse["leak"] > exact["leak"]


@PBT
@given(scene(), st.integers(3, 8))
def test_exact_mask_ranks_above_typical_mistakes(sc, depth):
    s, m, click, (r0, r1, c0, w), refl = sc
    exact = qc.score_mask(s, m, click)["score"]
    band = m.copy()
    band[r1:min(ROWS, r1 + depth), c0:c0 + w] = True
    side = m.copy()
    side[r0:r1, c0 + w:min(COLS, c0 + w + 6)] = True                # 6 traces of background beside the target
    cut = m.copy()
    cut[:, c0 + w - (qc.GUARD_PX + 1):c0 + w] = False
    mistakes = [band, side, cut]
    if refl:
        up = m.copy()
        up[refl[0]:r0, c0:c0 + w] = True
        mistakes.append(up)
    for x in mistakes:
        assert qc.score_mask(s, x, click)["score"] < exact + qc.SCORE_RESOLUTION


@PBT
@given(st.integers(0, 10_000), st.floats(0.0, 0.9))
def test_score_in_unit_interval_for_random_masks(seed, density):
    rng = np.random.default_rng(seed)
    s = rng.normal(0.0, 1.0, (ROWS, COLS)).astype(np.float32)
    m = rng.random((ROWS, COLS)) < density
    r = qc.score_mask(s, m, [(ROWS // 2, COLS // 2)])
    assert 0.0 <= r["score"] <= 1.0
    for k in ("leak", "miss"):
        assert r[k] is None or 0.0 <= r[k] <= 1.0


@PBT
@given(scene())
def test_deterministic(sc):
    s, m, click, _, _ = sc
    assert qc.public(qc.score_mask(s, m, click)) == qc.public(qc.score_mask(s.copy(), m.copy(), click))
