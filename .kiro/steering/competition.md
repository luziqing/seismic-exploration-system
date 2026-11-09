---
inclusion: always
---

# Competition Rules — Kiroween 2026

> Status: **VERIFIED 2026-11-08** against <https://kiroween.devpost.com/> and <https://kiroween.devpost.com/rules>. Full digest: `docs/COMPETITION_RULES.md`. Where the human's brief differs from the official rules, **the official rules win**.

## Event

Kiro's annual Halloween hackathon on Devpost. Total prize pool **USD 100,000**; Overall 1st place **USD 30,000**. Submission period **Oct 30 – Dec 4, 2026**; deadline **Fri Dec 4, 2026, 2:00 PM PST = Dec 5, 06:00 Beijing**.

Four categories, submit into **one**: Resurrection / **Frankenstein** / Skeleton Crew / Costume Contest. Frankenstein = *"Stitch together a chimera of technologies into one app."* A project wins one Overall Prize **or** one Category Prize, not both; Bonus Prizes are additive.

Judging: Stage One pass/fail (theme fit + required tools), Stage Two five equally weighted criteria at **20% each** — Potential Impact, Technological Implementation, Design, Innovation/Idea, Presentation. **Design + Presentation = 40%.** Official wording: *"Insufficient use of Kiro will result in disqualification at the Judges' sole discretion."*

## Hard requirements (checklist)

- [x] New repository with no inherited git history from the earlier SGSeg project (first commit 2026-11-08)
- [ ] **Public GitHub** repository (NOT GitLab/BitBucket) containing all source, assets and run instructions
- [x] MIT licence at root — must also be **detectable in the GitHub About section**
- [x] `/.kiro` at repo root, committed, never in `.gitignore`; specs / steering / hooks used substantively
- [ ] **URL to the working app(s)** so judges can actually run it (credentials go in the private Devpost form)
- [ ] Demo video **under 3 minutes**, **public on YouTube**
- [x] Written explanation of **how Kiro was used** (README section + the `/.kiro/` contents are the evidence)
- [ ] All submission materials in **English** (README, video, instructions)
- [ ] Submit before **Dec 4, 2026, 2:00 PM PST**

## What the sponsor explicitly wants to see

> "Work across a crew of agents in Kiro Crew, add structure with specs, customize workflows with hooks or steering, streamline with Kiro powers, or bring in new capabilities with MCP."

The Kiro-usage write-up is asked to address: how **IDE / CLI / Web / Crew** differed, which **custom agents** were used, and which workflows **agent hooks** automated.

Bonus prizes worth targeting: **Best Kiro Crew App** (requires a public GitHub URL for a Kiro Crew app; evaluated from the top 50), **Best Demo** (highest Presentation score in the top 10% overall), **Social Blitz** (`#KiroweenHackathon26`), **Bonus Blog**.

## Eligibility risk — human decision required

Official rule:

> "Only new projects are eligible. You must build your project during the Submission Period (October 30 to December 4, 2026). Projects you started before October 30, including Kiroween 2025 projects, are not eligible."

The earlier SGSeg project began in June 2026. This repository is new (first commit 2026-11-08, no inherited history) and every competition-facing element — low-frequency conditioning, the QC self-improving loop, product UI, and the whole Kiro workflow — is built after Oct 30, but the volume browser / SAM prompt pipeline was adapted from SGSeg.

Options: (a) present SGSeg as a pre-existing open-source technical base and document precisely what was built during the submission period; (b) reduce reuse to a minimum and rewrite the core; (c) ask the organisers through the Devpost Q&A. **Do not decide this quietly**, and never overstate originality in the submission.

## Data and honesty rules

- Only public or synthetic data in the public repository. No proprietary field data, no weights, no large volumes.
- Cite prior work (both arXiv papers are now VERIFIED in `#sources`); do not claim "first SAM for seismic".
- No invented numbers, benchmarks or performance claims.
- UAV / quantum sensing = background narrative only, never an implemented hardware claim.

## Deliverables beyond code

1. Polished UI (Design, 20%) — judges explicitly want a **complete product experience, not a technical POC**.
2. Short video script and a <3 min public video (Presentation, 20%) — must demonstrate the project working **end-to-end**.
3. README section documenting Kiro usage: which specs drove which features, which steering files constrain agent behaviour, which hooks automated what, and how Kiro Crew / CLI / IDE / Web were used.
4. A publicly reachable working app URL.
