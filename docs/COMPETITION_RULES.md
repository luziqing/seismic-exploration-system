# Kiroween 2026 — Verified Rules Digest

Re-verified **2026-11-12** against the full Official Rules PDF (21 pages, saved locally by the owner from <https://kiroween.devpost.com/rules>; kept under the gitignored `data/rules/`, not redistributed). First verified 2026-11-08 from the web pages. This is a paraphrase with short quotes; where anything conflicts, the Official Rules govern.

## Sources

| Item | URL |
|---|---|
| Hackathon home | <https://kiroween.devpost.com/> |
| Official rules | <https://kiroween.devpost.com/rules> |
| Kiro downloads | <https://kiro.dev/downloads/> |

## Timeline

| Period | Dates (Pacific Time) | Beijing |
|---|---|---|
| Registration | Oct 13 08:30 – Dec 4 14:00, 2026 | |
| Submission | Oct 30 09:00 – **Dec 4 14:00, 2026** | deadline Dec 5 06:00 |
| Judging | Dec 16, 2026 13:00 – **Jan 29, 2027 13:00** | |
| Winners announced | on or around Feb 3, 2027 | |

No extensions, no late submissions. After the deadline the submission cannot be changed (the Devpost portfolio page can).

## Entrants

Individuals of age of majority, teams of up to 3, or organisations. Residents of the listed excluded countries and regions cannot enter; mainland China is not on that list. Up to **4,000 Kiro credits** per entrant on request: request form due **Tue Dec 1, 2026, 12:00 PT**, codes must be redeemed by Dec 4, redeemed credits expire Dec 31, 2026.

## Project requirements

- **What to create:** "a working software application using Kiro (IDE, CLI, Web, and/or Kiro Crew)" in one category. "Insufficient use of Kiro will result in disqualification at the Judges' sole discretion."
- **Frankenstein:** "Stitch together a chimera of technologies into one app."
- **Functionality:** the project must install and run consistently on its intended platform, and work as shown in the video and text.
- **Platforms:** the project must run on the platform stated in the submission.
- **New projects only:** newly created after the submission period starts. Standard frameworks, libraries and starter templates are allowed, but entrants "must disclose any other pre-existing code or work incorporated into the Project. The work described and submitted must have been built during the Submission Period."
- **Third-party integrations:** the entrant must be authorised to use any third-party SDK, API or data under its licence.
- **Ownership / IP:** original work, solely owned by the entrant. Open-source software may be used if its licences are respected and the submission "enhances and builds upon" it.
- **No financial or preferential support** from AWS or Devpost.

## Submission requirements

1. A project built with Kiro that meets the requirements above.
2. **A URL to the functional application.** Credentials and instructions for judges go in the private form field.
3. A text description of features and functionality.
4. **Demo video:** under 3 minutes (judges need not watch beyond 3:00); shows the project running on the device it was built for; public on YouTube; **no third-party trademarks, copyrighted music or other material without permission**.
5. **Public GitHub repo** (not GitLab / Bitbucket) with all source, assets and instructions needed to run it; an open-source licence file that GitHub detects and shows in the About section.
6. **`/.kiro` at the repo root** showing specs, hooks and steering; never in `.gitignore`.
7. Category and bonus categories named.
8. **A write-up on how Kiro was used.** The rules list these prompts: IDE / CLI / Web / Crew and how they differed; custom agents; agent hooks and which workflows they automated; **spec-driven development** (structure, and comparison with vibe coding); **steering** strategy; **MCP**; **property-based testing** (did it catch issues unit tests missed); **Kiro powers**.

## Testing and access (section "Testing")

- Access to the working project must be given "by providing a link to a website, functioning demo, or a test build". A private site needs credentials and testing instructions in the private field.
- The project must stay available free of charge and without restriction for testing **until the judging period ends (Jan 29, 2027)**.
- "Judges are not required to test the Project and may choose to judge based solely on the text description, images, and video provided in the Submission."
- Not providing access when requested may lead to disqualification.

**Implication for this repository:** a hosted site is not the only option; a **test build** (the public repo with one-command setup and testing instructions) meets the access rule. Because judges may never run it, the video and text must carry the whole case on their own.

## Language

All submission materials in English, or with English translations of the video, text description and testing instructions.

## Judging

The Sponsor may use "expert panels, peer review, automated AI-driven analysis, or any combination". Stage One is pass/fail on theme fit and use of the required tools. Stage Two has five equally weighted criteria (10 points each):

| Criterion | What the rules ask |
|---|---|
| Potential Impact | Credible real problem for a real audience; useful, intuitive, accessible; would someone use it |
| Technological Implementation | How thoroughly and skilfully Kiro is used; a deliberate AI-development strategy; variety of Kiro tools used impactfully; deep understanding; experimentation |
| Design | A complete, coherent product experience, not a technical proof of concept; intuitive, polished, intentional |
| Innovation / Idea | Creative and different from existing concepts; unusual technologies or public resources (such as datasets) combined in a new way |
| Presentation | Video shows the project working end-to-end; pitch says what problem, for whom, why it matters; easy to follow; creative and memorable |

Ties are re-scored from scratch with a 20-point scale per criterion.

## Prizes

| Prize | Amount | Notes |
|---|---|---|
| Overall 1st / 2nd / 3rd | USD 30,000 / 20,000 / 10,000 | all categories |
| Best Frankenstein (and each other category) | USD 5,000 | |
| Best Startup Project | USD 10,000 | founder + LinkedIn + startup website |
| Best Ghost of Kiroween Past | USD 2,000 | registered for Kiroween 2025 |
| Best Kiro Crew App | USD 1,000 | **separate** GitHub repo for a Kiro Crew app, created in the period |
| Best Demo | USD 1,000 | highest Presentation score within the top 10% overall |
| Best Student Project (per category) | 1-year Kiro Pro Max | all team members students |
| Bonus Blog | 2,000 Kiro credits ×100 | public post on a third-party platform, mentions Kiroween 2026 |
| Social Blitz | 3-month Kiro Pro+ ×5 | post **starts with** `#KiroweenHackathon26`, during the period |

One Overall **or** one Category prize, plus any number of bonus prizes.

## Prior work — verified via arXiv API and PDF download (2026-11-08)

| Paper | Authors / date | Why it matters |
|---|---|---|
| *Seismic Fault SAM: Adapting SAM with Lightweight Modules and 2.5D Strategy for Fault Detection* — [arXiv:2407.14121](https://arxiv.org/abs/2407.14121) | Ran Chen, Zeren Zhang, Jinwen Ma; 2024-07-19 | States that it applies SAM to seismic fault interpretation for the first time; fine-tunes with adapters and a 2.5D strategy. |
| *Domain-Guided Prompting of the Segment Anything Model for Seismic Interpretation: The Role of Attributes, Visualization, and Hybrid Prompts* — [arXiv:2606.15786](https://arxiv.org/abs/2606.15786) | Aniq Ahmad, Heather Bedle, Ahmad Mustafa; 2026-06-14 | Zero-shot; matches attributes and colormaps to the target and combines sparse point prompts with dense mask prompts. |

**Therefore: never claim "first SAM for seismic".** Our angle is low-frequency deep targets, a cleaner (low-noise) data platform, and a QC-driven self-improving prompt loop.

## Changes since the 11-08 digest

- App access: "website, functioning demo, or a test build" — a hosted instance is optional.
- Availability required until **Jan 29, 2027**, not just the deadline.
- Pre-existing code is allowed **if disclosed**; the work described must be built in the period.
- The Kiro write-up prompts grew from 3 to 8 (spec-driven, steering, MCP, PBT, powers added).
- AI-driven analysis may be part of judging.
- Video must avoid third-party trademarks and copyrighted music without permission.
- Credit request deadline Dec 1, 12:00 PT.
