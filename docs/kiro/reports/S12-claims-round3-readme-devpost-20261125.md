# S12: Claims round 3 fixes for README and Devpost

- Branch / commits: `feat/ui-docs` / HEAD
- Files changed:
  - `README.md`
  - `docs/DEVPOST.md`

- What was done, mapped to the ticket (`tickets/2026-11-25-012-claims-round3-readme-devpost.md`):
  1. **README Results row 3 & DEVPOST Accomplishments (QC loop results):** Updated both to state that the clean-volume raw-view measurement used one simulated include click placed at the interior point of the ground-truth target slice (the pixel farthest from its edge), matching `docs/MEASUREMENTS.md`. All numbers unchanged.
  2. **README "Run it" Platform line:** Replaced `a current Chrome / Edge / Firefox` with `a current desktop browser (tested with Chrome only)`.
  3. **README step 2:** Removed the `+cu124` version expectation from the check comment (`# Check: should print True for CUDA`), keeping the `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124` command line untouched.
  4. **DEVPOST IDE paragraphs:** Reduced both occurrences of `The IDE was used for editing and reviewing [the] code and documents directly.` to `Kiro IDE was also used (owner statement; no separate log is kept).`, keeping CLI statements unchanged.

- Verification: commands run and their key output:
  - CJK regex check on `README.md` and `docs/DEVPOST.md`: `CJK hits: 0`.
  - `.venv\Scripts\python.exe scripts\verify.py`: `VERIFY OK in 12 s` (all 5 steps passed: JS syntax 9/9, Python AST 15 files parsed, preflight `kiro`/`claims`/`data` OK, `200 passed`, deterministic synthetic volumes verified).

- Numbers used in public text:
  - No numbers added or changed; all existing numbers remain traced to `docs/MEASUREMENTS.md`.

- Deviations from this guide or the spec, and why:
  - None.

- Open questions for the owner:
  - None.
