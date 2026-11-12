#!/usr/bin/env python
"""
Measure the QC-driven refine loop with real SAM3 (spec qc-refine-loop, Wave 5; scope S5/S6, §0 rule 2).
This script is the only source of H3 numbers and of the SAM-view comparison. Run it once.

Protocol (declared before the first run, no tuning):
  * Volumes: synthetic_deep_v1 (noisy, 6 dB) and synthetic_deep_v1_clean (30 dB).
  * Slices: every inline whose ground-truth deep-target slice is non-empty (inlines 11-29 for seed 42).
  * Click rule: ONE include click at the interior point of the truth slice
    (propagation_service.mask_to_points(truth, 1): the pixel farthest from the mask edge).
    This simulates an interpreter clicking the middle of the target. No exclude clicks.
  * SAM views: raw and low-frequency (the image SAM segments). QC always runs on the raw slice
    (decision A), exactly as POST /api/npy/{vol}/refine does: same renderer, one embed per run,
    refine_service.run with its declared constants, MAX_ROUNDS = 3.
  * "1 round" = round 1 of the loop (the plain SAM result). "Loop" = the round the loop keeps (best_round).
  * Truth IoU is attached after the loop (refine_service.attach_truth) and never seen by it.
  * Reported per case: gate fraction, every round's QC score and truth IoU, stop reason, best round.
    Every case where the kept round's truth IoU is not higher than round 1's is listed.
  * Output floats are rounded to 4 decimals so a rerun on the same GPU prints identical text.

Requires data/weights/sam3.pt and a CUDA GPU (CPU works but takes ~15 s per embed).
Usage:  python scripts/measure_refine.py [--json out.json]
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
import os
import tempfile
from pathlib import Path

import numpy as np

os.environ.setdefault("YOLO_VERBOSE", "False")    # ultralytics prints per-call warnings to stdout
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

VOLUMES = (("noisy", "synthetic_deep_v1"), ("clean", "synthetic_deep_v1_clean"))
VIEWS = ("raw", "lowfreq")
DIRECTION = "inline"


def _f(x) -> str:
    return "  -  " if x is None else f"{x:.3f}"


def r4(x):
    return None if x is None else round(float(x), 4)


def click_for(truth_slice: np.ndarray) -> dict:
    from propagation_service import mask_to_points
    (r, c), = mask_to_points(truth_slice, 1)
    return {"row": float(r), "col": float(c), "label": 1}


def run_case(raw: np.ndarray, view: np.ndarray, truth: np.ndarray, segmenter_for) -> dict:
    """One loop run. segmenter_for(view_image) -> (segment_fn, cleanup); injectable for tests."""
    import refine_service

    click = click_for(truth)
    segment, cleanup = segmenter_for(view, raw.shape)
    try:
        res = refine_service.run(raw, [click], segment, target_type="deep_target", direction=DIRECTION)
    finally:
        cleanup()
    refine_service.attach_truth(res, truth)
    rounds = [{"round": r["round"], "score": r4(r["score"]),
               "truth_iou": r4(r["truth_reference"]["iou"]) if r["truth_reference"] else None,
               "mask_px": int(np.asarray(r["mask"]).sum()),
               "correction": None if r["correction"] is None else
               {k: r["correction"][k] for k in ("row", "col", "label", "kind")}} for r in res["rounds"]]
    m1 = res["rounds"][0]["metrics"]
    best = rounds[res["best_round"] - 1]
    return {"click": [int(click["row"]), int(click["col"])],
            "target_like_fraction": r4(m1.get("target_like_fraction")), "reliable": bool(m1.get("reliable")),
            "rounds": rounds, "best_round": res["best_round"], "stop_reason": res["stop_reason"],
            "iou_round1": rounds[0]["truth_iou"], "iou_kept": best["truth_iou"]}


def summarise(cases: list[dict]) -> dict:
    i1 = np.array([c["iou_round1"] for c in cases], dtype=np.float64)
    ik = np.array([c["iou_kept"] for c in cases], dtype=np.float64)
    stops: dict[str, int] = {}
    for c in cases:
        stops[c["stop_reason"]] = stops.get(c["stop_reason"], 0) + 1
    d = ik - i1
    return {"n": len(cases), "mean_iou_round1": r4(i1.mean()), "median_iou_round1": r4(np.median(i1)),
            "mean_iou_kept": r4(ik.mean()), "median_iou_kept": r4(np.median(ik)),
            "kept_later_round": sum(c["best_round"] > 1 for c in cases),
            "improved": int((d > 0).sum()), "worse": int((d < 0).sum()), "unchanged": int((d == 0).sum()),
            "max_gain": r4(d.max()), "max_loss": r4(d.min()), "stop_reasons": dict(sorted(stops.items()))}


def sam_segmenter_factory(tmpdir: Path):
    import propagation_service
    import sam_service
    import volume_mask_service

    def factory(view: np.ndarray, grid_shape):
        rows, cols = grid_shape
        img, sy, sx = propagation_service.render_slice_image(view)
        path = tmpdir / "measure_refine.png"
        img.save(path, "PNG")
        emb = sam_service.embed_image(str(path))["embedding_id"]

        def segment(points_rc, labels):
            pts = [[(c + 0.5) * sx, (r + 0.5) * sy] for r, c in points_rc]
            out = sam_service.predict_mask_np(emb, pts, list(labels))
            return volume_mask_service.resample_mask_to_grid(out["mask"], (rows, cols))

        return segment, lambda: sam_service.drop_embedding(emb)
    return factory


def measure(npy_root: Path, segmenter_for) -> dict:
    import lowfreq_service
    import npy_service
    import refine_service

    out = {"protocol": {"direction": DIRECTION, "click_rule": "one include click at the truth slice's interior point",
                        "views": list(VIEWS), "qc_view": "raw"},
           "constants": refine_service.constants(), "volumes": {}}
    for label, name in VOLUMES:
        d = npy_root / name
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        truth_vol = np.load(d / "truth" / "deep_target_mask.npy")
        inlines = [int(i) for i in np.flatnonzero(truth_vol.any(axis=(1, 2)))]
        vout = {"name": name, "snr_db": meta.get("snr_db"),
                "amplitude_sha256": hashlib.sha256((d / "amplitude.npy").read_bytes()).hexdigest(),
                "inlines": inlines, "views": {}}
        for view_name in VIEWS:
            cases = []
            for il in inlines:
                raw = np.asarray(npy_service.read_inline(str(d), il), dtype=np.float32)
                view = raw if view_name == "raw" else lowfreq_service.condition_slice(
                    raw, dt_us=int(meta["dt_us"]), time_axis=0)
                truth = np.asarray(truth_vol[il]).T.astype(bool)
                if truth.shape != raw.shape:
                    raise RuntimeError(f"truth slice {truth.shape} does not match inline {raw.shape}")
                cases.append({"inline": il, **run_case(raw, view, truth, segmenter_for)})
            vout["views"][view_name] = {"summary": summarise(cases), "cases": cases}
        out["volumes"][label] = vout
    return out


def report(res: dict) -> str:
    lines = [f"Refine-loop measurement - click rule: {res['protocol']['click_rule']}; QC on raw; "
             f"MAX_ROUNDS {res['constants']['MAX_ROUNDS']}, MIN_GAIN {res['constants']['MIN_GAIN']}", ""]
    lines.append(f"{'volume':7s} {'SAM view':8s} {'n':>3s} | {'IoU round 1':>11s} {'IoU kept':>9s} (mean / median) | "
                 f"later kept  better worse same | stop reasons")
    for label, v in res["volumes"].items():
        for view_name, vv in v["views"].items():
            s = vv["summary"]
            lines.append(f"{label:7s} {view_name:8s} {s['n']:3d} | {s['mean_iou_round1']:.3f}/{s['median_iou_round1']:.3f} "
                         f"{s['mean_iou_kept']:.3f}/{s['median_iou_kept']:.3f}       | "
                         f"{s['kept_later_round']:5d}      {s['improved']:5d} {s['worse']:5d} {s['unchanged']:4d} | "
                         + ", ".join(f"{k} {n}" for k, n in s["stop_reasons"].items()))
    lines.append("")
    lines.append("Per case (inline: gate fraction; round score/IoU ...; stop; kept round)")
    for label, v in res["volumes"].items():
        for view_name, vv in v["views"].items():
            lines.append(f"-- {label} / SAM on {view_name}")
            for c in vv["cases"]:
                rs = "  ".join(f"r{r['round']} {_f(r['score'])}/{_f(r['truth_iou'])}" for r in c["rounds"])
                flag = "" if (c["iou_kept"] or 0) > (c["iou_round1"] or 0) else ("  [not improved]" if c["best_round"] > 1 else "")
                lines.append(f"  il {c['inline']:2d}: tl {_f(c['target_like_fraction'])}  {rs}  | "
                             f"{c['stop_reason']}, kept r{c['best_round']}{flag}")
    lines.append("")
    lines.append("Cases where the kept round's truth IoU is not higher than round 1 (loop did not help):")
    for label, v in res["volumes"].items():
        for view_name, vv in v["views"].items():
            nh = [c for c in vv["cases"] if not (c["iou_kept"] or 0) > (c["iou_round1"] or 0)]
            ils = ", ".join(str(c["inline"]) + ("*" if c["best_round"] > 1 else "") for c in nh)
            lines.append(f"  {label}/{view_name}: {len(nh)} of {len(vv['cases'])}: {ils}")
    lines.append("  (* = a later round was kept and its truth IoU is lower than or equal to round 1)")
    for label, v in res["volumes"].items():
        lines.append(f"{label}: amplitude sha256 {v['amplitude_sha256']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--npy-root", type=Path, default=ROOT / "data" / "npy")
    ap.add_argument("--weights", type=Path, default=ROOT / "data" / "weights" / "sam3.pt")
    ap.add_argument("--json", type=Path, help="also write the results to this JSON file")
    args = ap.parse_args()
    if not args.weights.exists():
        print(f"Missing SAM3 weights: {args.weights}. See README 'SAM3 weights'.", file=sys.stderr)
        return 2
    for _, name in VOLUMES:
        if not (args.npy_root / name / "amplitude.npy").exists():
            print(f"Missing {name}. Generate it first: python scripts/generate_synthetic_seismic.py", file=sys.stderr)
            return 2
    import sam_service
    sam_service.set_weights_path(str(args.weights))
    sam_service.ensure_loaded()
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(sys.stderr):   # library logs -> stderr
        res = measure(args.npy_root, sam_segmenter_factory(Path(tmp)))
    if args.json:
        args.json.write_text(json.dumps(res, indent=1, sort_keys=True), encoding="utf-8")
    print(report(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
