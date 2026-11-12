"""
QC-driven self-improving prompt loop (scope S5, spec .kiro/specs/qc-refine-loop/, Requirement 3).

run() takes a segmenter function and the interpreter's points, and repeats: segment -> QC on the raw
slice -> one corrective point at the worst region -> segment again, for at most MAX_ROUNDS rounds.
It never sees ground truth: truth overlap is attached afterwards by attach_truth(), for reporting only.
The segmenter is a parameter, so the loop is tested with deterministic stubs and no GPU.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

import qc_service as qc
from propagation_service import mask_to_points

MAX_ROUNDS = 3                      # product decision (MVP Requirement 4.2); one embed, so ~3 decoder passes
MIN_GAIN = qc.SCORE_RESOLUTION      # 0.01: smaller score changes carry no meaning
MIN_REGION_PX = 12                  # smaller leak / miss regions are a few pixels of envelope noise

STOP_REASONS = {
    "max_rounds": "Stopped after the maximum number of rounds.",
    "no_gain": "Stopped: the QC score did not improve.",
    "nothing_to_fix": "Stopped: nothing left to fix.",
    "empty_mask": "Stopped: SAM returned an empty mask.",
    "qc_unreliable": "Stopped: the target is too weak for label-free QC on this slice.",
}

# segment_fn(points_rc, labels) -> bool mask in the native grid; points are (row, col) floats
SegmentFn = Callable[[Sequence[tuple[float, float]], Sequence[int]], np.ndarray]


def constants() -> dict:
    return {"MAX_ROUNDS": MAX_ROUNDS, "MIN_GAIN": MIN_GAIN, "MIN_REGION_PX": MIN_REGION_PX, **qc.constants()}


def _correction(q: dict) -> tuple[tuple[int, int], int, int, str] | None:
    """(row, col), label, region size and kind for the larger of the largest leak / miss regions."""
    leak = qc.largest_region(q["leak_map"])
    miss = qc.largest_region(q["miss_map"])
    n_leak, n_miss = int(leak.sum()), int(miss.sum())
    region, label, kind = (leak, 0, "leak") if n_leak >= n_miss else (miss, 1, "miss")
    size = max(n_leak, n_miss)
    if size < MIN_REGION_PX:
        return None
    (r, c), = mask_to_points(region, 1)
    return (r, c), label, size, kind


def run(raw_slice: np.ndarray, user_points: Sequence[dict], segment_fn: SegmentFn,
        target_type: str = "deep_target", direction: str = "inline", max_rounds: int = MAX_ROUNDS) -> dict:
    """
    user_points: [{"row", "col", "label"}] in the native grid. Returns
    {"rounds": [...], "best_round", "stop_reason", "stop_message", "constants"}.
    Each round: {"round", "prompts", "metrics", "score", "delta", "mask", "correction"}.
    """
    if not 1 <= max_rounds <= MAX_ROUNDS:
        raise ValueError(f"max_rounds must be in [1, {MAX_ROUNDS}]")
    if not user_points:
        raise ValueError("at least one point is required")
    if not any(int(p["label"]) == 1 for p in user_points):
        raise ValueError("at least one include (positive) point is required")
    raw = np.asarray(raw_slice, dtype=np.float32)
    prompts = [{"row": float(p["row"]), "col": float(p["col"]), "label": int(p["label"]), "source": "user"}
               for p in user_points]
    seeds = [(p["row"], p["col"]) for p in prompts if p["label"] == 1]   # QC reference: the user's clicks only

    rounds, best, stop = [], None, "max_rounds"
    for r in range(1, max_rounds + 1):
        mask = np.asarray(segment_fn([(p["row"], p["col"]) for p in prompts], [p["label"] for p in prompts]),
                          dtype=bool)
        if mask.shape != raw.shape:
            raise ValueError(f"segmenter returned shape {mask.shape}, expected {raw.shape}")
        q = qc.score_mask(raw, mask, seeds, target_type=target_type, direction=direction)
        prev = rounds[-1]["score"] if rounds else None
        rec = {"round": r, "prompts": [dict(p) for p in prompts], "metrics": qc.public(q),
               "score": float(q["score"]), "delta": None if prev is None else float(q["score"] - prev),
               "mask": mask, "correction": None}
        rounds.append(rec)

        if not mask.any():
            stop = "empty_mask"
            break
        if r == 1 and not q["reliable"]:
            stop = "qc_unreliable"
            break
        if best is None or rec["score"] >= rounds[best - 1]["score"] + MIN_GAIN:
            best = r
        elif r > 1:
            stop = "no_gain"
            break
        if r == max_rounds:
            stop = "max_rounds"
            break
        corr = _correction(q)
        if corr is None:
            stop = "nothing_to_fix"
            break
        (cr, cc), label, size, kind = corr
        rec["correction"] = {"row": cr, "col": cc, "label": label, "region_px": size, "kind": kind}
        prompts.append({"row": float(cr), "col": float(cc), "label": label, "source": "correction"})

    if best is None:
        best = 1
    return {"rounds": rounds, "best_round": best, "stop_reason": stop,
            "stop_message": STOP_REASONS[stop], "constants": constants()}


def attach_truth(result: dict, truth_slice: np.ndarray | None) -> dict:
    """Add each round's overlap with the ground truth, for reporting only (run() never sees it)."""
    import validation_service

    for rec in result["rounds"]:
        if truth_slice is None or not np.asarray(truth_slice).any():
            rec["truth_reference"] = None
            continue
        v = validation_service.validate_segmentation(rec["mask"].astype(np.float32),
                                                     np.asarray(truth_slice, dtype=np.float32))
        rec["truth_reference"] = {k: v["metrics"][k] for k in ("iou", "dice", "precision", "recall")}
    return result
