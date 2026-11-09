---
inclusion: manual
---

# Sources and Claims Register

Reference with `#sources` in chat. **Verified 2026-11-08 (Beijing)** against primary sources fetched through the local HTTP proxy `127.0.0.1:7897`. Full rules digest: `docs/COMPETITION_RULES.md`.

## Prior work on SAM + seismic — VERIFIED

| Paper | Identifier | Authors / published | How it was checked |
|---|---|---|---|
| *Seismic Fault SAM: Adapting SAM with Lightweight Modules and 2.5D Strategy for Fault Detection* | [arXiv:2407.14121](https://arxiv.org/abs/2407.14121) | Ran Chen, Zeren Zhang, Jinwen Ma — 2024-07-19 | arXiv API metadata + abs page + PDF download |
| *Domain-Guided Prompting of the Segment Anything Model for Seismic Interpretation: The Role of Attributes, Visualization, and Hybrid Prompts* | [arXiv:2606.15786](https://arxiv.org/abs/2606.15786) | Aniq Ahmad, Heather Bedle, Ahmad Mustafa — 2026-06-14 | arXiv API metadata + abs page + PDF download |

Both identifiers resolve and both abstracts were retrieved from the arXiv API. Seismic Fault SAM explicitly claims to apply SAM to seismic fault interpretation **"for the first time"** (lightweight adapters + 2.5D strategy). Domain-Guided Prompting is **zero-shot**: seismic-attribute / colormap alignment plus hybrid sparse-point and dense-mask prompts.

**Therefore this project must never claim "first SAM for seismic".** Our differentiator is the low-frequency deep-target angle, a cleaner (low-noise) data platform, and a QC-driven self-improving prompt loop.

Local PDF copies are kept outside the repository and are **not committed** (licensing and size).

## Competition sources — VERIFIED

- Hackathon home: <https://kiroween.devpost.com/>
- Official rules: <https://kiroween.devpost.com/rules>
- Total prize pool **USD 100,000**; Overall 1st place **USD 30,000** (1 winner); deadline **Fri Dec 4, 2026, 2:00 PM PST**.
- Judging: five equally weighted criteria at **20% each** — Potential Impact, Technological Implementation, Design, Innovation/Idea, Presentation.
- Official wording on `/.kiro`: *"must contain the /.kiro directory at the root of the project"* and *"Do NOT add the /.kiro directory or sub-folders to your .gitignore, as this could disqualify your submission."*
- Official wording on eligibility: *"Only new projects are eligible ... Projects you started before October 30 ... are not eligible."*
- Official wording on Kiro depth: *"Insufficient use of Kiro will result in disqualification at the Judges' sole discretion."*

## Kiro product sources (verified reachable 2026-11-08)

- Kiro downloads: <https://kiro.dev/downloads/>
- Kiro Crew: <https://kiro.dev/crew/> — open source, built on Kiro CLI, shares `.kiro` config and ACP.
- Kiro hooks docs: <https://kiro.dev/docs/hooks/> — `.kiro/hooks/*.json`, schema `version: v1`.
- Kiro steering docs: <https://kiro.dev/docs/steering/>
- Kiro specs docs: <https://kiro.dev/docs/specs/>

## Still open / judgement calls

- **Eligibility**: the "only new projects" rule vs. reusing the earlier SGSeg codebase as a technical base. The human must decide how to present it; see `.kiro/steering/competition.md`.
- The exact opening clock time "Oct 30, 09:00 PT" was not independently confirmed. The official page states the submission period as "October 30 to December 4, 2026" and its JSON-LD `startDate` is `2026-10-30T12:00:00-04:00`.
- The 2026-11-09 service-cutoff notice on the downloads page (IDE < 0.11.133 / CLI < 1.28.2) was not re-checked; installed versions are far newer, so this is precautionary only.

## Rule for numbers

Any performance, accuracy, speed or dataset-size number must be produced by a script in this repo with a fixed seed and printed in the run log. Otherwise label it `conceptual` or leave it out.
