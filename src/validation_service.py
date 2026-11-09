"""
Validation helpers for SAM segmentation results.

This module computes binary segmentation metrics against a ground-truth mask
and evaluates those metrics against optional acceptance criteria.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _as_2d_float_array(mask: list[list[float]] | np.ndarray, name: str) -> np.ndarray:
    arr = np.asarray(mask, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be a 2D array, got shape {arr.shape}")
    if arr.size == 0:
        raise ValueError(f"{name} must not be empty")
    return arr


def _safe_div(numerator: float, denominator: float, empty_value: float = 0.0) -> float:
    if denominator == 0:
        return empty_value
    return float(numerator / denominator)


def _evaluate_acceptance(
    metrics: dict[str, float], acceptance: dict[str, float]
) -> tuple[dict[str, bool], bool]:
    checks: dict[str, bool] = {}
    passed = True
    for metric_name, minimum in acceptance.items():
        if minimum is None:
            continue
        actual = metrics.get(metric_name)
        if actual is None:
            continue
        ok = actual >= float(minimum)
        checks[metric_name] = ok
        passed = passed and ok
    return checks, passed


def validate_segmentation(
    predicted_mask: list[list[float]] | np.ndarray,
    ground_truth_mask: list[list[float]] | np.ndarray,
    prediction_threshold: float = 0.5,
    ground_truth_threshold: float = 0.5,
    acceptance: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Compare a predicted mask against a ground-truth mask.

    Both masks must be 2D arrays with identical shapes. Predicted values are
    thresholded at ``prediction_threshold``; ground-truth values are thresholded
    at ``ground_truth_threshold`` so callers can pass 0/1, 0/255, or float masks.
    """
    pred = _as_2d_float_array(predicted_mask, "predicted_mask")
    gt = _as_2d_float_array(ground_truth_mask, "ground_truth_mask")

    if pred.shape != gt.shape:
        raise ValueError(
            "predicted_mask and ground_truth_mask must have the same shape, "
            f"got {pred.shape} vs {gt.shape}"
        )

    pred_bin = pred >= float(prediction_threshold)
    gt_bin = gt >= float(ground_truth_threshold)

    tp = int(np.logical_and(pred_bin, gt_bin).sum())
    fp = int(np.logical_and(pred_bin, np.logical_not(gt_bin)).sum())
    tn = int(np.logical_and(np.logical_not(pred_bin), np.logical_not(gt_bin)).sum())
    fn = int(np.logical_and(np.logical_not(pred_bin), gt_bin).sum())
    total = tp + fp + tn + fn

    pred_pos = tp + fp
    gt_pos = tp + fn
    union = tp + fp + fn

    if pred_pos == 0 and gt_pos == 0:
        iou = dice = precision = recall = specificity = accuracy = 1.0
    else:
        iou = _safe_div(tp, union, empty_value=1.0)
        dice = _safe_div(2 * tp, 2 * tp + fp + fn, empty_value=1.0)
        precision = _safe_div(tp, tp + fp, empty_value=0.0)
        recall = _safe_div(tp, tp + fn, empty_value=0.0)
        specificity = _safe_div(tn, tn + fp, empty_value=1.0)
        accuracy = _safe_div(tp + tn, total, empty_value=1.0)

    metrics = {
        "iou": iou,
        "dice": dice,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "accuracy": accuracy,
    }
    acceptance = acceptance or {}
    checks, passed = _evaluate_acceptance(metrics, acceptance)

    return {
        "prediction_shape": [int(pred.shape[0]), int(pred.shape[1])],
        "ground_truth_shape": [int(gt.shape[0]), int(gt.shape[1])],
        "prediction_threshold": float(prediction_threshold),
        "ground_truth_threshold": float(ground_truth_threshold),
        "confusion": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "total": total,
            "predicted_positive": pred_pos,
            "ground_truth_positive": gt_pos,
        },
        "metrics": metrics,
        "acceptance": acceptance,
        "checks": checks,
        "passed": passed,
    }
