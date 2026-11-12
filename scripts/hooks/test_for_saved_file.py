#!/usr/bin/env python
"""PostFileSave hook: after the agent saves src/<module>.py, run the tests that cover that module.

Mapping: src/qc_service.py -> tests/test_qc_service*.py, plus tests/test_qc*.py (the stem without
"_service"). Files can also be given as arguments (manual use). Prints the pytest summary, which Kiro
adds to the agent's context. Exit 0 = tests passed or nothing to run; 1 = a test failed (Kiro shows a
warning and the agent sees the failure in the output)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _event import ROOT, read_event, strings_under, venv_python  # noqa: E402


def tests_for(path: str) -> list[Path]:
    p = Path(path)
    if p.suffix != ".py" or p.parent.name != "src":
        return []
    stems = {p.stem, p.stem.removesuffix("_service")}
    found = {t for s in stems for t in (ROOT / "tests").glob(f"test_{s}*.py")}
    return sorted(found)


def main() -> int:
    paths = sys.argv[1:] or strings_under(read_event(), ("path", "file"))
    tests = sorted({t for p in paths for t in tests_for(p)})
    if not tests:
        print(f"No matching tests for {', '.join(paths) or 'this save'}.")
        return 0
    rel = [str(t.relative_to(ROOT)) for t in tests]
    r = subprocess.run([venv_python(), "-m", "pytest", *rel, "-q", "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True)
    tail = [ln for ln in r.stdout.splitlines() if ln.strip()][-15:]
    print(f"pytest {' '.join(rel)}:\n" + "\n".join(tail))
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
