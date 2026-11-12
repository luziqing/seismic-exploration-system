#!/usr/bin/env python
"""
One command that proves the build (scope E1): `python scripts/verify.py` or `npm run verify`.

Steps, stopping at the first failure:
  1. JavaScript syntax of src/static/js/*.js   (needs Node.js; skipped with a note if `node` is missing)
  2. Python syntax of src/**/*.py
  3. Competition preflight (scripts/preflight.py --check all)
  4. Test suite (pytest tests; needs requirements-dev.txt)
  5. Demo data reproducibility (generate_synthetic_seismic.py --verify-only, both volumes)
No GPU and no SAM weights are needed. Exit code 0 = all steps passed.
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
VOLUMES = ("synthetic_deep_v1", "synthetic_deep_v1_clean")


def run(cmd: list[str]) -> bool:
    return subprocess.run(cmd, cwd=ROOT).returncode == 0


def step_js() -> bool | None:
    node = shutil.which("node")
    if node is None:
        print("      Node.js not found: JavaScript syntax check skipped (the app itself does not need Node).")
        return None
    return run([node, "scripts/check_js.js"])


def step_py_syntax() -> bool:
    files = sorted((ROOT / "src").rglob("*.py"))
    for f in files:
        try:
            ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError as e:
            print(f"      {e}")
            return False
    print(f"      {len(files)} files parsed")
    return True


def step_pytest() -> bool:
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("      pytest not installed. Run: python -m pip install -r requirements-dev.txt")
        return False
    return run([PY, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"])


def step_data() -> bool:
    ok = True
    for name in VOLUMES:
        d = ROOT / "data" / "npy" / name
        if not (d / "meta.json").exists():
            flag = " --clean" if name.endswith("_clean") else ""
            print(f"      {name} missing. Generate it: python scripts/generate_synthetic_seismic.py{flag}")
            ok = False
            continue
        ok = run([PY, "scripts/generate_synthetic_seismic.py", "--out", str(d), "--verify-only"]) and ok
    return ok


STEPS = (("JavaScript syntax", step_js), ("Python syntax", step_py_syntax),
         ("Preflight", lambda: run([PY, "scripts/preflight.py", "--check", "all"])),
         ("Tests", step_pytest), ("Demo data", step_data))


def main() -> int:
    t0 = time.time()
    skipped = []
    for i, (name, fn) in enumerate(STEPS, 1):
        print(f"[{i}/{len(STEPS)}] {name}", flush=True)
        res = fn()
        if res is None:
            skipped.append(name)
        elif not res:
            print(f"\nVERIFY FAILED at step {i}: {name}")
            return 1
    note = f" (skipped: {', '.join(skipped)})" if skipped else ""
    print(f"\nVERIFY OK in {time.time() - t0:.0f} s{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
