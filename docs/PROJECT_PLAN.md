# SamForGeophysics — Competition Plan (Kiroween 2026 · Frankenstein)

> Public planning summary, aligned with the **verified** official rules (`docs/COMPETITION_RULES.md`, checked 2026-11-08). This document defines **what, why, scope boundaries and acceptance** — not implementation. Execution-level design lives in `/.kiro/specs/`.
>
> **Numbers convention**: `[measured]` = backed by a reproducible run in this repository; `[target]` = a goal that has **not** been achieved yet and must never be presented as a result. No performance figure appears anywhere without a script that reproduces it.

**Priorities**: `P0` must-have (submission or demo breaks without it) · `P1` should-have (directly moves Design / Innovation score) · `P2` optional (never on the critical path).

---

## 1. Positioning and Highlights

**One line**: fuse a **vision foundation model** (built for natural images) with **seismic interpretation** (a domain it was never trained for), and add a self-correcting loop — so weak deep targets that are "unhearable" in the raw section become interpretable.

> Slogan: *"With lower frequencies and a cleaner platform, reach for deep targets once deemed unhearable — quiet yourself first, then hear the Earth."*

**Why this is Frankenstein**: the official category asks for *"a chimera of technologies"*. We stitch three things that do not usually meet — prompt-based visual segmentation, frequency-band reasoning from geophysics, and closed-loop quality control — into one app. The differentiation comes from the stitching, **never** from a first-of-its-kind claim: prior work is cited in `.kiro/steering/sources.md` (Seismic Fault SAM, arXiv:2407.14121; Domain-Guided Prompting, arXiv:2606.15786 — both verified 2026-11-08).

| # | Highlight | In one sentence | Primary judging dimension (20% each) |
|---|---|---|---|
| H1 | **Low-frequency-first** | Deep information survives mainly in the low band; emphasise it before prompting the model, always keeping the raw view for comparison | Innovation/Idea, Potential Impact |
| H2 | **A cleaner platform** | "Platform" here means low-noise data conditioning, shown as a paired high-/low-noise variant of the same geological model — not UAV or quantum hardware | Innovation/Idea, Design |
| H3 | **Self-improving interpretation loop** | After each segmentation round, score fault continuity and horizon closure error, auto-refine prompts for 2–3 rounds, and show the per-round scores live | Technological Implementation, Innovation/Idea, Presentation |

**Out of scope (hard boundaries)**: no first-of-its-kind claims; no UAV / quantum-sensing hardware claims (background narrative only); no proprietary or field data; no model fine-tuning; no real-survey geological conclusions; no multi-user / production deployment; no un-reproducible performance numbers; QC thresholds are declared heuristics, never presented as validated geophysical accuracy.

---

## 2. Scope

### 2.1 Features

| ID | Feature | Priority | Boundary | Acceptance anchor |
|---|---|---|---|---|
| F1 | Load and browse a seismic volume (three orthogonal slice directions) | P0 | Public/synthetic data only; uses the existing data contract | Section visible on cold start with no external resource |
| F2 | High-noise / low-noise paired comparison | P0 | Same geological model, two conditions | One-click comparison in the UI |
| F3 | Low-frequency-first conditioned view | P0 | Read-only enhancement; raw view never modified | Toggle + side-by-side with raw preserved |
| F4 | Point/box prompts → segmentation mask overlay | P0 | Faults, horizons, deep target | Prompt → mask → overlay loop visible |
| F5 | QC-driven self-improving loop (max 3 rounds) | P0 | Early stop when scores stop improving; keep best round | Per-round score log visible in the UI |
| F6 | Overlap metrics against synthetic ground truth | P0 | Demo-data self-evidence only, not a general benchmark | Every score traceable to a log |
| F7 | Result export (polygons + report) | P0 | Uses the existing export capability | Export opens in the demo |
| F8 | Degraded path without weights / network / API key | P0 | Browsing, conditioning and QC stay usable; missing parts stated in the UI | No blank page with weights removed |
| F9 | Product-grade UI and status feedback | P1 | First screen already explains itself; no cosmetic theming | Judge understands without narration |
| F10 | Publicly reachable running instance | P0 | Judges open it directly; credentials in the private form | Official submission requirement |
| F11 | Reproducibility & compliance self-checks | P1 | One command, deterministic + `/.kiro` visibility + claim/data guards | All green before submission |
| F12 | Bonus-prize material (social / blog / Kiro Crew app) | P2 | Only after P0/P1 are done | Off the critical path |

### 2.2 Primary flow (P0, the demo spine)

1. Open the app → first screen already shows a loaded synthetic section.
2. Choose slice direction/position → raw view + status.
3. Switch to the low-frequency view → comparison with raw.
4. Switch noise condition → cleaner-platform comparison.
5. Place positive/negative prompts → run segmentation → mask overlay.
6. QC scores computed → self-improving sub-flow.
7. Per-round scores and best round shown → export polygons + report.
8. One-click self-check entry for judges.

**Self-improving sub-flow**: round 1 uses the user's prompts → locate the worst-scoring region → derive a corrective prompt (positive if under-covering, negative if over-covering) → next round → stop after 3 rounds or when scores stop improving → keep the best round. Thresholds are declared heuristic constants.

### 2.3 Constraints (summary)

Data compliance (public/synthetic only, no weights or large volumes in git) · honesty (no fabricated numbers, no first-claims, no hardware claims) · reproducibility (fixed seed → identical output) · availability (usable with no weights/network/key) · competition compliance (`/.kiro` committed and never ignored; license detectable in the GitHub About section; submission material in English) · accessibility (public running URL; <3 min public YouTube video) · time (under four weeks to the deadline; P2 never blocks P0).

### 2.4 Error boundaries (summary)

Weights missing → explicit message, rest still works · demo data missing/unverifiable → guided generation, demo blocked rather than silently swapped · no network/key → main flow unaffected · QC scores decline → early stop, show honestly · prompt on empty area → undo + visible feedback · inference timeout → keep previous round, no infinite retry · export failure → session preserved · page refresh → recoverable state · determinism broken → loud error pointing at the generator change · forbidden phrasing appears → compliance check fails the build.

---

## 3. Representative Data Instances

All synthetic, deterministic, ground-truthed, licence-clean. The data **is** the argument: it embeds "low frequency carries deep information" and "a cleaner platform helps" as controllable variables.

`[measured]` The generator produces **two variants of the same geological model** — a high-noise ("raw") volume and a low-noise ("clean") volume — with byte-identical reproducibility for a fixed seed, plus ground-truth masks for fault, horizons and the deep target. Three demo instances are carried by these two volumes:

| ID | Geological elements | Carried by | Role in the demo | Expected observable result |
|---|---|---|---|---|
| **D1 baseline** | Gently dipping horizons + a fault offsetting deeper horizons | High-noise volume, **shallow objects** (high SNR at shallow depth) | Baseline "readable section"; validates horizon/fault segmentation | Horizons continuous, fault trace followable |
| **D2 core instance** | A **low-dominant-frequency, weak-amplitude deep target** | High-noise volume, **deep object** | The main show: the target is nearly "unhearable" in the raw view | Masked by noise in raw view; relatively more discernible in the low-frequency view |
| **D3 clean-platform control** | Identical geological model | Low-noise volume, same deep target | Isolates the "cleaner platform" variable | The same target is easier to identify than in D2 |

**Expected results, layered**:

| Layer | Content | Status |
|---|---|---|
| Structural (assertable) | One-command generation, reproducible, truth-aligned, per-round QC logs, raw/conditioned comparison | `[measured]` data side; UI side `[target]` |
| Qualitative (must be confirmed live) | Deep target more discernible in the low-frequency view; easier in the low-noise variant; loop scores change per round | `[target]` — must be confirmed before appearing in any public claim |
| Quantitative | Overlap / continuity / closure numbers per round | **Only script-measured values**, labelled as heuristic thresholds on this synthetic model |
| Forbidden | Pre-set accuracy or improvement percentages; demo-tuned scores presented as benchmarks | — |

---

## 4. Demo Plan

**Total target ≤165 s; hard cap 180 s** (judges are not required to watch beyond three minutes). `[target]`

| Time | Frame | Voice-over point | Judging dimension |
|---|---|---|---|
| 0:00–0:12 | One-line problem + the raw section where the deep target is invisible | Weak deep signal, noise masking, "unhearable" | Potential Impact / Presentation |
| 0:12–0:35 | App first screen with the three representative instances | Fully synthetic, reproducible data | Technological Implementation |
| 0:35–1:05 | **Raw ↔ low-frequency** comparison; D2 ↔ D3 noise comparison | H1 + H2 as separate, visible variables | Innovation/Idea / Design |
| 1:05–1:45 | Prompt interaction → mask overlay → three object classes | A vision foundation model applied to seismic | Technological Implementation |
| 1:45–2:15 | **QC per-round panel**: round 1 → auto-refined prompt → rounds 2/3 score changes | H3, the brightest moment of the demo | Innovation/Idea / Presentation |
| 2:15–2:35 | Export + truth comparison + one-click self-check all green | Verifiable, reproducible, usable result | Design / Potential Impact |
| 2:35–2:45 | Close: positioning, public repo & running link, one line on how Kiro was used | Complete product, deep Kiro usage | Presentation |

**Key frames** `[target ≥ 6]`: V1 raw section (problem) · V2 raw/low-frequency side-by-side · V3 noise-pair comparison · V4 prompt + mask overlay · V5 per-round QC panel with best-round marker · V6 export + truth + self-check · V7 `/.kiro` structure (specs / steering / hooks).

**Judging mapping**: the official process has **two stages** — Stage One is pass/fail (theme fit and required-tool use; failing it means no Stage Two), Stage Two is five equally weighted criteria at 20%: Potential Impact, Technological Implementation, Design, Innovation/Idea, Presentation. The mapping:

| Dimension | What judges ask | Our answer |
|---|---|---|
| Potential Impact | Real problem, real audience, would someone use it | V1 + interpreter scenario; no scope exaggeration |
| Technological Implementation | How deeply and variedly Kiro was used | V7 + README "How Kiro was used" + `/.kiro` artefacts + hook-driven check logs |
| Design | Complete product experience, not a POC | First screen with data, status feedback, comparison layout, F8 degraded path |
| Innovation/Idea | Different from existing concepts | V2/V3/V5 three highlights + cited prior-work positioning |
| Presentation | End-to-end video, clear memorable pitch | Timeline above + slogan + ≤165 s |

The official rules also state *"Insufficient use of Kiro will result in disqualification"* — V7 and the README Kiro section (IDE/CLI/Web/Crew differences, custom agents, automated hook workflows) are P0, not decoration. Design asks for a **complete, coherent product experience**; Presentation asks for the project **working end-to-end** — no stitched static screenshots.

---

## 5. Targets and Acceptance

### 5.1 Quantified targets

| Character | Metric | Value | Evidence |
|---|---|---|---|
| Completeness | Official submission checklist complete | `[target]` 100% | `docs/COMPETITION_RULES.md` item-by-item |
| Completeness | P0 features complete | `[target]` 100% (F1–F8, F10) | `tasks.md` + recording |
| Innovation | Each highlight has its own visible frame | `[target]` 3/3 (V2, V3, V5) | storyboard |
| Innovation | Loop rounds / early stop / log completeness | `[target]` ≤3 rounds, stop-on-plateau, 100% logged | QC logs |
| Feasibility | Cold start to demo state without weights/network/key | `[target]` main flow completes | F8 test |
| Feasibility | Standalone deterministic data generation | `[measured]` byte-identical for fixed seed | self-check output |
| Presentability | Video length / platform / language | `[target]` ≤165 s, public YouTube, English | video link |
| Presentability | Key frames | `[target]` ≥6 | §4 list |
| Presentability | Judge-openable running URL | `[target]` 1 public link | submission form |
| Verifiability | Fixed-seed data consistency | `[measured]` byte-identical | verify-only run |
| Verifiability | Compliance self-checks | `[measured]` all green | self-check output |
| Verifiability | Every public number reproducible | `[target]` 100% (no script, no number) | claims register + run logs |
| Verifiability | Kiro question points covered | `[target]` 3/3 | README section |

### 5.2 Acceptance (P0 pass conditions)

1. **Runs**: from the public link, no weights/login needed to complete the primary flow.
2. **Shows**: V1–V6 appear in the demo, produced by live interaction.
3. **Closes the loop**: per-round QC logs with visible early-stop and best-round logic.
4. **Reproduces**: clone → generate → run matches the video.
5. **Self-proves**: self-checks green; `/.kiro` committed and not ignored; license visible in About.
6. **Submittable**: <3 min English public video, working app URL, Kiro write-up, before the deadline.
7. **Stays honest**: no first-claims, no fabricated numbers, no hardware claims, no proprietary data in any public material.

### 5.3 Scoring target (`[target]` — a direction, not a prediction)

≥8/10 on each of the five criteria, ≥40/50 overall. If any dimension trends below 7, fix that dimension before adding features. Bonus prizes (Best Demo, Social Blitz, Bonus Blog, Best Kiro Crew App) are evaluated only after §5.2 passes.

---

## 6. Public Risk Register

| ID | Risk | Impact | Level | Mitigation |
|---|---|---|---|---|
| RK1 | Official rule: *"Only new projects are eligible … started before October 30 … are not eligible."* This repository is new (first commit 2026-11-08, no inherited history) and all competition-facing work is inside the submission period, but the volume-browser/SAM pipeline was adapted from an earlier open-source project by the same author | Eligibility | High | Disclosed openly in README (Eligibility note) with a precise list of what was built during the submission period; submission wording kept consistent with that disclosure |
| RK2 | No publicly reachable running instance yet | Submission | High | Stage-1 exit condition; provide the URL early |
| RK3 | Model weights cannot ship with a public repo | Feasibility | High | F8 degraded path is P0; documented weight acquisition |
| RK4 | Low-frequency conditioning and the QC loop are still spec-only | Innovation / demo spine | High | Stage-2 P0, ahead of any UI polish |
| RK5 | Any un-reproducible public number violates the honesty constraint | Credibility | High | No script, no number; claims register + compliance check |
| RK6 | All submission material must be English | Compliance | Medium | English README/video/form; this plan is English |
| RK7 | <3-min public video production time | Presentation | Medium | Storyboard above fixed in advance |
| RK8 | *"Insufficient use of Kiro will result in disqualification"* | Disqualification | High | README covers the three official question points; `/.kiro` artefacts + hook logs as evidence |
| RK9 | Under four weeks to the deadline; P2 can crowd out P0 | Global | Medium | Hard stage exit conditions; P2 deferred |

---

## 7. Status Snapshot

| Item | Status |
|---|---|
| New repo, no inherited history; `/.kiro` (3 specs / 6 steering / 3 hooks) committed | `[measured]` |
| Deterministic synthetic generator + truth masks + verify-only | `[measured]` |
| Compliance self-checks (`/.kiro` visibility / forbidden claims / data provenance) | `[measured]` all green |
| Official rules + both prior-work citations verified | `[measured]` 2026-11-08 |
| Low-frequency conditioning, QC self-improving loop | Spec only — Stage-2 P0 |
| Public running instance, demo video, English submission material | Not started — Stage-1/3 P0 |

**Stage discipline**: Stage 1 (compliance & runnable base) → Stage 2 (three highlights, verifiable) → Stage 3 (productisation & submission). A stage's exit conditions must be met before the next begins; P2 is considered only after all three.
