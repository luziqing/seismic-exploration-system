#!/usr/bin/env python
"""Export deterministic synthetic demo slices and recorded local SAM3+QC runs for the static Vercel demo.

Usage:
    python scripts/export_static_demo.py                  # export slices + manifest only
    python scripts/export_static_demo.py --runs           # also record refine runs from a live local server
    python scripts/export_static_demo.py --all            # export both slices and recorded runs
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import lowfreq_service  # noqa: E402
import npy_service  # noqa: E402
from propagation_service import mask_to_points  # noqa: E402

VOLUMES = ("synthetic_deep_v1", "synthetic_deep_v1_clean")
EXPORT_INDICES = list(range(11, 30))  # inline indices 11..29 (IL 12..30)
MODES = ("raw", "lowfreq")
SEED = 20261108
MAX_DEMO_BYTES = int(2.5 * 1024 * 1024)  # 2.5 MiB hard ceiling (<= 2.5 MB)
MAX_DEMO_DECIMAL_BYTES = 2_500_000       # 2.5 MB decimal ceiling for strict safety

DEMO_DIR = ROOT / "demo"
ASSETS_DIR = DEMO_DIR / "assets"
RECORDED_DIR = DEMO_DIR / "recorded"

RUN_CASES = (
    ("synthetic_deep_v1_clean", 23, None, "refine_clean_il24.json"),
    ("synthetic_deep_v1", 20, "qc_unreliable", "refine_noisy_il21.json"),
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_volume_mode_slices(vol_dir: Path, mode: str) -> tuple[dict[int, np.ndarray], float]:
    """Read and optionally low-frequency-condition inlines 11..29; return slices and shared int16 scale."""
    meta = npy_service.get_metadata(str(vol_dir))
    dt_us = int(meta.get("dt_us") or lowfreq_service.DEFAULT_DT_US)
    raw_slices: dict[int, np.ndarray] = {}
    max_abs = 0.0
    for idx in EXPORT_INDICES:
        arr = npy_service.read_inline(str(vol_dir), idx)
        if mode == "lowfreq":
            arr = lowfreq_service.condition_slice(arr, dt_us=dt_us, time_axis=0)
        else:
            arr = np.asarray(arr, dtype=np.float32)
        raw_slices[idx] = arr
        local_max = float(np.max(np.abs(arr))) if arr.size else 0.0
        if local_max > max_abs:
            max_abs = local_max
    scale = (max_abs / 32767.0) if max_abs > 0.0 else 1.0
    return raw_slices, scale


def quantize_i16_le(arr: np.ndarray, scale: float) -> bytes:
    """Quantize a float32 slice into little-endian int16 bytes using shared scale."""
    q = np.clip(np.round(np.asarray(arr, dtype=np.float64) / scale), -32767, 32767).astype("<i2")
    return q.tobytes(order="C")


def export_slices() -> dict:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    existing_manifest_path = ASSETS_DIR / "manifest.json"
    existing_recorded: dict | None = None
    if existing_manifest_path.exists():
        try:
            old = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
            existing_recorded = old.get("recorded_runs")
        except Exception:
            existing_recorded = None

    volumes_manifest: dict[str, dict] = {}
    volume_list: list[dict] = []

    for vol in VOLUMES:
        vol_dir = ROOT / "data" / "npy" / vol
        amp_path = vol_dir / "amplitude.npy"
        if not amp_path.exists():
            raise FileNotFoundError(
                f"Missing {amp_path}. Generate with scripts/generate_synthetic_seismic.py"
            )
        meta = npy_service.get_metadata(str(vol_dir))
        amp_sha = _sha256_file(amp_path)
        size_mb = round(amp_path.stat().st_size / (1024 * 1024), 1)
        volume_list.append({
            "name": vol,
            "path": f"demo/assets/{vol}",
            "il_range": meta.get("il_range", []),
            "xl_range": meta.get("xl_range", []),
            "n_inlines": meta.get("n_inlines", 0),
            "n_crosslines": meta.get("n_crosslines", 0),
            "n_samples": meta.get("n_samples", 0),
            "size_mb": size_mb,
        })

        modes_manifest: dict[str, dict] = {}
        for mode in MODES:
            out_dir = ASSETS_DIR / vol / mode
            out_dir.mkdir(parents=True, exist_ok=True)
            slices_map, scale = compute_volume_mode_slices(vol_dir, mode)
            files_manifest: dict[str, dict] = {}
            shape = None
            for idx, arr in slices_map.items():
                shape = list(arr.shape)
                raw_bytes = quantize_i16_le(arr, scale)
                fname = f"il_{idx}.i16"
                out_file = out_dir / fname
                out_file.write_bytes(raw_bytes)
                files_manifest[str(idx)] = {
                    "path": f"demo/assets/{vol}/{mode}/{fname}",
                    "bytes": len(raw_bytes),
                    "sha256": _sha256_bytes(raw_bytes),
                }
            modes_manifest[mode] = {
                "dtype": "int16",
                "endianness": "little",
                "scale": scale,
                "shape": shape,
                "slices": files_manifest,
            }

        volumes_manifest[vol] = {
            "meta": meta,
            "amplitude_sha256": amp_sha,
            "modes": modes_manifest,
        }

    manifest = {
        "schema_version": 1,
        "seed": SEED,
        "generator_commands": [
            "python scripts/generate_synthetic_seismic.py",
            "python scripts/generate_synthetic_seismic.py --clean",
        ],
        "export_command": "python scripts/export_static_demo.py",
        "inline_index_range": [EXPORT_INDICES[0], EXPORT_INDICES[-1]],
        "inline_number_range": [EXPORT_INDICES[0] + 1, EXPORT_INDICES[-1] + 1],
        "volume_list": volume_list,
        "volumes": volumes_manifest,
    }
    if existing_recorded:
        manifest["recorded_runs"] = existing_recorded

    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    (ASSETS_DIR / "manifest.json").write_bytes(manifest_bytes)
    print(f"Exported slices for {len(VOLUMES)} volumes x {len(MODES)} modes x {len(EXPORT_INDICES)} inlines.")
    return manifest


def _interior_click(vol: str, idx: int) -> list[float]:
    truth = np.load(ROOT / "data" / "npy" / vol / "truth" / "deep_target_mask.npy", mmap_mode="r")
    t = np.asarray(truth[idx]).T.astype(bool)
    (r, c), = mask_to_points(t, 1)
    rows, cols = t.shape
    return [(c + 0.5) / cols, (r + 0.5) / rows]


def export_recorded_runs(server_url: str) -> None:
    import requests

    RECORDED_DIR.mkdir(parents=True, exist_ok=True)
    status = requests.get(f"{server_url}/api/status", timeout=15)
    status.raise_for_status()
    status_json = status.json()
    if not status_json.get("weights_exists"):
        raise RuntimeError("Server reports weights_exists=False; cannot record real SAM3 runs.")

    gpu_name = status_json.get("gpu_name") or status_json.get("sam_device") or "unknown"
    today = dt.date.today().isoformat()
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()

    provenance_lines = [
        "# Recorded SAM3 + QC Refine Runs (Provenance)",
        "",
        "Generated from the live local FastAPI + SAM3 server using the exact click rule in `scripts/test_refine_e2e.py` (`write_mask: false`).",
        "",
        f"- **Date**: {today}",
        f"- **Git commit SHA**: `{git_sha}`",
        f"- **Device / GPU**: `{gpu_name}` (`sam_device={status_json.get('sam_device')}`)",
        "",
        "## Runs",
        "",
    ]

    recorded_meta: dict[str, dict] = {}
    for vol, idx, expect_stop, out_name in RUN_CASES:
        body = {
            "direction": "inline",
            "index": idx,
            "mode": "raw",
            "target_type": "deep_target",
            "points": [_interior_click(vol, idx)],
            "labels": [1],
            "write_mask": False,
        }
        post_resp = requests.post(f"{server_url}/api/npy/{vol}/refine", json=body, timeout=300)
        post_resp.raise_for_status()
        post_run = post_resp.json()
        run_id = post_run["run_id"]

        get_resp = requests.get(f"{server_url}/api/refine/{run_id}", timeout=30)
        get_resp.raise_for_status()
        rep = get_resp.json()
        if expect_stop and rep.get("stop_reason") != expect_stop:
            raise RuntimeError(f"Expected stop_reason={expect_stop} for {vol} idx={idx}, got {rep.get('stop_reason')}")

        out_path = RECORDED_DIR / out_name
        raw_json = (json.dumps(rep, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
        out_path.write_bytes(raw_json)
        sha = _sha256_bytes(raw_json)
        print(f"Recorded {out_name}: run_id={run_id} stop={rep['stop_reason']} best=r{rep['best_round']} bytes={len(raw_json)}")

        il_num = idx + 1
        key = "clean" if vol.endswith("_clean") else "noisy"
        recorded_meta[key] = {
            "file": f"demo/recorded/{out_name}",
            "run_id": run_id,
            "volume": vol,
            "direction": "inline",
            "index": idx,
            "il_number": il_num,
            "recorded_date": today,
            "gpu_name": gpu_name,
            "sha256": sha,
        }

        rounds_desc = ", ".join(
            f"round {r['round']}: score={r['score']:.6f}"
            + (f", truth_iou={r['truth_reference']['iou']:.6f}" if r.get("truth_reference") else "")
            for r in rep.get("rounds", [])
        )
        provenance_lines.extend([
            f"### {out_name} ({vol}, IL {il_num}, index {idx})",
            f"- **Request body**: `{json.dumps(body, separators=(',', ':'))}`",
            f"- **run_id**: `{run_id}`",
            f"- **stop_reason**: `{rep['stop_reason']}`",
            f"- **best_round**: `{rep['best_round']}`",
            f"- **Round QC scores**: {rounds_desc}",
            f"- **SHA-256**: `{sha}`",
            "",
        ])

    (RECORDED_DIR / "PROVENANCE.md").write_text("\n".join(provenance_lines), encoding="utf-8", newline="\n")

    manifest_path = ASSETS_DIR / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["recorded_runs"] = recorded_meta
        manifest_path.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))


def check_demo_size() -> int:
    total = sum(p.stat().st_size for p in DEMO_DIR.rglob("*") if p.is_file())
    print(f"Total demo/ size: {total:,} bytes ({total / (1024 * 1024):.3f} MiB)")
    if total > MAX_DEMO_DECIMAL_BYTES:
        raise RuntimeError(f"demo/ size {total} exceeds 2.5 MB limit ({MAX_DEMO_DECIMAL_BYTES} bytes)")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="Export static web demo assets and recorded runs.")
    ap.add_argument("--slices", action="store_true", help="Export int16 slices and manifest.json")
    ap.add_argument("--runs", action="store_true", help="Record live refine runs from local server")
    ap.add_argument("--all", action="store_true", help="Export slices and record live runs")
    ap.add_argument("--url", default=os.environ.get("SAM3_URL", "http://127.0.0.1:9346"),
                    help="Local server URL for --runs (default: http://127.0.0.1:9346)")
    args = ap.parse_args()

    do_slices = args.slices or args.all or not args.runs
    do_runs = args.runs or args.all

    if do_slices:
        export_slices()
    if do_runs:
        export_recorded_runs(args.url.rstrip("/"))
    check_demo_size()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
