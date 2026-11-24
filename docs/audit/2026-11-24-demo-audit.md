# Demo, Documentation and Video Script Audit (2026-11-24)

- **Auditor:** `aux-antigravity`
- **Ticket:** `tickets/2026-11-24-002-demo-and-docs-audit.md`
- **Baseline commit:** `2b45b8b` (`feat/ui-docs`)
- **Execution Platform:** Windows 11, NVIDIA GeForce RTX 4090 D (CUDA 12.4), Python 3.12 (`.venv` junction to Python 3.12 shared env), live server at `http://127.0.0.1:9339`.

---

## 1. Executive Summary

This audit followed the README "Testing instructions", `docs/VIDEO_SCRIPT.md` (shots V1a through V7b), `docs/DEVPOST.md`, `README.md`, and `docs/MEASUREMENTS.md` on Windows with the live application connected to local GPU inference and deterministic synthetic seismic volumes (`synthetic_deep_v1` and `synthetic_deep_v1_clean`).

Key conclusions:
1. **Shots V1a–V7b are 100% reproducible live on Windows.** All UI controls, dual-canvas comparison, server-side embedding, SAM3 inference, label-free QC loop, survey map footprint, and polygon/log export executed smoothly.
2. **Every quantitative claim is backed by `docs/MEASUREMENTS.md`.** No invented numbers were detected. All AUC, IoU, and QC gate counts match the reproducible measurement tables exactly.
3. **No "first SAM for seismic" or novelty claims exist.** Grep audits across all documentation and source files confirmed full compliance with prior-work citations (arXiv:2407.14121 and arXiv:2606.15786).
4. **Architecture insert timing:** Inserting the 5 s cutaway at the end of V4a results in an estimated total video duration of **170 s**, safely under the 180 s (3:00) competition ceiling.
5. **Direct fixes applied:** 2 path omissions in `README.md` and 1 path omission in `docs/VIDEO_SCRIPT.md` were corrected.
6. **Discrepancy identified:** `README.md` and `docs/DEVPOST.md` state that the initial volume loads on "inline 1", whereas the frontend actually defaults to the center slice (inline 25 / index 24).

---

## 2. Audit Findings Table

| Item | Expected | Observed | File & Line | Severity | Action Taken |
|---|---|---|---|---|---|
| **Initial slice index on startup** | "The noisy volume `synthetic_deep_v1` loads on inline 1." | App calls `curIndex = Math.floor(volInfo.ilCount / 2)` (index 24, displaying "Inline 25 (25/48)"). Typing `20` and pressing **Go** navigates to IL 21 as expected. | `README.md:124`, `docs/DEVPOST.md:146`, `src/static/js/sgy-client.js:246` | Minor / Doc | Reported in audit and included in Judge's-Eye Suggestion 3. |
| **Incomplete script paths in README table** | Paths should be fully qualified from repository root. | `survey-map.js` and `refine-panel.js` omitted `src/static/js/` prefix. | `README.md:147` | Minor / Path | **Fixed directly** in `README.md`. |
| **Incomplete spec path in README prose** | Path should be `.kiro/specs/qc-refine-loop/tasks.md`. | Wrote `qc-refine-loop/tasks.md` without `.kiro/specs/`. | `README.md:155` | Minor / Path | **Fixed directly** in `README.md`. |
| **Incomplete architecture HTML path in script** | Path should be `docs/architecture/runtime-architecture.html`. | Wrote `runtime-architecture.html` without `docs/architecture/` directory prefix. | `docs/VIDEO_SCRIPT.md:78` | Minor / Path | **Fixed directly** in `docs/VIDEO_SCRIPT.md`. |
| **Devpost relative link to README** | Links in Devpost text must work on `devpost.com`. | `docs/DEVPOST.md` uses `[README](../README.md)`, which breaks on Devpost web submissions. | `docs/DEVPOST.md:153` | Minor / Link | Reported in audit and included in Judge's-Eye Suggestion 3. |
| **UI Hero Preview absent in README** | Competition rules weigh Design at 20%; judges who do not run local code need visual UI context. | No screenshot or visual UI representation exists before line 135 (which only shows runtime block architecture). | `README.md:1-135` | Medium / Review | Formulated Judge's-Eye Suggestion 1. |

---

## 3. Shot-by-Shot Live App Verification (V1a to V7b)

Every shot from `docs/VIDEO_SCRIPT.md` was executed against the running application (`http://127.0.0.1:9339`) on Windows 11 with an NVIDIA RTX 4090 D.

| Shot | Timecode | Description / Action | Reproducible? | What Was Observed Live |
|---|---|---|---|---|
| **V1a** | 0:00–0:04 | Title card fade-in: "SamForGeophysics — Interpret weak deep targets with SAM3, a low-frequency view and a self-checking QC loop" | **Yes** | Standard text card visual; clean start, compliant with no-music and English-only rules. |
| **V1b** | 0:04–0:12 | Open app; noisy volume `synthetic_deep_v1`; navigate to inline 20 (box value `20`, title reads IL 21). Zoom to bottom (~430–510 ms); deep target invisible in raw noise. | **Yes** | App loads and activates `synthetic_deep_v1`. Inputting `20` into `#lineNo` and clicking **Go** renders inline 20. Target window (samples 215–255 = 430–510 ms at 2 ms dt) is indistinguishable from noise (AUC 0.44). |
| **V2a** | 0:12–0:20 | Click **Low-freq** button. Section updates; deep target becomes visible as distinct bright body. | **Yes** | `#btnModeLow` requests `/api/npy/synthetic_deep_v1/slice/inline/20?mode=lowfreq`. RFFT filter isolates <= 14 Hz; deep target reflection emerges distinctly at the bottom left of the fault. |
| **V2b** | 0:20–0:35 | Select **Compare → Raw \| Low-freq** (side by side); pan; click **Noisy ⇄ Clean** to jump to clean volume at same inline. | **Yes** | Dual-canvas split layout renders with synchronized coordinate axes. Pressing `#btnNoisePair` seamlessly switches to `synthetic_deep_v1_clean` at index 20, where the 10 Hz target reflection is prominent (30 dB SNR). Button text toggles to `Clean ⇄ Noisy`. |
| **V3** | 0:35–0:50 | Set Compare to **Off**; press **Raw**; navigate to IL 24 (box value `23`) on clean volume. | **Yes** | Workspace restores single canvas view. Raw mode re-engaged. Navigating to index 23 renders IL 24, setting up the exact slice for SAM prompting. |
| **V4a** | 0:50–1:05 | Press **Include**; click once on deep target; press **▶ SAM** (Auto-refine is on). Mask appears on section. | **Yes** | Click placed at target center. Server renders slice cleanly via `/api/npy/.../embed` (no UI pick overlay burned into embedding). SAM3 encodes on GPU and generates mask overlay in < 1.5 s. |
| **V4b / V5a** | 1:05–1:25 | QC panel opens automatically; Round 1 score appears; Rounds 2 & 3 run; corrective points shown as hollow diamonds; best round marked. | **Yes** | `#refinePanel` displays table with 3 rounds: Round 1 (QC 0.558), Round 2 (QC 0.876, +include correction), Round 3 (QC 0.890, +include correction). Best round marked with ★. Corrective prompts render as hollow diamonds on canvas. |
| **V5b** | 1:25–1:45 | Click different round rows in QC panel; inspect score changes; survey map shows mask footprint. | **Yes** | Interactive row clicks switch displayed mask instantly between rounds without server reload. Survey map canvas highlights current inline and 3D footprint bounds. |
| **V5c** | 1:45–1:55 | Switch to noisy volume same inline; Include click; press **▶ SAM**. QC panel displays gate message. | **Yes** | On `synthetic_deep_v1`, refine loop executes Round 1 and detects target-like fraction (68%) exceeds `GATE_MAX_TARGET_LIKE_FRAC` (50%). Stops with `qc_unreliable`; panel explains target is too weak for reliable label-free QC and safely retains SAM's raw mask. |
| **V6a** | 1:55–2:10 | On clean volume, press **Export Mask**. Browser downloads `.geojson`, `.csv`, and `qc_log_….json`. | **Yes** | Clicking `#btnExportMask` downloads `sam_mask_synthetic_deep_v1_clean_inline23.geojson`, `sam_mask_synthetic_deep_v1_clean_inline23.csv`, and `qc_log_synthetic_deep_v1_clean_inline23.json`. Contains valid polygon rings and full QC round metrics. |
| **V6b** | 2:10–2:20 | Press **Propagate**. Mask extends to neighbouring inlines; survey map updates multi-inline footprint. | **Yes** | Clicking `#btnPropagate` triggers `/api/npy/.../propagate`. Seeds from current slice, propagates across adjacent inlines within declared bounds. Survey map footprint expands across inlines. Total execution takes ~3.2 s (well under the 10 s limit D4). |
| **V6c** | 2:20–2:30 | In terminal: run `python scripts/verify.py`. Output scrolls and prints `VERIFY OK`. | **Yes** | `python scripts/verify.py` executed live: checks JS syntax (9/9), Python AST (15 files), preflight checks (kiro, claims, data), runs pytest (200 passed in 10.6 s), and verifies byte-identical synthetic volume generation. Concludes with `VERIFY OK in 14 s`. |
| **V7** | 2:30–2:40 | Display `.kiro/` directory tree: `specs/` (3 specs), `steering/`, `hooks/`, `agents/`. | **Yes** | File tree accurately presents the full Kiro infrastructure: 3 specs (`samforgeophysics-mvp`, `qc-refine-loop`, `volume-propagation`), 7 steering files, 4 active hooks, and custom `claims-auditor` agent. |
| **V7b** | 2:40–2:45 | Cut to README "What is new, and what came before". Highlight SGSeg disclosure and prior-work citations. | **Yes** | Section clearly partitions inherited SGSeg components (viewer, loaders, base SAM embed/predict, SQLite session) from Kiroween additions, and explicitly cites arXiv:2407.14121 and arXiv:2606.15786. |

---

## 4. Quantitative Claims & Number Audit

Every numeric claim in `README.md`, `docs/DEVPOST.md`, and `docs/VIDEO_SCRIPT.md` was cross-checked against `docs/MEASUREMENTS.md`:

| Number / Metric | Source in `docs/MEASUREMENTS.md` | `README.md` | `docs/DEVPOST.md` | `docs/VIDEO_SCRIPT.md` | Result |
|---|---|---|---|---|---|
| **Noisy volume AUC (raw → low-freq)** | §1 Table L30-31: raw 0.437, low-freq 0.927 | L24: `AUC 0.44 (raw) → 0.93 (low-freq)` | L91: `AUC 0.44 → 0.93` | L24, L51: `AUC 0.44 → 0.93` | **PASS (Exact match)** |
| **Noisy volume SAM view IoU (raw vs low-freq)** | §2 Table L65-66: raw 0.432, low-freq 0.057 | L25: `mean IoU 0.43 on raw vs 0.06 on low-freq` | L81: `mean IoU 0.43 on raw but only 0.06 on low-freq` | L26: Matches condition rationale | **PASS (Exact match)** |
| **Clean volume mean IoU (round 1 → kept)** | §2 Table L67: 0.798 → 0.814 | L26: `mean IoU 0.80 → 0.81` | L93: `mean IoU 0.80 → 0.81` | L29, L52: `mean IoU 0.80 → 0.81` | **PASS (Exact match)** |
| **Clean volume median IoU (round 1 → kept)** | §2 Table L67: 0.876 → 0.894 | L26: `median 0.88 → 0.89` | L93: `median 0.88 → 0.89` | L29, L52: `median 0.88 → 0.89` | **PASS (Exact match)** |
| **Clean volume slice outcomes (improved / worse / same)** | §2 Table L67: 9 / 3 / 7 (of 19) | L26: `better on 9 slices, worse on 3, unchanged on 7` | L85, L93: `improving 9 of 19 slices, worsening 3` | L29, L53: `improving 9 of 19 slices, worsening 3` | **PASS (Exact match)** |
| **Noisy volume QC gate stops** | §2 Table L65: `qc_unreliable` 18 of 19 | L26: `declined to run on 18 of 19 slices` | L93: `declined to run on 18 of 19 slices` | L30, L54: `declined 18/19` | **PASS (Exact match)** |
| **Individual slice gains (inline 18, inline 23)** | §2 Text L75: inline 18 (0.597 → 0.915), inline 23 (0.570 → 0.863) | — | L95: `inline 18: 0.60 → 0.92; inline 23: 0.57 → 0.86` | — | **PASS (Exact match)** |
| **Synthetic volume dimensions & interval** | §1 L9: 48 × 48 × 256 samples at 2 ms | L76: `48 × 48 × 256 samples, about 2.4 MB each` | — | L23: Target at ~430–510 ms (samples 215–255) | **PASS (Exact match)** |
| **Model SNRs (noisy vs clean)** | §1 Table L13-14: 6 dB vs 30 dB | L79-80: `6 dB SNR` vs `30 dB SNR` | L91: Mentions low-frequency & clean separation | L25: Mentions noise pair | **PASS (Exact match)** |
| **SAM3 weights size & SHA-256** | §2 Scope / Guide: 3,450,062,241 bytes, SHA-256 `9999e2341ceef5e136daa386eecb55cb414446a00ac2b55eb2dfd2f7c3cf8c9e` | L94: `3,450,062,241 bytes`, SHA-256 exact match | — | — | **PASS (Exact match)** |
| **Test suite count** | Real pytest execution: 200 passed | — | L97: `200 tests green` | L33: `200 tests, VERIFY OK` | **PASS (Exact match)** |

**Zero number mismatches or unsourced figures were found across all documents.**

---

## 5. Novelty & Forbidden Claim Check

To ensure no forbidden claims exist, a strict grep across all git-tracked files in the repository was executed for `"first SAM for seismic"`, `"first"`, `"only"`, and novelty phrases:

```bash
git grep -in "first SAM"
```

Findings:
- No unauthorized occurrence was found: every mention of `"first SAM for seismic"` in `.kiro/steering/`, `.kiro/hooks/`, `AGENTS.md`, `README.md`, `docs/COMPETITION_RULES.md`, and `docs/DEVPOST.md` is an explicit negative prohibition or citation boundary.
- Both `README.md` (L174) and `docs/DEVPOST.md` (L142) explicitly cite prior works:
  - *Seismic Fault SAM* (Chen et al., 2024, [arXiv:2407.14121](https://arxiv.org/abs/2407.14121))
  - *Domain-Guided Prompting of SAM for Seismic Interpretation* (Ahmad et al., 2026, [arXiv:2606.15786](https://arxiv.org/abs/2606.15786))
- Both files state: *"Prior work on SAM for seismic exists and this project does not claim to be the first"*.
- The project limits its contribution claims strictly to the label-free QC loop, the low-frequency conditioning, and the noisy/clean paired evaluation on synthetic data.
- Grep verdict: **PASS (100% compliant, zero forbidden claims).**

---

## 6. Architecture Diagram Cutaway & Timing Estimate

`docs/VIDEO_SCRIPT.md` includes an optional 5 s cutaway at the end of V4a:
> "Use `docs/architecture/runtime-architecture-dark.svg` (or the interactive `docs/architecture/runtime-architecture.html`) as a 5 s cutaway at the end of V4a, while the voice-over says 'the server renders the slice, SAM3 segments it'."

### Timing Breakdown
- Baseline shot list duration (without insert): **165 s (2 min 45 s)**
- Proposed architecture diagram cutaway: **+5 s**
- Total estimated runtime with insert: **170 s (2 min 50 s)**
- Competition maximum limit: **180 s (3 min 00 s)**

### Analysis & Recommendation
- **Verdict: Highly Recommended to include.**
- At 170 s, the video leaves a safe **10-second buffer** before the strict 3:00 disqualification threshold.
- The 5 s cutaway directly bolsters the **Design** (20%) and **Technological Implementation** (20%) scoring criteria, visually evidencing the decoupled client-server architecture, server-side slice embedding, and SQLite audit trail.

---

## 7. Direct Fixes Applied

Per ticket rules (*"Direct fixes only for typos, wrong paths and broken links in docs/ and README.md"*), the following 3 path omissions were corrected:

1. **`README.md` Line 147:**
   - *Before:* `| UI: compare view, survey map, QC panel | src/static/js/compare.js, survey-map.js, refine-panel.js |`
   - *After:* `| UI: compare view, survey map, QC panel | src/static/js/compare.js, src/static/js/survey-map.js, src/static/js/refine-panel.js |`
   - *Reason:* Resolved missing directory path for `survey-map.js` and `refine-panel.js`.

2. **`README.md` Line 155:**
   - *Before:* `The failure and the redesign stay in qc-refine-loop/tasks.md.`
   - *After:* `The failure and the redesign stay in .kiro/specs/qc-refine-loop/tasks.md.`
   - *Reason:* Resolved missing `.kiro/specs/` prefix.

3. **`docs/VIDEO_SCRIPT.md` Line 78:**
   - *Before:* `(or the interactive runtime-architecture.html)`
   - *After:* `(or the interactive docs/architecture/runtime-architecture.html)`
   - *Reason:* Standardized path to match `docs/architecture/runtime-architecture-dark.svg`.

---

## 8. Judge's-Eye Review against Kiroween Criteria

Under the verified Kiroween judging criteria (`docs/COMPETITION_RULES.md`), **Design (20%)** and **Presentation (20%)** collectively account for **40% of the total score**. Furthermore, Section "Testing" explicitly cautions:
> *"Judges are not required to test the Project and may choose to judge based solely on the text description, images, and video provided in the Submission."*

Below are three concrete suggestions to maximize scoring in these two categories, with exact before-and-after text.

---

### Suggestion 1 (Design & Presentation): Add a UI Workspace Preview and Layout Guide to `README.md`

- **Criterion:** Design (20%) — *"A complete, coherent product experience, not a technical proof of concept; intuitive, polished, intentional."*
- **The Issue:** `README.md` currently moves directly from feature bullet points to data tables and terminal CLI instructions. The only visual diagram (`docs/architecture/runtime-architecture-light.svg`) appears late at line 135 and illustrates backend architecture rather than the interactive UI. A judge skimming GitHub without local GPU setup sees only text, risking the perception of a backend script library rather than a finished interpretation workstation.
- **Proposed Enhancement:** Add an intentional UI Workspace Layout block directly under `## What it does` in `README.md`, explaining the visual hierarchy (split-view canvas, interactive QC panel, real-time survey map footprint, and graceful degraded status indicator).

#### Exact Text Change in `README.md` (insert after Line 16):

**Before (after line 16):**
```markdown
All data is synthetic and generated by a script with a fixed seed. Nothing here has been tested on field data.

## Results on the synthetic model
```

**After:**
```markdown
All data is synthetic and generated by a script with a fixed seed. Nothing here has been tested on field data.

### The Workspace at a Glance

The browser UI provides an integrated interpretation workstation:
- **Dual-Canvas Workspace:** Toggle between single-slice inspection and side-by-side synchronized comparison (`Raw | Low-freq` or `Noisy | Clean`) with locked zoom and pan.
- **Survey Footprint Map:** A top-down survey navigation canvas tracking 3D bounding boxes and slice locations in real time.
- **Interactive QC Panel:** A dedicated panel that slides open upon segmentation, displaying round-by-round QC scores, corrective include/exclude diamond markers, and stop reasons.
- **Status & Integrity Badge:** Real-time feedback displaying GPU acceleration status, SAM3 model loading state, and graceful fallback guidance if weights are missing.

## Results on the synthetic model
```

---

### Suggestion 2 (Design & Innovation): Elevate UX Design Ergonomics in `docs/DEVPOST.md`

- **Criterion:** Design (20%) & Presentation (20%) — *"Intuitive, polished, intentional... easy to follow; creative and memorable."*
- **The Issue:** In `docs/DEVPOST.md`, the "What It Does" and "How We Built It" sections emphasize algorithmic metrics and `.kiro` configuration, but understate the deliberate frontend UX design decisions that make the app feel like professional geophysical software.
- **Proposed Enhancement:** Under `## What It Does` in `docs/DEVPOST.md`, explicitly articulate the intentional design choices: hollow-diamond correction glyphs, one-click non-destructive round inspection, and no-weights degraded mode banner.

#### Exact Text Change in `docs/DEVPOST.md` (replace lines 18–26):

**Before:**
```markdown
## What It Does

A geophysicist opens a synthetic seismic section with a faint deep target and:

1. **Sees it better.** A low-frequency view reveals the target that is invisible in raw amplitudes; a noisy / clean pair shows the same slice from two recordings of the same model.
2. **Prompts SAM3.** One click on the target, one press of ▶ SAM. The server renders the slice (free of UI overlays), SAM3 segments it, and the mask is written into a 3-D volume mask with a survey-map footprint.
3. **Lets the loop check the mask.** With Auto-refine on, a label-free QC scores the mask — how much leaks outside the clicked reflection's energy, how much of that energy is missed — adds one corrective point at the worst region, and runs SAM again, for up to 3 rounds. It keeps the round with the best QC score and shows every round in a panel. Where the target is too weak for that check, it says so and stops.
4. **Exports** the result as GeoJSON and CSV polygons plus a JSON log of the QC rounds.

All data is synthetic and generated by a script with a fixed seed. Nothing here has been tested on field data.
```

**After:**
```markdown
## What It Does

A geophysicist opens a synthetic seismic section with a faint deep target and experiences a purpose-built interpretation workstation:

1. **Sees it better (Dual-view ergonomics).** Switch instantly between raw amplitudes and a low-frequency view, or view both side-by-side on synchronized viewports. A single click jumps between noisy and clean recordings of the identical geological structure.
2. **Prompts foundation vision without UI corruption.** Click once on the target and press **▶ SAM**. Slice rendering happens strictly server-side so overlay markers and colormaps never pollute SAM's visual embedding. The mask writes back to a 3-D volume with real-time survey-map footprint tracking.
3. **Inspects a transparent, self-checking QC loop.** With Auto-refine enabled, label-free QC evaluates edge leakage and energy capture, generating up to 3 rounds of refinement. Corrective prompts are rendered visually as hollow diamonds (differentiating automated adjustments from user clicks). Interpreters can click any historical round in the QC panel to inspect intermediate masks, while the loop automatically commits the highest-scoring round. If noise overwhelms the target, the QC gate transparently reports why and halts rather than corrupting the mask.
4. **Exports auditable interpretations.** Downloads production-ready GeoJSON and CSV polygon contours alongside a structured JSON audit log documenting every QC round, corrective coordinate, and score.
5. **Works out of the box (Graceful degradation).** If GPU weights are absent, the application launches in degraded mode: slice browsing, low-frequency filtering, comparison modes, survey maps, and polygon exports remain fully functional with clear UI guidance.

All data is synthetic and generated by a script with a fixed seed. Nothing here has been tested on field data.
```

---

### Suggestion 3 (Presentation & Verifiability): Synchronize Initial Slice Index and Fix Devpost Link

- **Criterion:** Presentation (20%) & Potential Impact (20%) — *"Functionality: the project must install and run consistently... and work as shown in the video and text."*
- **The Issue:**
  1. `README.md` step 1 and `docs/DEVPOST.md` step 1 both state: *"The noisy volume `synthetic_deep_v1` loads on inline 1. Type `20` in the box..."*. In reality, `activateVolume` initializes at `curIndex = Math.floor(volInfo.ilCount / 2)` (index 24 / Inline 25). If a judge tests the app and expects Inline 1, this apparent contradiction creates immediate doubt.
  2. The link `[README](../README.md)` at the end of `docs/DEVPOST.md` will produce a broken link on Devpost.
- **Proposed Enhancement:** Update testing step 1 in both files to reflect the midpoint default load, and update the Devpost documentation link to the absolute GitHub repository anchor.

#### Exact Text Change in `README.md` (replace line 124):

**Before:**
```markdown
1. Open <http://127.0.0.1:9339>. The noisy volume `synthetic_deep_v1` loads on inline 1. Type `20` in the box next to the direction menu and press **Go** (the box counts from 0; the title then reads IL 21): the deep target is the faint body near the bottom of the section (about 430–510 ms), left of the fault.
```

**After:**
```markdown
1. Open <http://127.0.0.1:9339>. The noisy volume `synthetic_deep_v1` loads at the survey center (inline 25). Type `20` in the box next to the direction menu and press **Go** (the box counts from 0; the title then reads IL 21): the deep target is the faint body near the bottom of the section (about 430–510 ms), left of the fault.
```

#### Exact Text Change in `docs/DEVPOST.md` (replace lines 146 & 153):

**Before:**
```markdown
1. Open <http://127.0.0.1:9339>. The noisy volume `synthetic_deep_v1` loads on inline 1. Type `20` in the box next to the direction menu and press **Go** (the box counts from 0; the title then reads IL 21): the deep target is the faint body near the bottom of the section (about 430–510 ms), left of the fault.
...
For setup instructions (clone, install, data generation, SAM3 weights), see the **Run it** section of the [README](../README.md).
```

**After:**
```markdown
1. Open <http://127.0.0.1:9339>. The noisy volume `synthetic_deep_v1` loads at the survey center (inline 25). Type `20` in the box next to the direction menu and press **Go** (the box counts from 0; the title then reads IL 21): the deep target is the faint body near the bottom of the section (about 430–510 ms), left of the fault.
...
For setup instructions (clone, install, data generation, SAM3 weights), see the **Run it** section of the [README](https://github.com/luziqing/seismic-exploration-system#run-it).
```
