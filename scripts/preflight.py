#!/usr/bin/env python3
"""Executable compliance checks used by the Kiro hooks in .kiro/hooks/.

    python scripts/preflight.py --check all
    python scripts/preflight.py --check kiro      # /.kiro committed and visible
    python scripts/preflight.py --check claims   # no fabricated / forbidden claims
    python scripts/preflight.py --check data     # no weights or field data tracked

Stdlib only, so it runs in any environment where the repository is cloned.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Lines in a negative / cautionary context are rules, not violations.
NEGATION = re.compile(
    r"\b(?:no|not|never|cannot)\b|do\s+not|must\s+not|shall\s+not|"
    r"不得|不能|禁止|不声称|UNVERIFIED",
    re.IGNORECASE,
)

FORBIDDEN = [
    (re.compile(r"first\s+(?:ever\s+)?SAM\s+(?:for|in)\s+seismic", re.I),
     "'first SAM for seismic' novelty claim"),
    (re.compile(r"首次\s*SAM|首个\s*SAM", re.I),
     "Chinese 'first SAM' novelty claim"),
    (re.compile(r"\b(?:implemented|built|deployed)\s+(?:an?\s+)?"
                r"(?:UAV|drone|quantum\s+sensor)", re.I),
     "UAV / quantum hardware presented as implemented"),
    (re.compile(r"\b\d+(?:\.\d+)?%\s+"
                r"(?:accuracy|improvement|speedup|faster|gain)\b", re.I),
     "unsourced performance percentage"),
]

BINARY_SUFFIXES = (".npy", ".sgy", ".segy", ".vds", ".vdso", ".zarr",
                   ".pt", ".pth", ".ckpt", ".onnx", ".pkl")
GITIGNORE_REQUIRED = ("*.npy", "*.pt", "*.sgy", "doc/")


def _gitignore_text() -> str:
    p = ROOT / ".gitignore"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def check_kiro() -> list[str]:
    errors: list[str] = []
    kiro = ROOT / ".kiro"
    if not kiro.is_dir():
        errors.append("/.kiro directory is missing at repo root")
    for part in ("specs", "steering", "hooks"):
        if not (kiro / part).is_dir():
            errors.append(f"/.kiro/{part} is missing")
    for required in ("requirements.md", "design.md", "tasks.md"):
        if not list((kiro / "specs").rglob(required)):
            errors.append(f"no spec contains {required}")

    for line in _gitignore_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!")):
            continue
        if stripped.startswith(".kiro"):
            errors.append(f".gitignore must not ignore .kiro: {stripped!r}")

    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", ".kiro/steering/product.md"],
            cwd=str(ROOT), capture_output=True)
        if result.returncode == 0:
            errors.append("git currently ignores .kiro/steering/product.md")
    except FileNotFoundError:
        pass  # git unavailable -> text check above still applies

    return errors


def check_claims() -> list[str]:
    errors: list[str] = []
    targets: list[Path] = [ROOT / "README.md", ROOT / "AGENTS.md",
                           ROOT / "HANDOFF.md"]
    for folder in ("docs", ".kiro/steering", ".kiro/specs"):
        targets.extend(sorted((ROOT / folder).rglob("*.md")))

    for path in targets:
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if NEGATION.search(line):
                continue
            for pattern, label in FORBIDDEN:
                if pattern.search(line):
                    errors.append(f"{rel}:{lineno}: {label}")
    return errors


def check_data() -> list[str]:
    errors: list[str] = []
    gi = _gitignore_text()
    for pattern in GITIGNORE_REQUIRED:
        if pattern not in gi:
            errors.append(f".gitignore is missing the {pattern!r} exclusion")

    try:
        result = subprocess.run(["git", "ls-files"], cwd=str(ROOT),
                                capture_output=True, text=True)
    except FileNotFoundError:
        return errors
    if result.returncode != 0:
        return errors
    for tracked in result.stdout.splitlines():
        low = tracked.lower()
        if low.startswith("doc/") or low.endswith(BINARY_SUFFIXES):
            errors.append(f"forbidden artefact is tracked by git: {tracked}")
    return errors


CHECKS = {"kiro": check_kiro, "claims": check_claims, "data": check_data}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=[*CHECKS, "all"], default="all")
    args = parser.parse_args()

    names = list(CHECKS) if args.check == "all" else [args.check]
    failed = False
    for name in names:
        issues = CHECKS[name]()
        if issues:
            failed = True
            print(f"FAIL  {name}")
            for issue in issues:
                print(f"      - {issue}")
        else:
            print(f"OK    {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
