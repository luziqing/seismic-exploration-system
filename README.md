# SamForGeophysics

> *"With lower frequencies and a cleaner platform, reach for deep targets once deemed unhearable — quiet yourself first, then hear the Earth."*

A **Frankenstein**-category experiment: fuse **SAM** (a vision foundation model built for natural images) with **seismic interpretation**, a domain it was never trained for, to make weak deep reflectors interpretable.

## Honest status

This repository is **work in progress**. It is not a finished submission.

| Capability | State |
|---|---|
| Load a seismic volume, browse inline / crossline / timeslice slices, binary float32 API | Available (inherited from SGSeg) |
| Point / box prompts → SAM segmentation → mask overlay | Available (requires weights at runtime) |
| GeoJSON + CSV polygon export, SQLite + localStorage persistence | Available (inherited) |
| IoU / Dice / Precision / Recall against ground truth | Available (`src/validation_service.py`) |
| Deterministic fully synthetic demo data + truth masks | Available (`scripts/`) |
| Low-frequency-first conditioning | Specified, **not yet implemented** |
| QC-driven self-improving interpretation loop | Specified, **not yet implemented** |
| Polished UI and <3 min demo video | Planned |

Full competition plan: `docs/PROJECT_PLAN.md`. See `.kiro/specs/samforgeophysics-mvp/tasks.md` for the live plan. Nothing here is a benchmark: **no accuracy, speed or dataset-size numbers are claimed**.

## What is different

- **Low-frequency-first**: deep information survives mainly in the low-frequency band; we emphasise it before prompting SAM, while always preserving the raw slice for comparison.
- **Cleaner platform**: in this software that means low-noise conditioning of the data, not a physical UAV or quantum sensor. UAV / quantum sensing appear only as background narrative and are **not implemented hardware**.
- **Self-improving interpretation loop**: after each SAM run, score fault continuity and horizon closure error, then automatically refine prompts for 2–3 rounds and show the round-by-round log.

**We do not claim to be the first to apply SAM to seismic data.** Prior work is verified and cited: *Seismic Fault SAM* ([arXiv:2407.14121](https://arxiv.org/abs/2407.14121), Chen et al., 2024) — which itself claims the first application of SAM to seismic fault interpretation — and *Domain-Guided Prompting of SAM for Seismic Interpretation* ([arXiv:2606.15786](https://arxiv.org/abs/2606.15786), Ahmad et al., 2026), a zero-shot attribute/colormap + hybrid-prompting framework. See `.kiro/steering/sources.md` and `docs/COMPETITION_RULES.md`.

## Quick start

### Via npm (recommended)

```bash
npm run data:gen       # generate deterministic synthetic demo volume
npm test               # run compliance checks & verify data reproducibility
npm start              # launch server at http://localhost:8000
```

### Or via direct Python commands

```bash
pip install -r requirements.txt
python scripts/generate_synthetic_seismic.py      # writes data/npy/synthetic_deep_v1/
python scripts/preflight.py --check all
python src/server.py                              # http://localhost:8000
```

Open the app, pick an inline slice, place positive/negative prompt points, run SAM, then export the mask. Model weights are **not** committed — without them, browsing, conditioning and QC still work and the UI says so explicitly.

Verify reproducibility:

```bash
python scripts/generate_synthetic_seismic.py --verify-only
```

## Data policy

Public or fully synthetic data only. `docs/DATA_PROVENANCE.md` documents the generator, the fixed seed, the ground-truth masks and the licence. No field data, no weights, no large volumes in git.

## How Kiro was used

Kiro is used as the development system for this project, not just as an editor. All of the following is committed at the repository root under `/.kiro` and is never gitignored.

| Kiro surface | What it does here |
|---|---|
| **Specs** — `.kiro/specs/samforgeophysics-mvp/` | The three-phase spec (`requirements.md` in EARS-style acceptance criteria, `design.md` with the data-flow sequence diagram, `tasks.md` with wave-grouped tasks) drives every feature. Low-frequency conditioning, QC metrics and the self-improving loop are specified before implementation. Tasks are ticked as work lands. |
| **Steering** — `.kiro/steering/` | `product.md`, `tech.md`, `structure.md`, `competition.md` are always-on constraints. `seismic-domain.md` uses `inclusion: auto` so domain knowledge loads only when relevant code is touched. `sources.md` is `inclusion: manual` (`#sources`) for the claims register. Together they ensure the agent never invents numbers, never claims "first SAM for seismic", and never commits proprietary data. |
| **Hooks** — `.kiro/hooks/*.json` | `competition-guards.json` re-checks `.kiro` visibility whenever `.gitignore` changes and rejects fabricated claims whenever docs/steering change. `data-provenance.json` injects the public-data policy whenever a file under `data/` or `doc/` is saved. `synthetic-data.json` re-runs determinism verification and the full preflight whenever the generator changes. Hooks are shell/agent actions in Kiro's `version: v1` schema. |
| **CLI / Crew** | Kiro CLI V3 provides the same `.kiro` configuration and ACP agent runtime for terminal-driven spec work; Kiro Crew is the persistent workspace used to keep long-running implementation sessions, memory and scheduled checks alive across sessions. |

The hooks call `scripts/preflight.py`, so the constraints are executable rather than decorative. Run `python scripts/preflight.py --check all` to see the same checks Kiro runs automatically.

## Competition checklist (Kiroween 2026)

> Verified **2026-11-08** against the official [hackathon page](https://kiroween.devpost.com/) and [official rules](https://kiroween.devpost.com/rules). Full digest: `docs/COMPETITION_RULES.md`.

- [x] New repository with no inherited git history from the earlier SGSeg project
- [x] Open-source licence (MIT) at the root — must also show in the GitHub About section
- [x] `/.kiro` at the repository root, committed, never in `.gitignore`
- [x] Written explanation of how Kiro was used (this section + `/.kiro` contents)
- [ ] **Public GitHub** repository (not GitLab/BitBucket) with all source, assets and run instructions
- [ ] **Publicly reachable working app URL** so judges can run it
- [ ] Demo video under 3 minutes, public on YouTube
- [ ] All submission materials in English
- [ ] Submit before **Dec 4, 2026, 2:00 PM PST** (Dec 5, 06:00 Beijing)

Prize pool **USD 100,000**; Overall 1st place **USD 30,000**. Judging: Potential Impact, Technological Implementation, Design, Innovation/Idea, Presentation — **20% each**, so Design + Presentation = 40%. Insufficient use of Kiro can disqualify a submission.

**Eligibility note:** the official rules state *"Only new projects are eligible ... Projects you started before October 30 ... are not eligible."* This repository is new (first commit 2026-11-08) and all competition-facing work is built during the submission period, but the volume browser / SAM prompt pipeline was adapted from the earlier SGSeg project. See `.kiro/steering/competition.md` for how to present this honestly.

## Credit

The seismic volume browser, SAM prompt loop and export pipeline were adapted from the earlier SGSeg (Seismic Geological Segmentation) project, an open-source tool by the same author. This repository is a fresh codebase for the hackathon entry; it does not inherit the earlier project's git history or its software-copyright application material. All competition-facing work — the synthetic data generator, low-frequency conditioning spec, QC self-improving loop spec, product UI plan and the entire Kiro specs/steering/hooks workflow — was created after Oct 30, 2026, during the Kiroween submission period.
