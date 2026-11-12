# Claims audit, run 1 (2026-11-12)

**Agent:** `.kiro/agents/claims-auditor.json` (read-only tools; prompt `.kiro/agents/claims-auditor.md`).
**Command:** `kiro-cli chat --v3 --no-interactive --trust-all-tools --agent claims-auditor "Audit README.md (the whole file) against docs/MEASUREMENTS.md and the repository. Check every path the README mentions exists. Follow your output format exactly."` (Kiro CLI 3.2.1, Windows).
**Input:** README.md at commit `798fa28` plus the E2 fixes (clone branch, uv `--seed`, CUDA torchvision, hash check).
**Result:** FAIL, 7 items. The agent's output is reproduced below unchanged except for removed tool-progress lines.

## What was changed because of it

| # | Finding | Change |
|---|---|---|
| 1 | Start date "2026-11-09" contradicts "first commit 2026-11-08" in `competition.md` / `HANDOFF.md` | `git log` shows the first commit at 2026-11-09 11:35 +0800, so the steering files were wrong: corrected there, README keeps 11-09 with the source named |
| 2 | Sub-agent claim had no artefact | Added `docs/kiro/build-log.md`; README links it |
| 3 | IDE / Web / Crew use not stated (placeholder) | Owner confirmed: Kiro CLI and Kiro IDE used, Web and Crew not; README states this |
| 4 | No audit run log linked | This file; README links it |
| 5 | cu124 install not traceable | README now says where it was tested (E2 on the second machine) and links the log |
| 6 | "3.13 and newer do not work" only evidenced for 3.14 | Reworded: 3.14 fails, 3.13 untested |
| 7 | Tooltip pointed to a README section that does not exist | Tooltip now points to "Run it, step 4" |

## Agent output

| File:line | Text (short quote) | Problem | Verdict | Evidence or source checked |
|---|---|---|---|---|
| README ~L24 (Results table, row 1) | "AUC 0.44 (raw) → 0.93 (low-freq)" | None. It also carries the "built with a 10 Hz target" caveat. | OK | MEASUREMENTS: noisy AUC 0.437 → 0.927, all background. |
| README ~L25 | "mean IoU 0.43 on raw vs 0.06 on low-freq" | None. The conditions (one click, noisy volume) match. | OK | MEASUREMENTS: noisy/raw 0.432, noisy/low-freq 0.057. |
| README ~L26 | "Clean volume, 19 inlines: mean IoU 0.80 → 0.81 (median 0.88 → 0.89)" | None. This is the clean volume, raw view, which the README does not state. | OK | MEASUREMENTS: 0.798 → 0.814 and 0.876 → 0.894. The conditions match the "Wording" paragraph. |
| README ~L26 | "better on 9 slices, worse on 3, unchanged on 7" | None. | OK | MEASUREMENTS: 9 / 3 / 7. |
| README ~L26 | "declined to run on 18 of 19 slices" | None. | OK | MEASUREMENTS: `qc_unreliable` 18 (noisy/raw). |
| README ~L28 | "on 3 of the 19 clean slices it kept a round that scored better on QC but worse against the truth" | None. | OK | MEASUREMENTS: inlines 16, 28, 29 (clean/raw). |
| README ~L28 | "not guaranteed to improve a mask" | None. This is the required wording. | OK | MEASUREMENTS "Wording" paragraph. |
| README ~L16 | "All data is synthetic… Nothing here has been tested on field data." | None. | OK | product.md and MEASUREMENTS "What it does not show". |
| README ~L34 | "about 15 s to encode for SAM3" on CPU | None. | OK | scope.md §2: ~15 s, measured at ~13.5 s. |
| README ~L36 | "Python 3.13 and newer do not work yet: `numpy<2.0` has no wheels for them" | The repo only records the failure on Python 3.14 (scope.md §9). 3.13 was not tested. | FIX | scope.md §9 "What the second machine already tells us". |
| README ~L36 | "3.5 GB for the SAM3 weights" | None. | OK | scope.md §9: 3,450,062,241 bytes. |
| README ~L52 | "`--index-url …/whl/cu124`" and "should print a `+cu124` version" | The CUDA 12.4 choice appears nowhere in the repo. `requirements.txt` has only `torch>=2.0.0`. | FIX | requirements.txt, scope.md. Not traceable, so label it as a tested configuration or drop it. |
| README ~L58 | "48 × 48 × 256 samples, about 2.4 MB each" | None. | OK | 48·48·256·4 B = 2,359,296 B. The shape matches MEASUREMENTS. |
| README ~L58 | "`--clean`… (30 dB SNR)", "noisy (6 dB SNR)" | None. | OK | `--clean` exists in the generator. SNRs match MEASUREMENTS. |
| README ~L66 | "3,450,062,241 bytes, SHA-256 `9999e234…8c9e`" | None. | OK | scope.md §9 (full hash identical). |
| README ~L66 | Weights from `facebook/sam3` under Meta's SAM License, not included | None. The README names Meta's source and licence and does not imply the weights are shipped. | OK | scope.md §9, competition.md. |
| README ~L90 | "Open `http://127.0.0.1:9339`… `SAM3_HOST`… `SAM3_PORT`" | None. | OK | `src/server.py` L1138–1139: default port 9339 and both environment variables. |
| README ~L100 | "`python scripts/verify.py` or `npm run verify`… `VERIFY OK`" | The paths exist. I did not check that `VERIFY OK` is printed. | OK | `scripts/verify.py` and the `package.json` "verify" script exist. |
| README ~L110 (No-weights mode) | "**SAM3: weights missing**" badge with a tooltip | None. | OK | `src/static/js/app.js` L142–144. |
| app.js L144 (outside README, linked to it) | Tooltip says `See README "SAM3 weights"` | The README has no section with that name. Weights are step 4 of "Run it". | FIX | `grep` of README headings. |
| README ~L120 (Testing instructions) | "about 430–510 ms", "IL 21", "box value `23`", "IL 24" | The time window agrees with MEASUREMENTS (samples 215–255 at 2 ms). The inline and box numbering and the QC gate outcome on IL 21 were not checked. | OK (partly unchecked) | MEASUREMENTS. The GUI behaviour was not verified. |
| README ~L120–128 | Button names **Low-freq**, **Compare**, **Noisy ⇄ Clean**, **Include**, **▶ SAM**, **Export Mask**, **Propagate**, **Auto-refine** | None. The labels exist. "More ▾", "⚙", the hollow-diamond markers and the output file names `…geojson`, `…csv`, `qc_log_….json` were not checked. | OK (partly unchecked) | `index.html` L42–78. |
| README ~L136 (How it works) | Paths: `scripts/generate_synthetic_seismic.py`, `src/lowfreq_service.py`, `src/qc_service.py`, `src/refine_service.py`, `src/volume_mask_service.py`, `src/propagation_service.py`, `src/static/js/{compare,survey-map,refine-panel}.js` | None. All exist. | OK | Directory listings. |
| README ~L136 | "four horizons, a fault, a weak 10 Hz deep target" | None. | OK | MEASUREMENTS (10 Hz target), qc-refine-loop tasks ("fourth horizon"). |
| README ~L146 | "`.kiro/specs/qc-refine-loop/`" and the three specs | None. All three directories exist. | OK | `.kiro/specs` listing. |
| README ~L152 | "Larger independent jobs were handed to sub-agents running in parallel… English translation… ran at the same time as the export work" | No artefact in the repo backs this. | FIX | Searched `.kiro/`, `docs/` and `tests/`. Add a pointer (commit, log) or remove. |
| README ~L152 | `<!-- OWNER: add IDE / Web / Crew use here if any, or state "not used". -->` | Unfinished placeholder in public text. The write-up never says whether IDE, Web or Crew were used. | FIX | The rules require this prompt (competition.md). |
| README ~L156 | "`qc-refine-loop`… the first QC design failed… ground truth ranked best on 0 of 12 demo checks" | None. | OK | qc-refine-loop/tasks.md L21. |
| README ~L160 | "the spec made the failure visible" (comparison with feature-by-feature prompting) | The comparison with the alternative is asserted, not shown. The spec history supports only the first half. | OK (soften) | tasks.md. There is no vibe-coding baseline in the repo. |
| README ~L164 | Steering files `product`, `tech`, `structure`, `competition`, `scope`, `seismic-domain`, `sources` | Names match scope.md §5. I did not list `.kiro/steering/`. `seismic-domain` is the one I did not see a file for. | OK | scope.md §5, system steering list. |
| README ~L168–176 | `dev-loop.json` hooks: `PostFileSave` ×2, `PreToolUse`, `Stop`; `competition-guards.json`, `data-provenance.json`, `synthetic-data.json` | None. Triggers, matchers and scripts match the files. | OK | `.kiro/hooks/*.json`, `scripts/hooks/{guard_shell,test_for_saved_file}.py` exist. |
| README ~L178 | "`tests/test_hooks.py`" | None. | OK | File exists. |
| README ~L180 | "`.kiro/agents/claims-auditor.json`… `kiro-cli chat --agent claims-auditor`" | The file exists. | OK | `.kiro/agents/` listing. |
| README ~L180 | `<!-- AUDIT-RUN: link to the run log here. -->` | Unfinished placeholder. scope.md §5 promises "one review run log" and none is linked. | FIX | `docs/kiro/` was not opened. |
| README ~L184 | "`tests/test_qc_service_pbt.py`… 583 of 900 scanned cases" | None. | OK | tasks.md L20: "583 of 900". The file exists. |
| README ~L188 | "MCP: Not used. The Pencil design MCP was available, but the panels were small enough to design directly in HTML." | "Not used" is acceptable. The claim that Pencil was available is unverified. | OK | scope.md §5 allows "not used". |
| README ~L190 | "Kiro powers. Checked; no power was installed or used." | "Not used" is acceptable. No artefact records the check. | OK | scope.md §5. |
| README ~L194 | "This repository started on 2026-11-09" and "(from 2026-11-09)" | Contradicts the recorded first commit date. | FIX | competition.md L19 and L46, HANDOFF.md L9: "first commit 2026-11-08". |
| README ~L196–198 | SGSeg disclosure: begun June 2026, "solely the author's"; lists what came from SGSeg and what is new | The disclosure is present and complete. It lists the volume browser, the loaders, the SAM3 embed/predict pipeline, the LLM assistant, SQLite sessions and the first GeoJSON/CSV export as SGSeg. "What it does" item 4 introduces Export without a pointer to this section, but the section follows. | OK | competition.md, scope.md D1/§9. |
| README ~L200 | Prior work: arXiv:2407.14121, arXiv:2606.15786; "does not claim to be the first" | None. | OK | sources.md. |
| README ~L200 | "What this entry adds is the label-free QC loop that decides for itself when it can be trusted, and the noisy / clean pair." | This is not a "first" claim. The noisy/clean pair is a synthetic-data device and not clearly novel. | OK (watch) | sources.md. |
| README ~L204 | "MIT (LICENSE)", "`docs/DATA_PROVENANCE.md`", "no UAV or quantum sensor is implemented" | None. | OK | `LICENSE` and `docs/DATA_PROVENANCE.md` exist. |
| README (whole file) | Language | English only. | OK | Full read. |
| README (whole file) | Numbers in the file that I did not trace | `git clone -b kiro …luziqing/seismic-exploration-system.git` matches scope.md §9. The README mentions no test count, latency or speed-up figure. | OK | scope.md §9. |

**Must fix before submission** (most serious first)
1. README ~L194 and ~L198: the start date "2026-11-09" contradicts the recorded first commit of 2026-11-08 (competition.md, HANDOFF.md). This is in the eligibility disclosure, so reconcile it.
2. README ~L152: the sub-agent / parallel-translation claim has no backing artefact. Add a pointer or remove it.
3. README ~L152: the `<!-- OWNER: … -->` placeholder is still there. The write-up doesn't say whether IDE, Web or Crew were used.
4. README ~L180: the `<!-- AUDIT-RUN … -->` placeholder is still there and there is no claims-auditor run log. scope.md §5 lists that log as the artefact.
5. README ~L52: the `cu124` PyTorch index and the "+cu124" check output are not traceable. State where they were tested or generalise them.
6. README ~L36: "Python 3.13 and newer do not work" is only evidenced for 3.14. Reword to "3.14 verified failing; 3.13 untested".
7. `src/static/js/app.js` L144 tooltip refers to `README "SAM3 weights"`, but the README has no section by that name. Rename the section or change the tooltip.

Not checked: the GUI behaviour in "Testing instructions" (inline numbering, "More ▾", "⚙", export file names), because I read files only and did not run the app.

Verdict: FAIL (7 items)
