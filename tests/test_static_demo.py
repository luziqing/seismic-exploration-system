"""Verification tests for the static web demo (assets, build output, shim routes, and hygiene)."""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demo"
MANIFEST_PATH = DEMO_DIR / "assets" / "manifest.json"
SHIM_PATH = DEMO_DIR / "demo-shim.js"
BUILD_SCRIPT = ROOT / "scripts" / "build_static_demo.mjs"
MAX_DEMO_BYTES = 2_500_000
MAX_DIST_BYTES = 4 * 1024 * 1024


def _load_exporter():
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import export_static_demo as exporter  # noqa: E402
    return exporter


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def test_demo_total_size_under_budget():
    files = [p for p in DEMO_DIR.rglob("*") if p.is_file()]
    assert files, "demo/ contains no files"
    total = sum(p.stat().st_size for p in files)
    assert total <= MAX_DEMO_BYTES, f"demo/ size {total} exceeds {MAX_DEMO_BYTES} bytes"


def test_manifest_sha256_and_slice_reproducibility():
    exporter = _load_exporter()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for vol, vol_info in manifest["volumes"].items():
        vol_dir = ROOT / "data" / "npy" / vol
        has_data = (vol_dir / "amplitude.npy").exists()
        if has_data:
            assert _sha256_file(vol_dir / "amplitude.npy") == vol_info["amplitude_sha256"]

        for mode, mode_info in vol_info["modes"].items():
            recomputed = None
            if has_data:
                slices_map, scale = exporter.compute_volume_mode_slices(vol_dir, mode)
                assert scale == pytest.approx(mode_info["scale"], rel=0, abs=1e-12)
                recomputed = slices_map

            for idx_str, slice_meta in mode_info["slices"].items():
                asset_path = ROOT / slice_meta["path"]
                assert asset_path.is_file(), f"missing asset: {asset_path}"
                data = asset_path.read_bytes()
                assert len(data) == slice_meta["bytes"]
                assert hashlib.sha256(data).hexdigest() == slice_meta["sha256"]
                if recomputed is not None:
                    expected_bytes = exporter.quantize_i16_le(recomputed[int(idx_str)], mode_info["scale"])
                    assert data == expected_bytes, f"byte mismatch at {vol}/{mode}/il_{idx_str}"

    for key, rec in manifest.get("recorded_runs", {}).items():
        rec_path = ROOT / rec["file"]
        assert rec_path.is_file(), f"missing recorded run {key}: {rec_path}"
        assert _sha256_file(rec_path) == rec["sha256"]
        run_obj = json.loads(rec_path.read_text(encoding="utf-8"))
        assert run_obj.get("rounds"), f"recorded run {key} has no rounds"


def test_build_static_demo_script():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js not installed")

    for js_file in (SHIM_PATH, BUILD_SCRIPT):
        chk = subprocess.run([node, "--check", str(js_file)], capture_output=True, text=True)
        assert chk.returncode == 0, f"node --check failed on {js_file}: {chk.stderr}"

    res = subprocess.run([node, str(BUILD_SCRIPT)], cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, f"build failed: {res.stdout}\n{res.stderr}"

    dist_dir = ROOT / "dist"
    dist_files = [p for p in dist_dir.rglob("*") if p.is_file()]
    assert dist_files, "dist/ is empty"
    assert not [p for p in dist_files if p.suffix == ".py"], "dist/ must contain no .py files"
    total_dist = sum(p.stat().st_size for p in dist_files)
    assert total_dist < MAX_DIST_BYTES

    orig_lines = (ROOT / "index.html").read_text(encoding="utf-8").splitlines()
    built_lines = (dist_dir / "index.html").read_text(encoding="utf-8").splitlines()
    diff = list(difflib.unified_diff(orig_lines, built_lines, lineterm=""))
    added = [ln[1:].strip() for ln in diff if ln.startswith("+") and not ln.startswith("+++")]
    removed = [ln[1:].strip() for ln in diff if ln.startswith("-") and not ln.startswith("---")]
    assert removed == [], f"Unexpected line removal in dist/index.html: {removed}"
    assert added == ['<script src="/demo/demo-shim.js"></script>'], f"Unexpected additions: {added}"


def test_all_frontend_fetch_urls_matched_by_shim_routes():
    shim_src = SHIM_PATH.read_text(encoding="utf-8")
    route_matches = re.findall(
        r"method:\s*'(GET|POST|DELETE|ANY)',\s*pattern:\s*/(.+?)/,",
        shim_src,
    )
    assert route_matches, "Could not parse ROUTES table from demo/demo-shim.js"
    routes = [(m, re.compile(pat.replace("\\/", "/"))) for m, pat in route_matches]

    concrete_paths: list[tuple[str, str]] = []
    js_dir = ROOT / "src" / "static" / "js"
    for js_file in sorted(js_dir.glob("*.js")):
        txt = js_file.read_text(encoding="utf-8")
        # Direct fetch('/api/...') or fetch(`/api/...`)
        for match in re.finditer(r"fetch\(\s*(['\"`])([^'\"`\n]+)\1(?:\s*,\s*\{([^}]+)\})?", txt):
            raw_url = match.group(2)
            opts = match.group(3) or ""
            m_method = re.search(r"method:\s*'([A-Z]+)'", opts)
            method = m_method.group(1) if m_method else "GET"
            if raw_url.startswith("/api/"):
                # Substitute JS template expressions with sample path segments
                resolved = re.sub(r"\$\{dir\}", "inline", raw_url)
                resolved = re.sub(r"\$\{(?:index|currentSessionId|sid|run_?id)\}", "20", resolved)
                resolved = re.sub(r"\$\{[^}]+\}", "synthetic_deep_v1", resolved)
                resolved = resolved.split("?", 1)[0]
                concrete_paths.append((f"{js_file.name}: {method} {resolved}", method + " " + resolved))
        # Also verify sgy-client.js dynamic fetchSlice URL builder (`/${source}/${name}/slice/${dir}/${index}`)
        if js_file.name == "sgy-client.js":
            assert "sliceApiUrl(" in txt and "fetch(url)" in txt
            for src_prefix in ("api/npy", "api/zarr", "api/vds"):
                sample = f"/{src_prefix}/synthetic_deep_v1/slice/inline/20"
                concrete_paths.append((f"sgy-client.js: GET {sample}", "GET " + sample))

    assert len(concrete_paths) >= 35, f"Expected >= 35 static fetch callsites, got {len(concrete_paths)}"
    for label, entry in concrete_paths:
        method, path = entry.split(" ", 1)
        matched = any(
            (rm == "ANY" or rm == method) and pat.search(path)
            for rm, pat in routes
        )
        assert matched, f"Unmatched frontend fetch in demo-shim.js: {label}"


def test_no_cjk_in_vercel_or_demo_files():
    cjk_re = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
    targets = [ROOT / "vercel.json", ROOT / ".vercelignore", BUILD_SCRIPT]
    targets.extend(p for p in DEMO_DIR.rglob("*") if p.is_file() and p.suffix in {".js", ".json", ".md"})
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert not cjk_re.search(text), f"Unexpected CJK character in {path}"
