> **Superseded for development work:** read [`guide.md`](guide.md) and `.kiro/steering/scope.md` section 0 first. This file is older (status and plans here may be out of date).

# GEMINI.md — SamForGeophysics (Kiroween 2026)

> Core development and configuration guide for the **SamForGeophysics** competition entry.
> Focused on product delivery and competition submission for the **Kiroween 2026 Hackathon (Devpost, Frankenstein category)**.

---

## 1. Project Positioning and Core Differentiators

- **Positioning**: Stitch the computer-vision foundation model **SAM** onto **seismic exploration interpretation**, combining low-frequency-first conditioning with a low-noise platform to identify deep reflection targets that appear weak, blurred, and nearly "unhearable" to conventional methods.
- **Slogan**: *"With lower frequencies and a cleaner platform, reach for deep targets once deemed 'unhearable' — quiet yourself first, then hear the Earth."*
- **Category**: Frankenstein (stitching together unrelated technologies).
- **Three core differentiators (product highlights)**:
  1. **H1 Low-frequency first**: Weak deep signals remain mainly in the low-frequency band; frequency-preserving / low-frequency enhancement (`lowfreq_service.py`) is applied before prompting SAM while keeping the raw section available for side-by-side comparison.
  2. **H2 Cleaner platform**: Low-noise synthetic volumes (SNR=18dB vs 6dB) verify the decisive impact of higher signal-to-noise ratio on extracting weak targets.
  3. **H3 Self-improving QC loop**: Automatically refines point/box prompts over 2–3 iterations based on geophysical QC metrics such as fault continuity and horizon closure error, emitting a per-round score log.

---

## 2. Repository and Branch Conventions

- **Public repository**: `https://github.com/luziqing/seismic-exploration-system.git`
- **Competition submission branch**: **`kiro`** (judging and Devpost submission branch, tracking `origin/kiro`)
- **Development branch**: `main`
- **Local workspace**: `D:\26tmp\KiroProject\SamForGeophysics\`
- **Open-source license**: MIT (root `LICENSE`, displayed in the GitHub About sidebar)
- **Toolchain targets**: Kiro IDE 1.4.121 / CLI 3.1.0 / Crew 0.12.0

---

## 3. Competition Compliance Rules and Judging Criteria

### 1. Five Judging Criteria (20% each; Design + Presentation = 40%)
- **Technological Implementation** (20%): Deep Kiro usage (Specs / Steering / Hooks / CLI / Crew).
- **Design** (20%): Complete product experience rather than a bare algorithm POC (clear first-screen presentation, comparison layout, status feedback, no-weights fallback path).
- **Innovation / Idea** (20%): Authentic stitching of low-frequency conditioning × cleaner platform × self-improving QC loop.
- **Presentation** (20%): < 3 minute YouTube demo video (end-to-end live workflow, no static slideshow).
- **Potential Impact** (20%): Directly addresses deep weak-target interpretation pain points.

### 2. Hard Compliance Rules
- 🚫 **Never claim "first SAM for seismic"**: Prior work exists (Chen et al. 2024 `arXiv:2407.14121`; Ahmad et al. 2026 `arXiv:2606.15786`); our differentiation lies in low-frequency deep weak targets and the self-improving QC loop.
- 🚫 **Never fabricate unmeasured numbers**: No script, no numbers — every publicly shown metric must be reproducible with a fixed random seed.
- 🚫 **UAV and quantum sensing are background narrative only**: Never claim physical hardware has been implemented.
- 🚫 **Never upload large files or weights**: All `data/*`, `*.npy`, `*.pt`, `*.ckpt`, `*.safetensors` are strictly excluded by `.gitignore`.
- 🚫 **Strict protection of `/.kiro` directory**: `/.kiro` must exist at the repository root and must never enter `.gitignore` (instant disqualification).

---

## 4. Core Data and Interface Contracts

### 1. Seismic Volume and Slice Contracts
- Volume data: `data/npy/<name>/amplitude.npy` (`float32`, C-order, shape: `[nIL, nXL, nSamples]`)
- Metadata: `data/npy/<name>/meta.json`
- Ground-truth masks: `data/npy/<name>/truth/{fault,horizon,deep_target}_mask.npy`
- Slice response: **Unified binary `float32` format**, with `X-Rows` and `X-Cols` response headers (do not introduce JSON variants).

### 2. Core Slice Endpoints
```http
GET /api/npy/{vol}/slice/inline/{i}?mode=raw|lowfreq
GET /api/npy/{vol}/slice/crossline/{j}?mode=raw|lowfreq
GET /api/npy/{vol}/slice/timeslice/{k}?mode=raw|lowfreq
```

---

## 5. Development Roadmap and Current Tasks (Wave 2 -> Wave 5)

```
[Wave 1 Skeleton]   --> [Wave 2 Conditioning & QC]  --> [Wave 3 Self-Improving Loop]  --> [Wave 4 Product & Deploy] --> [Wave 5 Video & Submit]
 (✅ Complete/Green)       (🔥 Current focus)              (Next up)                        (Week 4)                      (Before deadline)
```

### Current Focus: Wave 2 (Low-frequency conditioning & QC evaluation)
1. `src/lowfreq_service.py`:
   - 1D RFFT along the time axis, cosine-taper weighting window (preserves low frequencies, attenuates high frequencies), IRFFT back to float32.
   - Read-only enhancement; never modifies raw volumes on disk.
   - Pure NumPy implementation with built-in standalone verification.
2. Slice endpoint extension:
   - `src/server.py` slice endpoints support `?mode=lowfreq`, returning binary float32.
3. `src/qc_service.py`:
   - Fault continuity metric: cross-trace sample offset and discontinuity penalty.
   - Horizon closure error: closed-loop trace tracking residual (samples / ms).
   - Overlap metrics directly reuse `src/validation_service.py` (Dice, IoU, Precision, Recall).
4. Frontend interaction support:
   - Toolbar adds quick Raw / Low-freq view switching.

---

## 6. Development and Verification Commands (npm run workflow)

The project includes out-of-the-box npm scripts wrapping dev server startup, data generation, syntax checks, and compliance verification:

```bash
# 1. Start local dev server (http://localhost:9339)
npm start             # or npm run dev

# 2. Core checks (runs preflight + data determinism verification automatically)
npm test

# 3. One-shot static checks (frontend JS syntax + backend Python AST + compliance check)
npm run check

# 4. Data generation and determinism re-verification
npm run data:gen      # regenerate synthetic volumes and ground-truth masks
npm run data:verify   # byte-level determinism check only

# 5. Competition compliance check
npm run preflight     # run preflight.py to check .kiro/claims/data
```
