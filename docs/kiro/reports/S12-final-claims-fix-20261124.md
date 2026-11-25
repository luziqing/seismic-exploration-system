# S12: Final claims-audit fixes for README and Devpost

- Branch / commits: `feat/ui-docs` / HEAD
- Files changed:
  - `README.md`
  - `docs/DEVPOST.md`

- What was done, mapped to the ticket (`tickets/2026-11-24-010-final-claims-readme-devpost.md`):
  1. **README Run it step 2:** Removed the unsourced phrase `developed with torch 2.6.0+cu124` while keeping the fresh-machine test statement.
  2. **DEVPOST Inspiration:** Replaced `beneath kilometres of stronger signal and noise` with `below stronger reflections and noise`.
  3. **DEVPOST Challenge 2:** Reworded to state that the UI pick produced a 32-pixel marker mask whereas clean server rendering produced a 521,298-pixel mask, explicitly noting that these pixel counts expose the overlay-corruption bug and are not ground-truth target measurements.
  4. **DEVPOST Accomplishments:** Replaced `following only the README` with `following the README after obtaining the repository bundle`.

- Verification: commands run and their key output:
  - CJK regex check on `README.md` and `docs/DEVPOST.md`: `CJK hits: 0`.
  - `.venv\Scripts\python.exe scripts/verify.py`: `VERIFY OK in 12 s` (JS syntax 9/9, Python AST 15 files parsed, preflight `kiro`/`claims`/`data` OK, `200 passed`, deterministic synthetic volumes verified).

- Numbers used in public text:
  - `32-pixel` and `521,298-pixel`: `.kiro/steering/scope.md` B1 (explicitly qualified as exposing the overlay-corruption bug, not ground-truth target measurements).
  - No new quantitative claims introduced.

- Deviations from this guide or the spec, and why:
  - None.

- Open questions for the owner:
  - None.
