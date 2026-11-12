---
inclusion: always
---

# Scope, Quality Bar and Plan — Kiroween 2026

> Status: **ACTIVE since 2026-11-12.** Based on the full Official Rules PDF, re-read 11-12 (digest: `docs/COMPETITION_RULES.md`). This file is the boundary for every agent session: work that does not map to an S- or E-item below is not started, however small it looks. Changing the boundary means editing this file first, with the owner's yes.
>
> Submission deadline: **Fri 2026-12-04 14:00 PT = Sat 12-05 06:00 Beijing.** Internal target: **Thu 12-03**. The project must stay runnable until judging ends **2027-01-29**.

## 0. Status and convergence rules (updated 2026-11-12, end of M3) - read this first

**Done:** M1 (S1, S2, S3, S13, B1) · M2 (S4, S5, `measure_refine.py`, S6) · M3 (S7, S8, S9, S10, most of S11; E1, E2, E3, first E6). 200 tests green; pushed to `origin/kiro`.

**UI defaults set by the measurement (`docs/MEASUREMENTS.md`):** SAM and the loop segment the raw slice; Auto-refine on for NPY volumes.

**Open before the freeze (11-27):** owner: make the repo public (E2 found it private), state IDE / Web / Crew use for the README; after that, a second `claims-auditor` run on README + Devpost text. Then M4: video script, recording, Devpost text, merge `kiro` → `main` (and change the README clone line back to the default branch), tag.

**Known limitations recorded, not to be fixed (rule 1):** the QC kept a worse-than-round-1 mask (by truth) on 3 / 19 clean slices; the line box counts from 0 while the title shows IL numbers; the e2e scripts print Chinese text.

**Convergence rules:**
1. **No more research or redesign.** The QC design, its constants and the H1/H2 metric are frozen. A new weakness is written down as a limitation in `docs/MEASUREMENTS.md` or the spec, not fixed by a new design.
2. **One measurement, run once.** `measure_refine.py` uses one declared click rule, compares raw vs low-freq view and 1 round vs loop, and its output decides two UI defaults (which view SAM segments, whether Auto-refine is on). No follow-up experiments.
3. **The demo story follows the numbers.** If SAM does better on the raw view, the story is "the low-freq view helps the interpreter see; SAM and QC work on raw". If the loop rarely beats round 1, H3 is presented as "checks itself, fixes poor clicks, never keeps a worse round", which the diagnostic runs already support.
4. **Deep target only in the UI.** Fault QC stays in code and tests, not in the panel.
5. Anything not in §3.1 needs the owner's yes first (existing rule).

## 1. Goal

A geophysicist or judge clones the public repo, runs one setup command and opens the app on a desktop machine. They see a synthetic section with a weak deep target, make it more visible with the low-frequency view and the noisy/clean pair, prompt SAM3, and watch a label-free QC loop refine the mask for up to 3 rounds, then export the result. A <3 min public video shows the same flow on the local GPU machine, and the README explains how Kiro built it.

**Done** = every S- and E-item below is ticked, and every hard requirement in `competition.md` is met.

## 2. Platform and delivery (rules: Functionality, Platforms, Testing)

| Item | Decision |
|---|---|
| Intended platform (stated in the submission) | Desktop web app: Python 3.10+ server on Windows 10/11 or Linux, opened in a current desktop browser. NVIDIA GPU recommended; CPU works but each new slice takes ~15 s to encode (measured 11-12, Core Ultra 9 285K: ~13.5 s) |
| Judge access | **Test build** = the public GitHub repo plus testing instructions (the rules allow "a website, functioning demo, or a test build"). No hosted instance (owner, 11-12) |
| SAM weights | `sam3.pt` under Meta's SAM License. Never committed. The README points judges to Meta's official release (`facebookresearch/sam3` → gated `facebook/sam3` on Hugging Face) with size and SHA-256 (§9); without weights the app runs in a clearly labelled no-SAM mode |
| Development and recording | Local or LAN GPU machines only. CPU and hosting are not optimised |
| Availability | Tag `v1.0-submission` on `main`. After 12-04, `main` changes only for fixes that keep the tagged behaviour, until 2027-01-29 |

Because the rules say judges "may choose to judge based solely on the text description, images, and video", the video and README must make the whole case without anyone running the code.

## 3. Feature boundary

### 3.1 In scope (and nothing else)

| ID | Feature | Priority | Acceptance check | Due |
|---|---|---|---|---|
| S1 | `?mode=raw\|lowfreq` on the three slice endpoints, reusing `lowfreq_service` and `_npy_binary_response`; SAM embed can take the low-frequency image | P0 | Same shape and headers as raw; `amplitude.npy` unchanged; unit tests | 11-13 |
| S2 | UI: Raw / Low-freq toggle and side-by-side view; one-click Noisy / Clean pair at the same slice position | P0 | **Done 11-12** (`src/static/js/compare.js`). Headless-Chrome run: toggle requests `?mode=lowfreq` and restores raw exactly; Compare = Raw \| Low-freq and Noisy \| Clean with labelled panels and duplicated top-axis ticks; navigation keeps both panels in step; Noisy ⇄ Clean keeps direction and index; SAM on the low-freq view embeds `mode: lowfreq` (seed 648 voxels); no JS errors. Each compare panel uses its own auto gain (99th-percentile clip) times the shared user gain Changed 11-12 by the S5 measurement: SAM always embeds the **raw** slice, whatever view is shown (`docs/MEASUREMENTS.md`). | 11-15 |
| S3 | `scripts/measure_lowfreq.py`: deep-target vs background contrast, raw vs low-freq, noisy vs clean, fixed seed | P0 | **Done 11-12.** Byte-identical reruns; metric (window RMS, TBR, AUC, shifted-footprint control) declared before the first run; 10 tests in `tests/test_measure_lowfreq.py`. Results and allowed wording in `docs/MEASUREMENTS.md`: noisy AUC 0.437 raw → 0.927 low-freq; clean 0.515 → 1.000; control ≤ 0.33. The model was built with a 10 Hz target and 32 Hz horizons, so this confirms the pipeline, not real-data separability | 11-16 |
| S4 | `src/qc_service.py`: **label-free** QC of the deep-target mask (edge leakage, envelope contrast inside vs ring outside) and fault continuity; constants declared at module top. Ground-truth overlap from `validation_service` is shown beside it and never feeds the loop | P0 | Monotonic on constructed masks (unit + property tests) | 11-19 **Done 11-12** (design C + decision A): QC relative to the clicked envelope, always on the raw view, with a reliability gate. 27 QC tests. Demo check: clean volume reliable, truth ranked best 3/3; noisy volume flagged unreliable, so the loop does not run there — see `qc-refine-loop/tasks.md` |
| S5 | Refinement driver + `POST /api/npy/{vol}/refine`: worst region → corrective positive/negative point, max 3 rounds, early stop, keep best round; round log persisted in SQLite | P0 | Tests cover early stop, best-round keep, log replay; one embed per loop **Done 11-12** (`measure_refine.py`, `test_refine_e2e.py` PASS here and on `gpu4090`). | 11-21 |
| S6 | UI: round-by-round QC panel (score per round, corrective points drawn, best round marked) | P0 | Frame V5 can be recorded live **Done 11-12**: `refine-panel.js`; headless Chrome: clean IL 24 three rounds, round selection changes the mask, diamonds drawn; noisy shows the gate message; Auto-refine off uses `/predict`; time slice disables it; no JS errors. | 11-22 |
| S7 | Degraded paths: no weights → status bar says what is missing and where to get it, browse / low-freq / export keep working; CPU only → visible "encoding on CPU" state; `/propagate` and SAM endpoints return 503 when weights are missing | P0 | Manual run with weights moved away; no blank page, no unhandled 500 **Done 11-12**: SAM3 badge (GPU / CPU / weights missing + source), CPU encoding notice, `/propagate` 503, `errText` / `respError` for unreachable server and non-JSON answers; `tests/test_degraded.py`; E3 walk done. | 11-24 |
| S8 | English UI: every button, label, status and error string in the demo flow. Includes the layout pass found 11-12: the toolbar wraps to 3 rows at 1600×900, which pushes the slice slider (`#slicePanel`) below the footer; regroup and hide controls the demo does not use | P0 | `grep` for CJK characters in `index.html` and `src/static/js/` returns nothing user-visible; slice slider visible at 1600×900 **Done 11-12**: CJK grep over `index.html`, `src/static/**` and `src/*.py` is empty; toolbar 2 rows (58 px) at 1600×900, other controls under More ▾; slider visible. | 11-25 |
| S9 | Test build: README "Run it" section (prerequisites incl. supported Python 3.10–3.12 and whether Node.js is needed, venv creation, `pip install -r requirements.txt`, data generation, weights download + checksum, start), and `npm run verify` running check + pytest + data verify, with a plain-Python equivalent | P0 | E2 passes on `gpu4090` **Done 11-12**: README "Run it" + testing instructions; `scripts/verify.py` = `npm run verify`; E2 passed on `gpu4090` after README fixes (see `docs/kiro/build-log.md`). | 11-26 |
| S10 | Export: GeoJSON + CSV polygons + QC round log (JSON) | P0 | Files open and match the on-screen result **Done 11-12**: pixel-edge contours (round trip IoU 1.00 with the shown mask), `qc_log_*.json`. | 11-26 |
| S11 | Kiro evidence (see §5) | P0 | Each write-up topic has a real artefact or an honest "not used" **Mostly done 11-12**: `dev-loop.json` (PostFileSave ×2, PreToolUse guard, Stop), `claims-auditor` agent + first headless run (FAIL 7 → fixed, `docs/kiro/claims-audit-2026-11-12.md`), README Kiro section, `docs/kiro/build-log.md`. Open: owner's IDE / Web / Crew statement. | 11-28 |
| S12 | Submission: video ≤165 s, English README final with SGSeg disclosure, Devpost text and testing instructions, `kiro` merged into `main`, tag | P0 | `competition.md` checklist all ticked | 12-03 |
| S13 | Survey map panel in the section view (owner, 11-12): IL × XL plan view, current-slice line, volume-mask footprint (`GET /api/npy/{vol}/mask/{name}/footprint`), click to open an inline / crossline, collapsible. A separate 3-D window stays out of scope | P1 | **Done 11-12**: `tests/test_mask_footprint.py`; browser run (Chrome headless) covered load, inline / crossline / time-slice clicks, footprint after propagation, collapse, volume switch, no JS errors | 11-12 |
| B1 | **Fixed 11-12.** Bug: a SAM click in the UI wrote an empty slice to the volume mask, so browser propagation failed. Root cause: the browser embedded a screenshot of the live canvas, which contains the pick marker (and colour map / overlays); SAM segmented the 6×6 px marker (reproduced in-process: 32 mask pixels with the marker, 521,298 without). Fix: new `POST /api/npy/{vol}/embed` renders the slice on the server (grey, uniform integer upscale, same renderer as propagation) and returns the scale; the UI sends clicks in that image's pixels. Non-NPY sources embed the clean rendering instead of the canvas | P0 | `tests/test_npy_embed.py` (10); headless-Chrome click → SAM → propagate: seeds 749 / 402 voxels, 10 slices propagated, no JS errors; `scripts/test_propagation_e2e.py` now seeds through this endpoint and asserts a non-empty seed | 11-12 |

### 3.2 Frozen as is (bug fixes only)

- Volume mask and cross-slice propagation (`.kiro/specs/volume-propagation/`). Touched only by S7 (503) and S8 (English). At most a ~10 s "3-D extension" shot in the video, recorded only after V2–V5 exist (D4).
- Inherited SGSeg features: SEG-Y upload, Zarr / VDS backends, LLM assistant, SQLite sessions. They must keep working; no new work; not in the video.

### 3.3 Out of scope until after 12-04

- Hosted or public instance, CPU latency work, authentication, multi-user.
- Horizon closure error (MVP Requirement 4.1 narrowed; see D2).
- Propagation extensions (negative or box prompts, write locks, low-freq propagation).
- Mask management UI, 3-D rendering or a separate 3-D window, meshes (the in-view survey map, S13, is the agreed substitute).
- Crossline / timeslice polish beyond what works today.
- New data sources, real field data, fine-tuning.
- Bonus-prize work (separate Kiro Crew app repo, blog, social post) before M4 is complete.
- Refactors not required by an S- or E-item.

## 4. Stability and executability (rules: Functionality, Testing)

| ID | Requirement | Check | Due |
|---|---|---|---|
| E1 | One command proves the build: `npm run verify` = JS syntax + Python AST + preflight + `pytest tests` + data verify | Green on the dev machine before every commit that touches `src/` **Done 11-12** (`python scripts/verify.py`, `npm run verify`). | 11-26 |
| E2 | Clean clone runs: on a second machine (LAN, ideally Linux), follow only the README from `git clone` to the loaded first screen, with and without weights | Done by the owner or a fresh agent session that has not seen this repo; notes recorded in the S9 task **Done 11-12** on `gpu4090` by a fresh sub-agent, with and without weights; README fixed (clone `-b kiro`, `uv --seed`, CUDA torchvision, `timm`). The repo was not reachable anonymously. | 11-29 |
| E3 | No unhandled error in the demo flow: every API failure reaches the status bar in plain English | Walk the demo flow with the server stopped mid-way and with weights missing **Done 11-12** (weights moved away; server killed mid-flow; no blank page, no unhandled error). | 11-29 |
| E4 | Repeatable demo: the full flow (S1→S6→S10) runs 3 times in a row without restarting the server or reloading the page | Dry run before recording | 11-30 |
| E5 | Determinism: synthetic data byte-identical (`--verify-only`); QC metrics and refine decisions are deterministic for a given mask; the measurement script prints identical output on reruns | Tests + rerun `measure_lowfreq.py` | 11-23 |
| E6 | GPU end-to-end scripts (`scripts/test_sam_inference.py`, `scripts/test_propagation_e2e.py`, and a new refine e2e) pass before the freeze and before tagging | Run against a live server First pass **done 11-12**: all three GPU scripts pass locally; refine e2e also on `gpu4090`. Repeat 12-02. | 11-29, 12-02 |
| E7 | Honesty gates: `preflight --check all` green; every number in README / video traced to a script; SGSeg reuse disclosed in README and Devpost text | Preflight + `claims-auditor` agent review | 12-02 |

## 5. Kiro usage plan (rules: Technological Implementation and the write-up prompts)

Rule for the write-up: describe only what was actually done, with a pointer to the artefact. "Not used, because …" is better than padding.

| Write-up prompt | What we do | Artefact |
|---|---|---|
| IDE / CLI / Web / Crew | CLI (this workflow) for spec execution, verification runs and commits; IDE for UI work and hook triggers; Crew for one parallel task if it fits (e.g. S8 alongside S5). Record what differed | README section, commit messages |
| Custom agents | `claims-auditor` in `.kiro/agents/`: reviews README / video script / Devpost text for numbers without a script, forbidden claims and missing disclosures | Agent file + one review run log |
| Agent hooks | Keep the 3 existing `PostFileSave` hooks; add hooks with other triggers: run the matching pytest file when `src/*.py` is saved; run `check:js` when `src/static/js/*.js` is saved; block `git add data/` or weights before tool use | `.kiro/hooks/*.json` + a run log |
| Spec-driven development | Specs: `samforgeophysics-mvp`, `volume-propagation` (written after the code, and the write-up says so), new `qc-refine-loop` written **before** S4–S6 | `.kiro/specs/` |
| Steering | `product` / `tech` / `structure` / `competition` / `scope` always on; `seismic-domain` auto; `sources` manual. The `scope.md` boundary is the strategy to report | `.kiro/steering/` |
| MCP | Use the Pencil MCP to design the QC panel and first screen before coding S2 / S6, only if it saves time | `.pen` file + screenshot, or "not used" |
| Property-based testing | Add `hypothesis` as a dev dependency: lowfreq preserves shape and is idempotent on DC; mask resample round-trip; QC metrics monotonic under growing leakage | `tests/test_*_pbt.py`; note any bug PBT found |
| Kiro powers | Check the available powers once; use one only if it applies | Note in README either way |

## 6. Judging map

| Criterion (20% each) | What carries it | Main risk |
|---|---|---|
| Potential Impact | V1 problem frame (weak deep target hidden in noise); interpreter workflow ending in an export | Synthetic-only data looks academic; say plainly who would use it and on what data |
| Technological Implementation | §5 artefacts; spec-before-code for the QC loop; hooks and agents in daily use | Thin Kiro evidence → disqualification risk |
| Design | First screen already loaded; one obvious prompt path; status always visible; English; no-weight mode | Inherited SGSeg toolbar is dense; hide what the demo does not use |
| Innovation / Idea | Label-free QC loop (H3) plus the noisy/clean pair (H2) | Ahmad et al. 2026 (arXiv:2606.15786) already conditions SAM inputs with attributes; lead with H3, present H1 as a conditioning choice, not as new |
| Presentation | ≤165 s storyboard in `docs/PROJECT_PLAN.md` §4; live footage only; no copyrighted music or third-party marks | Running long; record V5 first |

## 7. Plan (Beijing dates)

| Milestone | Window | Work | Exit check | If missed |
|---|---|---|---|---|
| M1 H1/H2 visible | 11-12 | **Done 11-12**: S1, S2, S3, S13 | — | — |
| M2 H3 loop | 11-13 → 11-17 | Backend **done 11-12** (S4, S5 API). Left: `measure_refine.py`, one declared click rule, run once (11-13); S6 panel, deep target only (11-14 → 11-15); browser check (11-16); buffer (11-17) | Loop runs live in the UI on the clean volume; tests green | Panel shows rounds without round selection |
| M3 Product + test build | 11-18 → 11-26 | S11 Kiro evidence: hooks, `claims-auditor`, CLI run, README Kiro section draft (11-18 → 11-19); S8 English UI + toolbar declutter (11-20 → 11-21); S7 + S10 (11-22); S9 + E1 (11-23); E2 on `gpu4090`, E3, E6 (11-24 → 11-25); buffer (11-26) | Clean clone works on `gpu4090` with and without weights | Cut S11 to what exists |
| **Feature freeze** | **11-27** | Bug fixes, copy and video only from here | — | — |
| M4 Submission | 11-27 → 12-03 | Video script (11-27); E4 dry run + record (11-28 → 11-29); README final, `claims-auditor` review, E7 (11-30 → 12-01); merge to `main`, tag, push (12-02); Devpost submit (12-03) | Checklist ticked | 12-04 is buffer for form problems only |

Rule from `docs/PROJECT_PLAN.md`: if any criterion looks below 7/10, fix that criterion before adding anything.

## 8. Decisions

| ID | Decision | Status |
|---|---|---|
| D1 | Reuse of SGSeg (begun June 2026) | **Resolved 11-12.** Rules allow pre-existing code if disclosed, and the work described must be built in the period. Owner confirms SGSeg is solely theirs (part of their PhD thesis). README and Devpost text list exactly what came from SGSeg and what was built after 10-30, and describe only the new work as the project |
| D2 | MVP Requirement 4.1 narrowed from "fault continuity + horizon closure error" to "label-free deep-target QC + fault continuity" | **Adopted 11-12** under the owner's instruction to fix the boundary. Reason: the deep target is the demo's subject and neither original metric measures it; a loop driven by ground truth would not work on real data; horizon closure needs multi-slice horizon picks that do not exist. Owner may reverse |
| D3 | No hosted instance; access through a test build | **Decided by owner 11-12**; consistent with the rules' "test build" option |
| D4 | Propagation in the video | **Adopted:** at most ~10 s, after V2–V5 are recorded |

## 9. Owner actions and environment facts

| Item | Status (11-12) |
|---|---|
| SGSeg ownership | **Done.** Solely the owner's, part of their PhD thesis |
| Kiro credits | **Done.** Received |
| Public repo `luziqing/seismic-exploration-system` | **Done.** Public; owner allows pushes at any time. Agents push `kiro` with fast-forward only, never force; `main` is updated at S12 |
| SAM3 weights for judges | **Decided 11-12 (owner): Meta's official source.** Code: <https://github.com/facebookresearch/sam3>; its README says the checkpoints are on the gated Hugging Face repo <https://huggingface.co/facebook/sam3> (request access, then `hf auth login`). Checked 11-12: `facebook/sam3` lists `sam3.pt` at 3,450,062,241 bytes with Git object `5b7c2eaba7c1e2a81f26bc7476bfe80e43e979e4` for its LFS pointer; the public mirror `bodhicitta/sam3` has the same object, whose pointer gives SHA-256 `9999e2341ceef5e136daa386eecb55cb414446a00ac2b55eb2dfd2f7c3cf8c9e`, equal to the local `data/weights/sam3.pt`. So Meta's file is byte-identical to ours. The README gives: request access → download `sam3.pt` → place at `data/weights/sam3.pt` → check size and SHA-256; use is under Meta's SAM License. Access approval is Meta's decision and may take time, so the README tells judges to request it first, and the no-SAM mode covers the wait |
| Second machine for E2 | **Available:** `ssh gpu4090` (192.168.204.76, user `yuzu`, key `~/.ssh/id_ed25519_huawei`, already in `~/.ssh/config`). Windows 10 Pro for Workstations, RTX 4090 24 GB (driver 617.14), 128 GB RAM, 464 GB free on C:. Has Git; default Python is **3.14**, Python 3.12 available through `uv`; **no Node.js / npm**. Agents may use it only for E2/E6 test runs in a fresh folder under the user's home, and must not install system-wide software without asking |
| YouTube upload (public) and Devpost submission | Owner, by 12-03 |

### Weight sources on record (11-12; follow-ups deferred)

| Source | File | Size (bytes) | Notes |
|---|---|---|---|
| <https://huggingface.co/facebook/sam3> (Meta, gated) | `sam3.pt` | 3,450,062,241 | **The one we use.** Byte-identical to local `data/weights/sam3.pt` (SHA-256 `9999e234…c3cf8c9e`) |
| <https://huggingface.co/facebook/sam3.1> (Meta, gated) | `sam3.1_multiplex.pt` | 3,502,755,717 | Released 2026-03-27. Adds Object Multiplex for multi-object **video** tracking; the image point-prompt path keeps the SAM 3 architecture. Ultralytics loads it for image point/box prompts. Not used: no expected gain for single-slice point prompts, and switching would mean re-verifying the SAM path |
| Owner's Google Drive mirror | `sam3.pt` + `LICENSE` | — | Upload in progress. `LICENSE` prepared at `data/weights/LICENSE` (SAM License, same Git object `16ee5f63…` as in both Meta repos) |

Deferred, not in scope before 12-04 unless the owner reopens them:
- Add the Drive link to the README as a backup source, after downloading it once on `gpu4090` and checking size + SHA-256 (with E2).
- Evaluate SAM 3.1 (`sam3.1_multiplex.pt`) for single-slice prompts, and its video predictor for cross-slice propagation (after the deadline).

### What the second machine already tells us (feeds S9 / E2)

- `requirements.txt` pins `numpy<2.0`; NumPy 1.26 has no wheels for Python 3.14, so `pip install` with the default Python on a fresh machine will fail. The README must state the supported Python range (3.10–3.12) and show how to create a venv with it.
- The npm scripts need Node.js, which a geophysicist's machine may not have. The README must either list Node as a prerequisite or give the plain Python commands first.
- SSH sessions on that machine run PowerShell, not a POSIX shell; E2 scripts must be PowerShell.
