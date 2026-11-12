---
inclusion: always
---

# Competition Rules — Kiroween 2026

> Status: **VERIFIED 2026-11-08** against the web pages and **re-verified 2026-11-12 against the full Official Rules PDF**. Full digest: `docs/COMPETITION_RULES.md`. Boundary and plan: `scope.md`. Where the human's brief differs from the official rules, **the official rules win**.

## Event

Kiro's annual Halloween hackathon on Devpost. Total prize pool **USD 100,000**; Overall 1st place **USD 30,000**. Submission period **Oct 30 – Dec 4, 2026**; deadline **Fri Dec 4, 2026, 2:00 PM PST = Dec 5, 06:00 Beijing**.

Four categories, submit into **one**: Resurrection / **Frankenstein** / Skeleton Crew / Costume Contest. Frankenstein = *"Stitch together a chimera of technologies into one app."* A project wins one Overall Prize **or** one Category Prize, not both; Bonus Prizes are additive.

Judging: Stage One pass/fail (theme fit + required tools), Stage Two five equally weighted criteria at **20% each** — Potential Impact, Technological Implementation, Design, Innovation/Idea, Presentation. **Design + Presentation = 40%.** Official wording: *"Insufficient use of Kiro will result in disqualification at the Judges' sole discretion."*

## Hard requirements (checklist)

- [x] New repository with no inherited git history from the earlier SGSeg project (first commit 2026-11-09 11:35 Beijing, per `git log`)
- [ ] **Public GitHub** repository (NOT GitLab/BitBucket) containing all source, assets and run instructions
- [x] MIT licence at root — must also be **detectable in the GitHub About section**
- [x] `/.kiro` at repo root, committed, never in `.gitignore`; specs / steering / hooks used substantively
- [ ] **Access to the working app**: the rules accept "a website, functioning demo, or a test build". We provide a **test build** (public repo + testing instructions, `scope.md` §2); it must stay runnable until judging ends **2027-01-29**
- [ ] Demo video **under 3 minutes**, **public on YouTube**
- [ ] Written explanation of **how Kiro was used**, covering the rules' prompts: IDE/CLI/Web/Crew, custom agents, hooks, spec-driven, steering, MCP, property-based testing, powers (`scope.md` §5)
- [ ] All submission materials in **English** (README, video, text description, testing instructions)
- [ ] Pre-existing SGSeg code **disclosed**; only work built after Oct 30 described as the project
- [ ] Video: <3 min, shows the app running on the device it was built for, no copyrighted music or third-party trademarks without permission
- [ ] Kiro credits requested before **Dec 1, 12:00 PT**
- [ ] Submit before **Dec 4, 2026, 2:00 PM PST**

## What the sponsor explicitly wants to see

> "Work across a crew of agents in Kiro Crew, add structure with specs, customize workflows with hooks or steering, streamline with Kiro powers, or bring in new capabilities with MCP."

The Kiro-usage write-up is asked to address: how **IDE / CLI / Web / Crew** differed, which **custom agents** were used, and which workflows **agent hooks** automated.

Bonus prizes worth targeting: **Best Kiro Crew App** (requires a public GitHub URL for a Kiro Crew app; evaluated from the top 50), **Best Demo** (highest Presentation score in the top 10% overall), **Social Blitz** (`#KiroweenHackathon26`), **Bonus Blog**.

## Eligibility — pre-existing code

Official rule:

> "Only new projects are eligible. You must build your project during the Submission Period (October 30 to December 4, 2026). Projects you started before October 30, including Kiroween 2025 projects, are not eligible."

The earlier SGSeg project began in June 2026. This repository is new (first commit 2026-11-09, no inherited history) and every competition-facing element — low-frequency conditioning, the QC self-improving loop, product UI, and the whole Kiro workflow — is built after Oct 30, but the volume browser / SAM prompt pipeline was adapted from SGSeg.

The full rules (re-read 2026-11-12) settle the approach: entrants "must disclose any other pre-existing code or work incorporated into the Project. The work described and submitted must have been built during the Submission Period." So we take option (a): present SGSeg as a disclosed pre-existing technical base, list precisely what was built after Oct 30, and describe only that as the project. The owner must still confirm SGSeg is solely theirs (`scope.md` §9). Never overstate originality.

## Data and honesty rules

- Only public or synthetic data in the public repository. No proprietary field data, no weights, no large volumes.
- Cite prior work (both arXiv papers are now VERIFIED in `#sources`); do not claim "first SAM for seismic".
- No invented numbers, benchmarks or performance claims.
- UAV / quantum sensing = background narrative only, never an implemented hardware claim.

## Deliverables beyond code

1. Polished UI (Design, 20%) — judges explicitly want a **complete product experience, not a technical POC**.
2. Short video script and a <3 min public video (Presentation, 20%) — must demonstrate the project working **end-to-end**.
3. README section documenting Kiro usage: which specs drove which features, which steering files constrain agent behaviour, which hooks automated what, and how Kiro Crew / CLI / IDE / Web were used.
4. A test build judges can run: public repo + testing instructions, runnable until 2027-01-29 (`scope.md` §2).
