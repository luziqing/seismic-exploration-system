# SamForGeophysics — Demo Video Script (≤ 165 s)

> Kiroween 2026 · Frankenstein category.  
> Shot-by-shot script for the demo video. All on-screen footage is live from the local app running on an RTX 4090.

## Constraints
- English only. No copyrighted music or third-party trademarks.
- Every number comes from `docs/MEASUREMENTS.md` with allowed wording. Never invent a number.
- No "first SAM for seismic" or any first / only / novel claim.
- Qualifier "on our synthetic model" wherever a result number appears.
- The low-freq view helps the *interpreter* see; SAM segments the raw slice.
- The loop "checks itself, fixes poor clicks, never keeps a round with a worse QC score" (by QC score).
- SAM segments the RAW slice; Auto-refine ON for NPY. On noisy volume the QC gate stops the loop.
- Propagation shot ≤ ~10 s (D4).

---

## Shot List

| Time | Shot | Visual | Voice-over / text overlay | Notes |
|---|---|---|---|---|
| 0:00–0:04 | **V1a** | Black screen → white text fade-in: "SamForGeophysics" / one-line subtitle | **Text overlay:** "SamForGeophysics — Interpret weak deep targets with SAM3, a low-frequency view and a self-checking QC loop" | Title card. No music. Clean fade. |
| 0:04–0:12 | **V1b** | App opens at `127.0.0.1:9339`. Noisy volume `synthetic_deep_v1`, navigate to inline 20 (box value `20`, title reads IL 21). Camera zooms to the bottom of the section (~430–510 ms). The deep target is invisible in the noise. | **VO:** "A geophysicist opens a synthetic seismic section. Near the bottom, a weak deep target sits below the noise floor — invisible in the raw amplitudes." | Problem statement: "unhearable". Establishes Potential Impact. |
| 0:12–0:20 | **V2a** | Click **Low-freq** button. The section changes: the deep target becomes visible as a distinct bright body in the low-frequency view. | **VO:** "One click switches to the low-frequency view. On our synthetic model, this view separates the deep target from the background — AUC 0.44 to 0.93 on the noisy volume. The model was built with a 10 Hz target." **Text overlay:** "AUC 0.44 → 0.93 on the synthetic noisy volume (script: measure_lowfreq.py)" | H1 moment. Number from `MEASUREMENTS.md` §"Wording for README and video". The model was built with a 10 Hz target — say so. |
| 0:20–0:35 | **V2b** | Choose **Compare → Raw \| Low-freq** to show both side by side. Pan left/right briefly. Then press **Noisy ⇄ Clean** to jump to the clean volume same inline. The target is even clearer. Text overlay appears. | **VO:** "Side by side with raw, you see what the filter reveals. Switching to the clean recording of the same model, the target stands out further — the two effects add up." **Text overlay:** "H1: low-frequency view · H2: cleaner platform" | H1 + H2 together. Shows the comparison UI (Design). Do not claim real-data separability. |
| 0:35–0:50 | **V3** | Set Compare back to **Off**. Press **Raw**. Now on the **clean** volume, navigate to IL 24 (box value `23`). The section is in raw view. | **VO:** "Back to the raw view on the clean volume, inline 24. SAM and the QC loop always work on the raw slice — measured better on the noisy volume. The low-frequency view is for the interpreter's eyes." | Transition to SAM. Explains the design decision: low-freq for humans, raw for SAM. Key constraint. |
| 0:50–1:05 | **V4a** | Press **Include**, click once in the middle of the deep target. Press **▶ SAM** (Auto-refine is on). The mask appears overlaid on the section. | **VO:** "One include click, press SAM. The server renders the slice, SAM3 segments it, and the mask is written into a 3-D volume." | Live SAM interaction. Technological Implementation. The click triggers the full pipeline: embed → predict → mask → volume write. |
| 1:05–1:25 | **V4b / V5a** | The QC panel opens automatically (Auto-refine was on). Round 1 shows its QC score. Rounds 2 and 3 appear as the loop runs. The corrective points (hollow diamonds) are visible on-screen. The best round is marked. | **VO:** "With Auto-refine on, the label-free QC scores the mask — how much leaks past the reflection edge, how much energy it misses. It adds one corrective point at the worst region and runs SAM again, for up to 3 rounds. It checks itself, fixes poor clicks, and never keeps a round with a worse QC score." | H3 — the brightest moment of the demo. Innovation / Presentation. Do NOT say "always improves". |
| 1:25–1:45 | **V5b** | Click different round rows in the QC panel to show their masks. Point out the score changes. The survey map shows the mask footprint. | **VO:** "On the clean synthetic volume, the loop raised the mean IoU of a one-click SAM mask from 0.80 to 0.81 — median 0.88 to 0.89 — improving 9 of 19 slices, worsening 3. It is not guaranteed to improve; on 3 slices, QC preferred a round that was worse against the truth. The QC log records every round." **Text overlay:** "IoU 0.80 → 0.81 (mean), 0.88 → 0.89 (median), clean synthetic volume · script: measure_refine.py" | Numbers from `MEASUREMENTS.md` §"Wording for README and video". Honest framing: state the 3 worse cases. Survey map shows footprint. |
| 1:45–1:55 | **V5c** | Switch to the **noisy** volume, same inline. Press Include, click on the deep target, press **▶ SAM**. The QC panel shows the gate message: the target is too weak for the QC on this slice. | **VO:** "On most noisy slices, the QC gate recognises the target is too weak and declines to refine. It keeps SAM's original mask and says why." | Honesty moment. The gate does its job. Shows degraded behaviour. |
| 1:55–2:10 | **V6a** | Back on the clean volume. Press **Export Mask**. The browser downloads three files: `.geojson`, `.csv`, `qc_log_….json`. Open or preview them briefly. | **VO:** "Export gives you GeoJSON and CSV polygons, plus a JSON log of every QC round — the scores, the corrective points, and which round was kept." | Export + verifiability. Design / Potential Impact. |
| 2:10–2:20 | **V6b** | Press **Propagate**. The mask extends to neighbouring inlines. The survey map updates to show the propagated footprint across multiple inlines. | **VO:** "Propagation extends the mask to neighbouring slices. The survey map tracks the footprint." | Propagation shot ≤ 10 s (D4). Quick, not the focus. |
| 2:20–2:30 | **V6c** | Terminal: run `python scripts/verify.py`. Output scrolls and prints `VERIFY OK`. | **VO:** "One command proves the build: syntax, tests, data determinism — 200 tests, VERIFY OK." | Self-check. Design / Technological Implementation. |
| 2:30–2:40 | **V7** | Show the `.kiro/` directory in the file tree: `specs/` (3 specs), `steering/` (scope, product, tech, structure, competition, sources, seismic-domain), `hooks/` (dev-loop, competition-guards, data-provenance, synthetic-data), `agents/` (claims-auditor). | **VO:** "The project is organised with Kiro: specs written before code — the QC spec's first design failed and the failure is recorded. Steering files set the boundary. Hooks run tests on save, block data commits, and audit claims. A custom agent reviews public text against the measurements." | Kiro evidence — Technological Implementation. Judges look for this. Mention spec-before-code, the failure, hooks and the claims-auditor agent. |
| 2:40–2:45 | **V7b** | Cut to the README section "What is new, and what came before". Highlight the SGSeg disclosure and the two prior-work citations. | **VO:** "The README discloses what came from the author's earlier SGSeg project and what was built here. Prior work on SAM for seismic is cited." | SGSeg disclosure + prior work. Honesty. |

---

## Totals

| Metric | Value |
|---|---|
| **Total duration** | **165 s (2 min 45 s)** |
| **Shots** | V1a, V1b, V2a, V2b, V3, V4a, V4b/V5a, V5b, V5c, V6a, V6b, V6c, V7, V7b |
| **Key frames** | V1 (problem) · V2 (raw/low-freq) · V3 (noise pair transition) · V4 (SAM prompt + mask) · V5 (QC panel + rounds) · V6 (export + propagation + verify) · V7 (.kiro structure + disclosure) |

## Numbers used (all from `docs/MEASUREMENTS.md`)

| Number | Source section | Allowed wording used? |
|---|---|---|
| AUC 0.44 → 0.93 (noisy, raw → low-freq) | §"Deep-target visibility", wording paragraph | Yes — "on our synthetic model, the low-frequency view separates the deep target from the background" |
| Mean IoU 0.80 → 0.81, median 0.88 → 0.89 | §"SAM3 + QC refine loop", wording paragraph | Yes — "on the clean synthetic volume, the label-free QC loop raised the mean IoU…" |
| 9 improved, 3 worsened (of 19) | §"SAM3 + QC refine loop", wording paragraph | Yes |
| Noisy volume: QC gate declined 18/19 | §"SAM3 + QC refine loop", results table | Yes — "declines to run on the noisy volume" |

## Forbidden-claim check

- [x] No "first SAM for seismic" or any first / only / novel claim
- [x] No copyrighted music or third-party trademarks
- [x] No claim of real-data results
- [x] "On our synthetic model" qualifier on all numbers
- [x] Low-freq helps the interpreter, not SAM
- [x] Loop "checks itself, fixes poor clicks, never keeps a round with a worse QC score" — not "always improves"
- [x] SGSeg disclosed; prior work cited
- [x] English only

## Recording notes

- Resolution: 1600 × 900 (toolbar fits in 2 rows at this size).
- Server must be running with SAM3 weights loaded before recording.
- Record live interaction, not stitched screenshots.
- No background music. Voice-over recorded separately and mixed in.
- The text overlays with numbers should stay on screen for at least 3 seconds for readability.
- Run E4 (3 consecutive demo flows) before the recording session.
