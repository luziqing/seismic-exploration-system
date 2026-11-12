# Build log: how the work was split across Kiro sessions

What each Kiro CLI session or sub-agent was asked and what came back, for the README's "How Kiro was used". Dates are Beijing time. The main session is Kiro CLI on the development machine (Windows 11, RTX 4090 D). Sub-agents run with a fresh context and report back; several ran in parallel.

## 2026-11-12, M2 and M3

| Work | Who | Result |
|---|---|---|
| `scripts/measure_refine.py`: protocol declared in the script, run once, two reruns byte-identical | main session | Results and UI defaults in `docs/MEASUREMENTS.md`; commit `51cd1a7` |
| S6 QC panel, browser check in headless Chrome | main session | Commit `4e756e9`. The check found that the panel covered the deep target and blocked clicks, so it was moved |
| S8 English UI and toolbar declutter (index.html, src/static) | sub-agent (general-task-execution), which itself split `sam-client.js` and `sgy-client.js` to two more sub-agents | Toolbar 115 px → 58 px at 1600×900; slider visible; CJK grep empty |
| S8 server messages (src/*.py) to English | sub-agent, **in parallel** with the next row | Strings only; 2 test files updated to the new texts |
| S10 export: GeoJSON / CSV + QC log | sub-agent, **in parallel** with the previous row | Replaced the angle-sorted contour with pixel-edge tracing (round trip IoU 0.84 → 1.00). It also reported a pick-position bug at 1600×900 introduced by the new layout; the main session fixed it |
| Kiro hook and agent file formats | `introspect` sub-agent (answers from kiro.dev docs) | Confirmed the `.kiro/hooks/*.json` v1 schema already in use, the trigger names, exit code 2 for blocking `PreToolUse`, and the V3 agent format; used for `dev-loop.json` and `claims-auditor.json` |
| S7 no-weights mode, E3 walk (weights moved away; server stopped mid-flow) | main session | Every failure reaches the status bar in plain English; `tests/test_degraded.py` |
| Claims audit of README | custom agent `claims-auditor`, headless CLI | FAIL with 7 items, see `claims-audit-2026-11-12.md` |

## E2: clean clone on a second machine

Run by a sub-agent that had not seen the repository, following only the README, on the LAN machine `gpu4090` (Windows 10, RTX 4090, Python 3.12 from `uv`, no Node.js), in a fresh folder.

- **Without weights:** `python scripts/verify.py` printed `VERIFY OK` with the JavaScript check skipped (no Node). The page, `/api/status`, the volume list and a low-frequency slice answered 200; `POST /embed` answered 503 with the download instructions.
- **With weights** (copied from the development machine, size and SHA-256 checked with the README's command): `scripts/test_refine_e2e.py` printed `PASS`; `scripts/test_sam_inference.py` ran.
- **README problems it found, all fixed in the README or `requirements.txt`:**
  - the clone needs `-b kiro` until the branch is merged into `main`;
  - `uv venv` needs `--seed`, or the venv has no pip;
  - installing torch alone from the CUDA index is not enough: `pip install -r requirements.txt` then pulled a PyPI torchvision, which replaced the CUDA torch with a CPU build. torch and torchvision now come from the CUDA index together;
  - `timm` was missing from `requirements.txt`: ultralytics tried to pip-install it at the first SAM call, which hung on a machine without internet;
  - the SHA-256 check now prints `True` instead of asking the reader to compare 64 characters.
- **Not a README problem, for the owner:** the repository was not reachable anonymously (GitHub API answered 404), so the sub-agent cloned from a git bundle. Judges need it public.
