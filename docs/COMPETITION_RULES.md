# Kiroween 2026 — Verified Rules Digest

Verified **2026-11-08 (Beijing)** against the official Devpost pages (fetched through the local HTTP proxy `127.0.0.1:7897`). This is a paraphrase, not a copy of the Official Rules; if anything conflicts, the Devpost Official Rules govern.

## Sources

| Item | URL |
|---|---|
| Hackathon home | <https://kiroween.devpost.com/> |
| Official rules | <https://kiroween.devpost.com/rules> |
| Kiro downloads | <https://kiro.dev/downloads/> |

## Timeline and prizes

| | |
|---|---|
| Submission period | Oct 30 – Dec 4, 2026 |
| Deadline | Friday, Dec 4, 2026, **2:00 PM Pacific (PST)** = Dec 5, 06:00 Beijing |
| Total prize pool | **USD 100,000** |
| Overall 1st place | **USD 30,000**, 1 winner |

## Categories (submit into one)

Resurrection / **Frankenstein** / Skeleton Crew / Costume Contest.

> Frankenstein: "Stitch together a chimera of technologies into one app. Bring together seemingly incompatible elements to build something unexpectedly powerful."

A project can win one Overall Prize **or** one Category Prize, not both. Bonus Prizes are additive.

## Judging — Stage Two, equally weighted (10 points each)

| Criterion | Weight | What the judges ask |
|---|---|---|
| Potential Impact | 20% | Real problem and audience, useful/intuitive, would someone actually use it |
| Technological Implementation | 20% | **How thoroughly and skillfully Kiro was used**; variety of Kiro tools; experimentation |
| Design | 20% | Complete coherent **product experience, not a technical POC** |
| Innovation/Idea | 20% | Novelty vs existing concepts; unusual technologies or public resources combined |
| Presentation | 20% | Video demonstrates end-to-end; clear pitch; memorable |

Stage One is pass/fail on theme fit and required-tool use. **Design + Presentation = 40%.**

## Submission requirements

- A **working software application** built with Kiro (IDE, CLI, Web and/or Kiro Crew). Official wording: *"Insufficient use of Kiro will result in disqualification at the Judges' sole discretion."*
- **URL to a public GitHub repo** (NOT GitLab/BitBucket) containing all source code, assets and instructions; must be public and open source with an **open-source licence detectable in the GitHub About section**.
- **`/.kiro` directory at the repository root** showing specs, hooks and steering. Official wording: *"Do NOT add the /.kiro directory or sub-folders to your .gitignore, as this could disqualify your submission."*
- **URL to the working app(s)** — judges must be able to run it; any credentials go in the private Devpost form.
- **Demo video under 3 minutes**, uploaded to **YouTube and public** (judges are not required to watch beyond 3 minutes).
- **Written explanation of how Kiro was used.** Suggested prompts: how IDE / CLI / Web / Crew differed, which custom agents were used, and which workflows agent hooks automated.
- All submission materials must be in **English**, or include an English translation.
- Functionality: the project must install and run consistently and work as depicted in the video.

## Eligibility — the hard one

> "Only new projects are eligible. You must build your project during the Submission Period (October 30 to December 4, 2026). Projects you started before October 30, including Kiroween 2025 projects, are not eligible."

Submissions must be the entrant's original work and solely owned by the entrant.

**Implication for this repository:** the new repo's first commit is 2026-11-08 and it inherits no git history from the earlier SGSeg project, but SGSeg itself began in June 2026. Every competition-facing element (low-frequency conditioning, QC self-improving loop, product UI, the whole Kiro workflow) is built after Oct 30. Whether reusing one's own earlier open-source code as a technical base is acceptable is a judgement the human must make — see the risk note in `.kiro/steering/competition.md`. Do not gloss over it in the submission.

## Kiro features the sponsor explicitly names

> "Work across a crew of agents in Kiro Crew, add structure with specs, customize workflows with hooks or steering, streamline with Kiro powers, or bring in new capabilities with MCP."

## Bonus prizes worth considering

- **Best Kiro Crew App** — requires the public GitHub URL of a *Kiro Crew app*; evaluated by the Kiro team from the top 50 eligible submissions.
- **Best Demo** — highest Presentation score among the top 10% overall.
- **Social Blitz** — post with `#KiroweenHackathon26` during the submission period and add the URL.
- **Bonus Blog** — public blog post about Kiro and the project, mentioning Kiroween 2026.
- Also: Best Student Project, Best Startup Project, Best Ghost of Kiroween Past (requires 2025 registration).

## Prior work — verified via arXiv API and PDF download

| Paper | Authors / date | Why it matters |
|---|---|---|
| *Seismic Fault SAM: Adapting SAM with Lightweight Modules and 2.5D Strategy for Fault Detection* — [arXiv:2407.14121](https://arxiv.org/abs/2407.14121) | Ran Chen, Zeren Zhang, Jinwen Ma; 2024-07-19 | Explicitly claims to apply SAM to seismic fault interpretation **"for the first time"**; fine-tunes with lightweight adapters and a 2.5D strategy. |
| *Domain-Guided Prompting of the Segment Anything Model for Seismic Interpretation: The Role of Attributes, Visualization, and Hybrid Prompts* — [arXiv:2606.15786](https://arxiv.org/abs/2606.15786) | Aniq Ahmad, Heather Bedle, Ahmad Mustafa; 2026-06-14 | **Zero-shot**; aligns seismic attributes and colormaps with the geological target and combines sparse point prompts with dense mask prompts from SAM's internal activations. |

Both identifiers resolve, both abstracts were retrieved from the arXiv API, and both PDFs downloaded successfully. **Therefore: never claim "first SAM for seismic".** Our angle is low-frequency deep targets, a cleaner (low-noise) data platform, and a QC-driven self-improving prompt loop.
