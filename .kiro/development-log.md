# Development log

How SamForGeophysics was built: each iteration, who did it, what failed and how it was corrected, and which decisions shaped it. It links to the evidence in this repository instead of repeating it. Written 2026-11-27 (Beijing time) on baseline `9644378` (`origin/kiro`).

Related records: [`docs/kiro/build-log.md`](../docs/kiro/build-log.md) (Kiro sessions and sub-agents in M2–M3), [`docs/kiro/KIRO_USAGE.md`](../docs/kiro/KIRO_USAGE.md) (Kiro features), [`docs/kiro/reports/`](../docs/kiro/reports/) (one report per finished task), [`tickets/`](../tickets/) (the multi-agent work orders from 11-24), [`.kiro/steering/scope.md`](steering/scope.md) (boundary and decisions D1–D4).

## How to read this log

| Status | Meaning |
|---|---|
| **Done** | In `origin/kiro`, with a commit and a report, ticket or test as evidence |
| **Verified only** | Independently accepted on its own branch, not yet integrated into `kiro` |
| **Candidate** | Proposed on a branch, waiting for independent acceptance |
| **Outside the repository** | Real work with no git evidence (for example video files); described, not linked |

Evidence rules:
- Every commit in this repository is authored by the owner's account. Git therefore does not show which agent did the work. Roles below come from the `Assignee` field of each ticket, from the agents' own reports, and from summaries the participants gave on 2026-11-27. Where those sources do not settle a point, the log says so.
- Numbers about results are only those in [`docs/MEASUREMENTS.md`](../docs/MEASUREMENTS.md). Test counts and verdicts are quoted from the linked reports.
- No session transcripts, credentials or machine-specific paths are reproduced here.

## Participants and roles

| Participant | Role | Where its work is recorded |
|---|---|---|
| Owner | Scope decisions, SGSeg ownership (D1), Kiro surfaces used, merges to `main` (release step) | `scope.md` §8–9, commit messages |
| Kiro CLI sessions (with Kiro IDE for editing) | M1–M3 implementation, specs, steering, hooks, the `claims-auditor` agent, measurements. From 11-24, ticket acceptance ("lead-kiro acceptance" merges) and, on 11-26/27, planning and decisions for the English cleanup | `build-log.md`, `KIRO_USAGE.md`, merge commits |
| Kiro sub-agents | Parallel M3 work (English UI, server messages, export), Kiro format checks, the E2 clean-clone test | `build-log.md` |
| `claims-auditor` (custom Kiro agent, read-only) | Audits README, Devpost text and video script against `MEASUREMENTS.md` | `docs/kiro/claims-audit-*.md` |
| Codex (`aux-codex`, branch `feat/sam-seg`) | Refactor 001, E4 browser and GPU checks 004/007, video-script claims fixes 011/013 | Tickets 001, 004, 007, 011, 013; reports `E4-*`, `S12-claims-round3-video-*` |
| Antigravity (`aux-antigravity`; branches `feat/ui-docs`, `fix/llm-integration`, `chore/en-cleanup`) | Demo and docs audit 002, README preview 005, README/Devpost claims fixes 008/010/012, UI-EN, LLM fix, English cleanup | Tickets 002, 005, 008, 010, 012; reports `S12-*`, `LLM-FIX-*` |
| OpenCode (`aux-simple`, branch `chore/simple`) | Link check 003, Devpost links 006, first video-script claims fix 009; from 11-26, independent acceptance of UI-EN and the LLM fix | Tickets 003, 006, 009; acceptance summaries below |

Kiro Web and Kiro Crew were not used. The other agents ran as separate tools on their own git worktrees and branches. Each branch was merged into `kiro` only after its ticket's checks were accepted.

## Iterations

### I0 · 2026-11-09 · Wave 1: new repository and guard rails · Done

First commit `552100e`, the start of the project's git history. It added the scaffold and `/.kiro` with one spec (`samforgeophysics-mvp`), six steering files and three hooks. The other two specs came later: `volume-propagation` in `f8d5f61` and `qc-refine-loop` in `cfed1f6`. The commit also added the deterministic synthetic data generator, `scripts/preflight.py` and the data-provenance document. Follow-ups `e984f45`…`f0ad826` set the volume switcher, the default port and npm scripts. The volume browser and SAM base pipeline were adapted from the owner's earlier SGSeg project, which is disclosed in the README (decision D1).

### I1 · 2026-11-12 · M1: low-frequency view and noisy/clean pair (H1, H2) · Done

| Item | Commits |
|---|---|
| Rules re-read; scope boundary fixed | `e242e13`, `f72acc0` |
| S1 `?mode=raw\|lowfreq` on the slice endpoints | `ee9c0c5` |
| S13 survey map | `b405c96` |
| S2 Raw / Low-freq toggle, compare view, noisy/clean pair | `20529e9` |
| S3 `measure_lowfreq.py` (H1/H2 numbers) | `43a0da7` |
| SAM3 weight source: Meta's official release, checksum recorded | `20bd12a`, `7977146`, `251992d`, `05dc942` |

**Failure and correction (B1).** A SAM click in the browser wrote an empty seed, so propagation failed. The cause: the browser embedded a screenshot of the canvas, and SAM segmented the pick marker drawn on it. Fix `4046d88`: a new `POST /embed` renders the slice on the server. Recorded in `scope.md` §3.1 B1 and `tests/test_npy_embed.py`.

### I2 · 2026-11-12 · M2: label-free QC loop (H3), spec before code · Done

| Step | Commit |
|---|---|
| `qc-refine-loop` spec written before any code | `cfed1f6` |
| QC as first declared; the commit records that it fails Requirement 1.3 | `e197d27` |
| Redesign C: QC relative to the clicked envelope (owner's choice) | `f0d2504` |
| Decision A: QC on the raw view with a reliability gate | `0dd0711` |
| Loop driver, then API with SQLite round log and replay | `603501b`, `7abab5d` |
| `measure_refine.py`, protocol declared, run once | `51cd1a7` |
| S6 QC panel | `4e756e9` |

**Failure and correction.** Property tests found that adding background pixels to an exact mask *raised* its score in the first QC design, and ground truth did not rank best on the demo checks. The spec was changed first, then the code (details in `.kiro/specs/qc-refine-loop/tasks.md` and `KIRO_USAGE.md`). The single measurement run then set two UI defaults: SAM segments the raw slice, and Auto-refine is on. Its weaknesses are recorded as limitations in `MEASUREMENTS.md`, not redesigned (scope §0 rule 1).

### I3 · 2026-11-12/13 · M3: product and test build · Done

| Item | Commit |
|---|---|
| English UI, toolbar declutter, no-weights mode, export with QC log (S8, S7, S10) | `ddc2c69` |
| Hooks, `claims-auditor`, `verify.py`, README run and Kiro sections (S9, S11, E1) | `798fa28` |
| E2 clean-clone fixes, first claims audit, build log | `ce73c50` |
| `guide.md` for development agents; README method section; Kiro write-up moved to `KIRO_USAGE.md` | `fa14372`, `0050b44`, `248721f` |

**Failures and corrections.**
- The first `claims-auditor` run failed the README with 7 items, which were fixed ([`claims-audit-2026-11-12.md`](../docs/kiro/claims-audit-2026-11-12.md)).
- The E2 clean clone on a second machine exposed five README and requirements problems, all fixed (`build-log.md`, E2).
- The new layout caused a pick-position bug, which the export sub-agent reported and the main session fixed (`build-log.md`).

### I4 · 2026-11-18 · S12 drafts · Done

Drafts of `docs/VIDEO_SCRIPT.md` and `docs/DEVPOST.md` (`a3406e9`).

### I5 · 2026-11-24/25 · Multi-agent tickets · Done

Tickets were opened in `2b45b8b` (001–003), `3fd6fee` (004–006), `5fc65ef` (007), `1c35a90` (008–009), `c34996d` (010–011) and `91f28df` (012–013). Each ticket names an assignee, a worktree, inputs, paths not to touch, a checklist and a report back. Each fix landed as its own commit and was accepted into `kiro` as a separate merge.

| Ticket | Work | Assignee | Fix commit | Accepted in |
|---|---|---|---|---|
| 001 | Refactor `refine_service.run` / `sam_service.predict_mask_np` into helpers, behaviour unchanged | Codex | `b4f8273` | `a112016` |
| 002 | Demo and docs audit | Antigravity | `521bff0` | `2974661` |
| 003 | Link check | OpenCode | `3a152df` | `2f1f9b3` |
| 004 | E4: three demo cycles on real SAM3/GPU after the refactor | Codex | `f0cd90b` | `a48c1f8` |
| 005 | README workspace preview | Antigravity | `cd9ec2c` | `eadd4e3` |
| 006 | Devpost absolute links | OpenCode | `bc9389b` | `1cca5d1` |
| 007 | Skip mask requests when no volume mask exists (E4 follow-up) | Codex | `4bda0dd` | `02f7f18` |
| 008 | README/Devpost claims fixes, round 1 | Antigravity | `cda5e97` | `6b9addd` |
| 009 | Video-script claims fixes, round 1 | OpenCode | `fd0571f` | `719a853` |
| 010 | README/Devpost claims fixes, round 2 | Antigravity | `cda8528` | `5883881` |
| 011 | Video-script claims fixes, round 2 | Codex | `cab357b` | `05c0e75` |
| 012 | README/Devpost claims fixes, round 3 | Antigravity | `bec27ca` | `b14966c` |
| 013 | Video-script claims fixes, round 3 | Codex | `0aafc46` | `c329fa2` |

**Failures and corrections.**
- **001:** the isolated worktree had no demo data or weights, so `verify.py` stopped at its demo-data step. Temporarily generated synthetic data passed the byte check and was removed. Codex reports 199 passed / 1 skipped before and after the refactor. The GPU end-to-end check moved to ticket 004.
- **004 → 007:** the three demo cycles completed on real SAM3, but saved-mask lookups returned HTTP 404 before the first mask was written, so the console criterion failed ([`E4-20261124.md`](../docs/kiro/reports/E4-20261124.md)). Ticket 007 skipped those requests when no mask exists. The rerun passed three cycles on one page with 0 page or console errors, apart from the favicon 404 ([`E4-20261125.md`](../docs/kiro/reports/E4-20261125.md), `tests/test_e4_browser.cjs`).
- **E7 claims:** the `claims-auditor` run of 2026-11-24 failed with 20 items (README 3, Devpost 10, video script 7) ([`claims-audit-2026-11-24.md`](../docs/kiro/claims-audit-2026-11-24.md), commit `1c35a90`). Three rounds of fix tickets followed, split into README/Devpost and video script. They tightened the synthetic-data conditions on every metric, the wording of the measurements, the SGSeg disclosure and the Kiro coverage claims (reports `S12-claims-fix-20261124.md`, `S12-final-claims-fix-20261124.md`, `S12-claims-round3-*-20261125.md`). No `claims-auditor` PASS after round 3 is committed, so E7 stays open in this log.
- **Data check in the video tickets:** in the worktrees of tickets 011 and 013, `generate_synthetic_seismic.py --verify-only` reported `regenerated bytes differ from stored`. The cause is not established and no data was changed ([`S12-claims-round3-video-20261125.md`](../docs/kiro/reports/S12-claims-round3-video-20261125.md)). The `verify.py` runs in the other reports passed their data step.

### I6 · 2026-11-26 · UI-EN and the LLM connection fix

| Item | Status | Evidence |
|---|---|---|
| **UI-EN**: the initial plot subtitle was a leftover SGSeg example ("Line no.=1511 (Panel=467)"), now "No volume loaded". Before the change, a scan of `index.html`, `src/static/**` and `src/*.py` already showed 0 Chinese characters | **Verified only**: commit `5253a64` on `feat/ui-docs`, not in `kiro` | Report `UI-EN-20261126.md` (on that branch). Independent acceptance by OpenCode: 7 of 7 criteria passed, including `verify.py` 200 passed and a headless-browser check of five UI states with no Chinese characters and no console errors |
| **LLM fix**: `_chat_openai` had been missing since the first commit, so the OpenAI-compatible and local providers failed. Restored, plus a test-connection endpoint and English error handling | **Done**: `3478da4`, merged as `9644378` | [`LLM-FIX-20261126.md`](../docs/kiro/reports/LLM-FIX-20261126.md); OpenCode's independent acceptance: `verify.py` 212 passed; mocked and real OpenAI-compatible checks; Anthropic checked with mocks only |

How the UI-EN gap was found: Kiro planned the task from a read-only scan, Antigravity made the change, and OpenCode accepted it. That plan deliberately left British spelling, the inherited LLM prompt name and the code files' Chinese comments unchanged; the comments were translated later, in I8. While accepting UI-EN, OpenCode also found the LLM defect, which led to the fix above.

The participants' accounts differ on which session ran the `9644378` merge, and git does not record it, so it is left unattributed.

### I7 · 2026-11-26/27 · Demo video · Outside the repository

The planned script is in [`docs/VIDEO_SCRIPT.md`](../docs/VIDEO_SCRIPT.md). Two cuts were made outside the repository: a 3:00 English screen-recording version, and a 2:20 hand-drawn animation. The animation was drawn in code by a Kiro CLI session from the real synthetic sections, the SAM3 refine rounds stored by the app and the `MEASUREMENTS.md` numbers. Antigravity made an original music track.

**Correction.** OpenCode's review found that the comparison scene showed *Noisy · Raw | Clean · Low-freq*, a pair the app cannot display. Antigravity confirmed this, and the scene was redrawn to follow `compare.js` `compareTarget()` and the toolbar in `index.html`. Only that scene changed. The rest of the video and the audio are bit-identical to the earlier cut.

The video files, their production notes and the review notes stay outside the repository and are not published yet. Nobody has watched and listened to the video at normal speed.

### I8 · 2026-11-27 · English cleanup and this log · Candidate

- **Translation (Antigravity, branch `chore/en-cleanup` from `9644378`), two commits:**
  - `68c94fd`, documents. `CLAUDE.md`, `GEMINI.md`, `tickets/TEMPLATE.md` and tickets 001–011 are translated into English, keeping every command, path, commit ID and number. The mojibake in `docs/kiro/claims-audit-2026-11-24.md` (UTF-8 symbols mis-decoded) is repaired.
  - `4b286f8`, tests and end-to-end scripts. Comments, docstrings, printed messages and assertion messages are translated. With every string constant replaced by a placeholder, the code's syntax tree is unchanged, so behaviour is the same. No test inputs or expected values changed; 212 tests passed.
  - The two E4 reports keep the scripts' former Chinese output verbatim, as evidence, with an English gloss.
- **This log (Kiro, branch `docs/dev-log` from `9644378`):** a separate commit.
- The three commits are combined into one candidate branch and accepted by OpenCode from a clean checkout before integration.

## Design and process decisions

| Decision | When | Source |
|---|---|---|
| Pre-existing SGSeg code is disclosed. Only work built after 10-30 is described as the project | 11-12 | `scope.md` D1 |
| Requirement 4.1 narrowed to label-free deep-target QC plus fault continuity. Horizon closure deferred | 11-12 | `scope.md` D2 |
| Test build instead of a hosted instance | 11-12 | `scope.md` D3 |
| QC redesign C, then decision A (raw-view QC with a reliability gate) | 11-12 | `qc-refine-loop/tasks.md` |
| One measurement run decides the UI defaults (raw slice for SAM, Auto-refine on) | 11-12 | `MEASUREMENTS.md`, `scope.md` §0 |
| Convergence rules: no redesign after M3; weaknesses become recorded limitations | 11-12 | `scope.md` §0 |
| Work split into tickets on separate worktrees per agent; one commit per fix; acceptance merge per ticket; `main` changed only at release | 11-24 | `tickets/`, merge commits, `guide.md` §3 |
| Claims fixes split by document (README/Devpost vs video script) after the FAIL 20 audit | 11-24 | `1c35a90`, tickets 008–013 |
| Executor and acceptor are different agents, and acceptance runs in a separate worktree | 11-26 | UI-EN and LLM-fix acceptance |
| Translate the Chinese comments and script output in the test and e2e files, after the owner asked for the cleanup | 11-27 | `4b286f8` |

## Open and candidate items

| Item | Status | Next step |
|---|---|---|
| UI-EN `5253a64` (`feat/ui-docs`) | Verified only | Integrate into `kiro` as its own merge. Not part of the English-cleanup candidate |
| English cleanup (`68c94fd`, `4b286f8`) + this log | Candidate | OpenCode acceptance from a clean checkout |
| Chinese text kept on purpose, each line with a reason: detection patterns in `scripts/preflight.py` lines 25 and 32 (removing them would stop the check from catching Chinese wording of forbidden claims); `docs/architecture/runtime-architecture.html` (14 lines of generator template comments and one CSS selector, `q:lang(zh)`, in a generated file); the quoted former script output in `docs/kiro/reports/E4-20261124.md` lines 12–13 and `E4-20261125.md` lines 18 and 20, which is evidence and carries an English gloss | Kept | None |
| Final `claims-auditor` PASS on README, Devpost and video script (E7) | Open | Run the audit and commit its log |
| `--verify-only` byte mismatch seen in the video-ticket worktrees | Open, cause unknown | Reproduce on a clean clone before tagging |
| LLM fix: real Anthropic success path untested; `requirements.txt` still lists `anthropic` / `openai` although the runtime uses `httpx`; the LLM report names an internal gateway host | Open | Owner decision |
| Video: 1× human viewing and listening; loudness is low for YouTube (owner's choice); publication | Outside the repository | Owner |
| `GEMINI.md` (older agent notes, kept as translated) gives the clean volume as 18 dB; the volumes are 6 dB and 30 dB (`MEASUREMENTS.md`) | Open, predates the translation | Owner decides whether to correct the older notes |
