---
inclusion: always
---

# Scope, Quality Bar and Plan — Kiroween 2026

> Status: **ACTIVE since 2026-11-12.** Based on the full Official Rules PDF, re-read 11-12 (digest: `docs/COMPETITION_RULES.md`). This file is the boundary for every agent session: work that does not map to an S- or E-item below is not started, however small it looks. Changing the boundary means editing this file first, with the owner's yes.
>
> Submission deadline: **Fri 2026-12-04 14:00 PT = Sat 12-05 06:00 Beijing.** Internal target: **Thu 12-03**. The project must stay runnable until judging ends **2027-01-29**.

## 1. Goal

A geophysicist or judge clones the public repo, runs one setup command and opens the app on a desktop machine. They see a synthetic section with a weak deep target, make it more visible with the low-frequency view and the noisy/clean pair, prompt SAM3, and watch a label-free QC loop refine the mask for up to 3 rounds, then export the result. A <3 min public video shows the same flow on the local GPU machine, and the README explains how Kiro built it.

**Done** = every S- and E-item below is ticked, and every hard requirement in `competition.md` is met.

## 2. Platform and delivery (rules: Functionality, Platforms, Testing)

| Item | Decision |
|---|---|
| Intended platform (stated in the submission) | Desktop web app: Python 3.10+ server on Windows 10/11 or Linux, opened in a current desktop browser. NVIDIA GPU recommended; CPU works but each new slice takes ~15 s to encode (measured 11-12, Core Ultra 9 285K: ~13.5 s) |
| Judge access | **Test build** = the public GitHub repo plus testing instructions (the rules allow "a website, functioning demo, or a test build"). No hosted instance (owner, 11-12) |
| SAM weights | `sam3.pt` under the SAM License (Meta). Never committed. The README points judges to Meta's official Hugging Face release and the owner's Google Drive mirror (with the licence file), plus size and SHA-256 (§9); without weights the app runs in a clearly labelled no-SAM mode |
| Development and recording | Local or LAN GPU machines only. CPU and hosting are not optimised |
| Availability | Tag `v1.0-submission` on `main`. After 12-04, `main` changes only for fixes that keep the tagged behaviour, until 2027-01-29 |

Because the rules say judges "may choose to judge based solely on the text description, images, and video", the video and README must make the whole case without anyone running the code.

## 3. Feature boundary

### 3.1 In scope (and nothing else)

| ID | Feature | Priority | Acceptance check | Due |
|---|---|---|---|---|
| S1 | `?mode=raw\|lowfreq` on the three slice endpoints, reusing `lowfreq_service` and `_npy_binary_response`; SAM embed can take the low-frequency image | P0 | Same shape and headers as raw; `amplitude.npy` unchanged; unit tests | 11-13 |
| S2 | UI: Raw / Low-freq toggle and side-by-side view; one-click Noisy / Clean pair at the same slice position | P0 | Frames V2 and V3 can be recorded live | 11-15 |
| S3 | `scripts/measure_lowfreq.py`: deep-target vs background contrast, raw vs low-freq, noisy vs clean, fixed seed | P0 | Prints the same numbers on every run; the only source of H1/H2 numbers | 11-16 |
| S4 | `src/qc_service.py`: **label-free** QC of the deep-target mask (edge leakage, envelope contrast inside vs ring outside) and fault continuity; constants declared at module top. Ground-truth overlap from `validation_service` is shown beside it and never feeds the loop | P0 | Monotonic on constructed masks (unit + property tests) | 11-19 |
| S5 | Refinement driver + `POST /api/npy/{vol}/refine`: worst region → corrective positive/negative point, max 3 rounds, early stop, keep best round; round log persisted in SQLite | P0 | Tests cover early stop, best-round keep, log replay; one embed per loop | 11-21 |
| S6 | UI: round-by-round QC panel (score per round, corrective points drawn, best round marked) | P0 | Frame V5 can be recorded live | 11-22 |
| S7 | Degraded paths: no weights → status bar says what is missing and where to get it, browse / low-freq / export keep working; CPU only → visible "encoding on CPU" state; `/propagate` and SAM endpoints return 503 when weights are missing | P0 | Manual run with weights moved away; no blank page, no unhandled 500 | 11-24 |
| S8 | English UI: every button, label, status and error string in the demo flow | P0 | `grep` for CJK characters in `index.html` and `src/static/js/` returns nothing user-visible | 11-25 |
| S9 | Test build: README "Run it" section (prerequisites incl. supported Python 3.10–3.12 and whether Node.js is needed, venv creation, `pip install -r requirements.txt`, data generation, weights download + checksum, start), and `npm run verify` running check + pytest + data verify, with a plain-Python equivalent | P0 | E2 passes on `gpu4090` | 11-26 |
| S10 | Export: GeoJSON + CSV polygons + QC round log (JSON) | P0 | Files open and match the on-screen result | 11-26 |
| S11 | Kiro evidence (see §5) | P0 | Each write-up topic has a real artefact or an honest "not used" | 11-28 |
| S12 | Submission: video ≤165 s, English README final with SGSeg disclosure, Devpost text and testing instructions, `kiro` merged into `main`, tag | P0 | `competition.md` checklist all ticked | 12-03 |

### 3.2 Frozen as is (bug fixes only)

- Volume mask and cross-slice propagation (`.kiro/specs/volume-propagation/`). Touched only by S7 (503) and S8 (English). At most a ~10 s "3-D extension" shot in the video, recorded only after V2–V5 exist (D4).
- Inherited SGSeg features: SEG-Y upload, Zarr / VDS backends, LLM assistant, SQLite sessions. They must keep working; no new work; not in the video.

### 3.3 Out of scope until after 12-04

- Hosted or public instance, CPU latency work, authentication, multi-user.
- Horizon closure error (MVP Requirement 4.1 narrowed; see D2).
- Propagation extensions (negative or box prompts, write locks, low-freq propagation), mask management UI, 3-D rendering, meshes.
- Crossline / timeslice polish beyond what works today.
- New data sources, real field data, fine-tuning.
- Bonus-prize work (separate Kiro Crew app repo, blog, social post) before M4 is complete.
- Refactors not required by an S- or E-item.

## 4. Stability and executability (rules: Functionality, Testing)

| ID | Requirement | Check | Due |
|---|---|---|---|
| E1 | One command proves the build: `npm run verify` = JS syntax + Python AST + preflight + `pytest tests` + data verify | Green on the dev machine before every commit that touches `src/` | 11-26 |
| E2 | Clean clone runs: on a second machine (LAN, ideally Linux), follow only the README from `git clone` to the loaded first screen, with and without weights | Done by the owner or a fresh agent session that has not seen this repo; notes recorded in the S9 task | 11-29 |
| E3 | No unhandled error in the demo flow: every API failure reaches the status bar in plain English | Walk the demo flow with the server stopped mid-way and with weights missing | 11-29 |
| E4 | Repeatable demo: the full flow (S1→S6→S10) runs 3 times in a row without restarting the server or reloading the page | Dry run before recording | 11-30 |
| E5 | Determinism: synthetic data byte-identical (`--verify-only`); QC metrics and refine decisions are deterministic for a given mask; the measurement script prints identical output on reruns | Tests + rerun `measure_lowfreq.py` | 11-23 |
| E6 | GPU end-to-end scripts (`scripts/test_sam_inference.py`, `scripts/test_propagation_e2e.py`, and a new refine e2e) pass before the freeze and before tagging | Run against a live server | 11-29, 12-02 |
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
| M1 H1/H2 visible | 11-12 → 11-16 | Scope + specs committed (11-12); S1 (11-13); `hypothesis` + PBT for lowfreq (11-14); S2 (11-15); S3 (11-16) | V2 and V3 recordable; S3 prints stable numbers | Drop side-by-side, keep the toggle |
| M2 H3 loop | 11-17 → 11-23 | `qc-refine-loop` spec (11-17); S4 + PBT (11-18 → 11-19); S5 (11-20 → 11-21); S6 (11-22); E5 (11-23) | Loop runs live on the deep target; tests green | Drop fault continuity; deep target only |
| M3 Product + test build | 11-24 → 11-29 | S7 (11-24); S8 (11-25); S9 + S10 + E1 (11-26); S11 hooks / agent (11-27 → 11-28); E2, E3, E6 (11-29) | Clean clone works on a second machine with and without weights | Cut S11 to what exists |
| **Feature freeze** | **11-30** | Bug fixes, copy and video only from here | — | — |
| M4 Submission | 11-30 → 12-03 | E4 dry run + record (11-30 → 12-01); README final, `claims-auditor` review, E7 (12-02); merge to `main`, tag, push, Devpost submit (12-03) | Checklist ticked | 12-04 is buffer for form problems only |

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
| SAM3 weights for judges | **Decided:** primary source is Meta's official release (Hugging Face `facebook/sam3`, gated: request access). The owner will provide a Google Drive mirror; the SAM License (1.b.i) allows redistribution only under its terms and with a copy of the licence, so the Drive folder must contain `LICENSE` (SAM License) next to `sam3.pt`. The README gives both links, the expected file name `data/weights/sam3.pt`, size 3,450,062,241 bytes and SHA-256 `9999e2341ceef5e136daa386eecb55cb414446a00ac2b55eb2dfd2f7c3cf8c9e`. **Pending:** the Drive URL |
| Second machine for E2 | **Available:** `ssh gpu4090` (192.168.204.76, user `yuzu`, key `~/.ssh/id_ed25519_huawei`, already in `~/.ssh/config`). Windows 10 Pro for Workstations, RTX 4090 24 GB (driver 617.14), 128 GB RAM, 464 GB free on C:. Has Git; default Python is **3.14**, Python 3.12 available through `uv`; **no Node.js / npm**. Agents may use it only for E2/E6 test runs in a fresh folder under the user's home, and must not install system-wide software without asking |
| YouTube upload (public) and Devpost submission | Owner, by 12-03 |

### What the second machine already tells us (feeds S9 / E2)

- `requirements.txt` pins `numpy<2.0`; NumPy 1.26 has no wheels for Python 3.14, so `pip install` with the default Python on a fresh machine will fail. The README must state the supported Python range (3.10–3.12) and show how to create a venv with it.
- The npm scripts need Node.js, which a geophysicist's machine may not have. The README must either list Node as a prerequisite or give the plain Python commands first.
- SSH sessions on that machine run PowerShell, not a POSIX shell; E2 scripts must be PowerShell.
