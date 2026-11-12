"""Shared helpers for the Kiro hook scripts in this folder (standard library only).

Kiro passes the hook event as JSON on STDIN. The scripts do not depend on its exact shape: they
walk the JSON and collect every string under a key of interest (file paths, shell commands)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_event() -> object:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {"raw": raw}


def strings_under(obj: object, keys: tuple[str, ...]) -> list[str]:
    """Every string value whose key contains one of `keys` (case-insensitive), at any depth."""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and any(s in str(k).lower() for s in keys):
                out.append(v)
            else:
                out.extend(strings_under(v, keys))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(strings_under(v, keys))
    return out


def venv_python() -> str:
    for p in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if p.exists():
            return str(p)
    return sys.executable
