# TICKET 2026-11-24-005-readme-ui-preview

- Assignee: aux-antigravity
- Worktree: D:\26tmp\KiroProject\sam-worktrees\sam-antigravity-ui-docs (branch feat/ui-docs)
- Base commit: `kiro` HEAD after the ff-merge done by lead-kiro before dispatch (`git log -1`)
- Goal: Implement Suggestion 1 and Suggestion 2 of your own audit (`docs/audit/2026-11-24-demo-audit.md` section 8) so a judge who never runs the code sees the product, with honest wording only.
- Inputs: your audit section 8; `README.md`; `docs/DEVPOST.md`; `docs/MEASUREMENTS.md`; `guide.md` sections 3 and 10; the running app (README "Run it"). If you start a server, use port **9341** from your worktree; generate data into your worktree with the script; junction weights with `cmd /c mklink /J data\weights D:\26tmp\KiroProject\SamForGeophysics\data\weights` if you need SAM.
- Outputs:
  1. 2 or 3 real screenshots of the app at 1600×900 in `docs/images/` (PNG, each under 400 KB): (a) Compare Raw | Low-freq on the noisy volume, (b) the QC panel with 3 rounds on the clean volume IL 24, optionally (c) the no-weights badge. Captured from the actual app, not mock-ups.
  2. `README.md`: a short "The workspace at a glance" block under "What it does", with screenshot (a) or (b) and one caption line each. Keep it to the features that exist.
  3. `docs/DEVPOST.md` "What It Does": your Suggestion 2, edited for honesty (see rules below).
  4. `docs/kiro/reports/S12-ui-preview-20261124.md` in the guide.md section 10 format.
- Wording rules (lead-kiro review will reject otherwise):
  - No "production-ready", "real-time", "professional", "purpose-built", "seamless" or other puffery. Describe what the UI does.
  - No new numbers. Any number must already be in `docs/MEASUREMENTS.md` with its allowed wording.
  - English only; the CJK grep of guide.md section 6 stays empty.
  - "Works out of the box" is not allowed: the app needs Python setup and 3.5 GB of weights. Say "without the SAM3 weights the app still opens; browsing, the low-frequency view, compare and export keep working" only if you verified it.
- Paths not to touch: `src/`, `.kiro/`, `scripts/`, `tests/`, `data/` (except your local junction, never committed), `docs/MEASUREMENTS.md`, `docs/VIDEO_SCRIPT.md`, the last paragraph of `docs/DEVPOST.md` that links to the README (aux-simple owns that line), other worktrees, main/kiro branches.
- Checklist:
  - [x] Screenshots exist, are under 400 KB each, and show the described state (lead-kiro will open them).
  - [x] README renders the image with a relative path that resolves.
  - [x] `python scripts/verify.py` prints VERIFY OK; CJK grep empty.
  - [x] Server stopped, test masks deleted, `git status` clean after commit.
  - [x] Commit on `feat/ui-docs`: `docs(readme): workspace preview screenshots and Devpost design wording (S12)`. Do not push, do not merge.
- Deadline: 2026-11-26

Do not log in anywhere, do not upload or post anything.

## Report back (filled in by the executor)

- Files touched:
  - `docs/images/workspace-compare-raw-lowfreq.png`: real 1600×900 screenshot of Compare Raw | Low-freq on noisy volume IL 21 (372.9 KB).
  - `docs/images/workspace-qc-panel-clean.png`: real 1600×900 screenshot of 3-round QC refine panel, mask overlay and corrective point on clean volume IL 24 (184.0 KB).
  - `README.md`: added "The workspace at a glance" visual block under "What it does" with relative image links and factual caption lines.
  - `docs/DEVPOST.md`: updated "What It Does" with ergonomics and design explanations, strictly adhering to honest wording rules with all puffery removed.
  - `docs/kiro/reports/S12-ui-preview-20261124.md`: completed report adhering to guide.md section 10 template.
  - `tickets/2026-11-24-005-readme-ui-preview.md`: completed checklist and handoff.
- Test results:
  - Real screenshots captured via headless Chrome CDP at 1600×900 against local server on port 9341 with GPU SAM3 inference.
  - Image sizes: 372.9 KB and 184.0 KB (both strictly < 400 KB).
  - CJK grep across modified markdown files: 0 matches.
  - `python scripts/verify.py`: `VERIFY OK in 12 s` (JS syntax 9/9, Python AST 15/15, Preflight OK, 200 tests passed, Demo data deterministic).
  - Cleanup: test masks deleted, no background processes remaining.
- Not done:
  - None.
