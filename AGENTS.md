# AGENTS.md — SamForGeophysics

**Start with [`guide.md`](guide.md)**: rules, environment, traps, code map, remaining work and how to report for review.

Read `.kiro/steering/product.md`, `tech.md`, `structure.md` and `competition.md` before changing code. They are the authoritative project constraints for any agent working here.

Non-negotiables:

1. **Public/synthetic data only.** No proprietary field data, model weights or large volumes in git. Demo data comes from `scripts/generate_synthetic_seismic.py`.
2. **No invented numbers.** Every quantitative claim must be reproducible by a script in `scripts/` with a fixed seed.
3. **No "first SAM for seismic" claim.** Prior work exists; see `.kiro/steering/sources.md` (references are UNVERIFIED until checked).
4. **UAV / quantum sensing are background narrative only**, never implemented hardware.
5. **`.kiro/` must stay committed** and never appear as an ignore rule.
6. Follow `.kiro/specs/samforgeophysics-mvp/` (requirements → design → tasks) and tick `tasks.md` as work lands.

Before declaring work done: `python scripts/generate_synthetic_seismic.py --verify-only` and `python scripts/preflight.py --check all`.
