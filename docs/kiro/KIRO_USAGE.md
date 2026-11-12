# How Kiro was used

This is the detailed account of Kiro use for the hackathon write-up; the README keeps only a summary of the engineering method. Paths are relative to the repository root.

Everything below is committed under [`/.kiro`](../../.kiro) and in the scripts it calls.

**Kiro CLI and Kiro IDE.** Both were used; Kiro Web and Kiro Crew were not. The two share one configuration: the specs, steering files and hooks under `/.kiro` are read by the IDE and by the CLI alike, so the same rules and checks applied in both. The IDE was used for editing and reviewing the code and documents directly. The CLI ran the agent sessions: spec writing, implementation, test and GPU measurement runs, browser checks and commits. Larger independent jobs were handed to sub-agents with fresh context, some in parallel: the English translation of the frontend, the translation of the server messages alongside the export rewrite, a documentation check of Kiro's hook and agent formats, and the clean-clone test on a second machine by a session that had not seen the repository. What each was asked and what it reported is in [`docs/kiro/build-log.md`](build-log.md).

**Spec-driven development.** Three specs in `.kiro/specs/`:
- `samforgeophysics-mvp`: the product spec.
- `qc-refine-loop`: written **before** the code. Its `tasks.md` records what happened when the declared design met data: the first QC design failed its own acceptance criterion (a property test found a counterexample and the ground truth ranked best on 0 of 12 demo checks), the owner chose a redesign, and the spec was changed first, then the code. The measurement protocol was declared in the script before its only run, and its results set two UI defaults.
- `volume-propagation`: written **after** the code, to document and test it.

Compared with prompting feature by feature, the spec made the failure visible: the acceptance criteria were fixed before any result was seen, so a QC that "looked fine" on demo data could not be tuned until it passed.

**Steering.** `.kiro/steering/`: `product`, `tech`, `structure`, `competition` and `scope` are always included; `seismic-domain` loads automatically; `sources` (verified prior work) is manual. `scope.md` is the boundary: work that does not map to one of its items is not started, and it holds the convergence rules (no more redesign, one measurement run, the demo story follows the numbers).

**Agent hooks.** `.kiro/hooks/`:
- `dev-loop.json`
  - `PostFileSave` on `src/*.py`: runs that module's tests (`scripts/hooks/test_for_saved_file.py`).
  - `PostFileSave` on `src/static/js/*.js`: syntax-checks the frontend scripts.
  - `PreToolUse` on the shell: blocks `git add` of data, weights or volume files, `git add --force`, force pushes and `git reset --hard` (`scripts/hooks/guard_shell.py`, exit code 2).
  - `Stop`: re-runs the claims check at the end of every agent turn.
- `competition-guards.json`: keeps `/.kiro` out of `.gitignore`; rejects forbidden claims when docs change.
- `data-provenance.json`, `synthetic-data.json`: public-data policy and generator determinism.

Tests for the hook scripts and the hook files are in `tests/test_hooks.py`.

**Custom agent.** `.kiro/agents/claims-auditor.json` is a read-only reviewer for public text: every number must trace to `docs/MEASUREMENTS.md`, no forbidden claims, SGSeg reuse disclosed, every Kiro claim backed by a file. Run it with `kiro-cli chat --agent claims-auditor`. Its first run on this README (headless, `kiro-cli chat --v3 --no-interactive --agent claims-auditor`) failed it with 7 items, including a wrong start date and two unbacked claims; the run and the fixes are in [`docs/kiro/claims-audit-2026-11-12.md`](claims-audit-2026-11-12.md).

**Property-based testing.** `hypothesis` tests in `tests/test_qc_service_pbt.py`. They caught a bug the unit tests missed: in the first QC design, *adding* background pixels to an exact mask raised its score (583 of 900 scanned cases), because the envelope spreads target energy past the target's edge. The same tests then defined the redesign's two stated resolution limits.

**MCP.** Not used. The Pencil design MCP was available, but the panels were small enough to design directly in HTML.

**Kiro powers.** Checked; no power was installed or used.
