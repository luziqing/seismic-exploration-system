"""Kiro hook scripts (scripts/hooks/) and the hook files in .kiro/hooks/ (schema: kiro.dev/docs/hooks)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "scripts" / "hooks"


def run_hook(script, event):
    return subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(event),
                          capture_output=True, text=True, cwd=ROOT)


@pytest.mark.parametrize("cmd", [
    "git add data/weights/sam3.pt",
    "git add src/server.py data/npy/synthetic_deep_v1/amplitude.npy",
    "git add ./data/rules/kiroween-2026-official-rules.pdf",
    "git add -f build.log",
    "git add model.safetensors",
    "git push --force origin kiro",
    "git push origin +kiro",
    "git reset --hard HEAD~1",
])
def test_guard_blocks(cmd):
    r = run_hook("guard_shell.py", {"tool_name": "execute_pwsh", "tool_input": {"command": cmd}})
    assert r.returncode == 2 and "Blocked" in r.stderr


@pytest.mark.parametrize("cmd", [
    "git add src/server.py tests/test_hooks.py docs/MEASUREMENTS.md",
    "git add -A .kiro/specs docs index.html src tests",
    "git push origin kiro",
    "python scripts/generate_synthetic_seismic.py --verify-only",
    "git status --short data",
])
def test_guard_allows(cmd):
    r = run_hook("guard_shell.py", {"tool_input": {"command": cmd}})
    assert r.returncode == 0, r.stderr


def test_tests_for_saved_file_maps_module_to_its_tests():
    sys.path.insert(0, str(HOOKS))
    from test_for_saved_file import tests_for
    names = {p.name for p in tests_for(str(ROOT / "src" / "qc_service.py"))}
    assert {"test_qc_service.py", "test_qc_service_pbt.py"} <= names
    assert tests_for(str(ROOT / "scripts" / "verify.py")) == []
    assert tests_for(str(ROOT / "src" / "static" / "js" / "app.js")) == []


def test_hook_files_follow_the_v1_schema():
    for f in sorted((ROOT / ".kiro" / "hooks").glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        assert doc["version"] == "v1", f
        for h in doc["hooks"]:
            assert h["name"] and h["trigger"] in {"SessionStart", "UserPromptSubmit", "Stop", "PreToolUse", "PostToolUse",
                                                   "PostFileCreate", "PostFileSave", "PostFileDelete",
                                                   "PreTaskExec", "PostTaskExec"}, (f, h)
            a = h["action"]
            assert a["type"] in {"command", "agent"} and (a.get("command") or a.get("prompt")), (f, h)
