# Requirements Document — SamForGeophysics MVP

## Introduction

Build a demonstrable product that fuses SAM (a vision foundation model) with seismic interpretation to surface weak deep targets. The user loads a synthetic seismic section, emphasises low-frequency content, prompts SAM with points/boxes to segment faults, horizons and deep targets, and watches a QC-driven self-improving loop refine the prompts. All data must be public or fully synthetic, all numbers reproducible, and the whole experience must be presentable in under three minutes.

## Requirements

### Requirement 1 — Load public or synthetic seismic data

**User Story:** As a geophysicist, I want to load a seismic section with one command, so that I can start interpreting without proprietary data or a hidden setup step.

#### Acceptance Criteria

1. WHEN `python scripts/generate_synthetic_seismic.py` is run THEN the system SHALL write `data/npy/<name>/amplitude.npy` as a C-order `float32` array of shape `[nIL, nXL, nSamples]` and a companion `meta.json` containing every key required by `src/npy_service.py`.
2. WHEN the generator is run twice with the same seed THEN the system SHALL produce byte-identical amplitude data, verifiable with `--verify-only`.
3. WHEN the server starts THEN `GET /api/npy/list` SHALL list the generated volume and the three slice endpoints SHALL return binary float32 slices of the expected shapes.
4. IF NumPy is unavailable THEN the generator SHALL exit with a clear, actionable message rather than a traceback.

### Requirement 2 — Low-frequency-first conditioning

**User Story:** As a geophysicist, I want to view the same section with the low-frequency band emphasised, so that weak deep reflectors become visible before I prompt the model.

#### Acceptance Criteria

1. WHEN a slice is requested in low-frequency mode THEN the system SHALL apply a documented band-pass or spectral weighting to that slice and return it without modifying the stored raw volume.
2. WHEN low-frequency mode is toggled THEN the UI SHALL allow side-by-side or toggle comparison with the raw slice.
3. THE system SHALL NOT claim any measured improvement unless a reproducible comparison script prints the measurement.

### Requirement 3 — SAM segmentation with point and box prompts

**User Story:** As an interpreter, I want to click positive/negative points or draw a box, so that SAM segments faults, horizons and deep targets on the displayed section.

#### Acceptance Criteria

1. WHEN the user places include/exclude points and runs segmentation THEN the system SHALL return a mask overlay aligned to the displayed slice.
2. IF model weights are missing THEN the system SHALL show a clear message and keep browsing, prompting and exporting usable.
3. WHEN a mask is produced THEN `src/validation_service.py` SHALL be able to score it against the synthetic ground-truth masks.

### Requirement 4 — QC-driven self-improving interpretation loop

**User Story:** As an interpreter, I want the system to check its own result and retry, so that a poor first segmentation is corrected without me re-prompting manually.

#### Acceptance Criteria

1. WHEN a segmentation round completes THEN the system SHALL compute label-free QC metrics for the deep target (edge leakage, envelope contrast) and fault continuity, log them, and report the ground-truth overlap from `validation_service.py` alongside without using it to drive the loop. (Narrowed 2026-11-12 from "fault continuity and horizon closure error"; see `.kiro/steering/scope.md` D2. Horizon closure error is deferred.)
2. WHEN a round scores below a declared threshold THEN the system SHALL derive a corrective point or box prompt at the worst-scoring location and run another round, up to a maximum of 3 rounds.
3. WHEN scores stop improving THEN the loop SHALL stop early and retain the best round.
4. THE UI SHALL display the round-by-round score log so the improvement is visible in the demo video.

### Requirement 5 — Visualise and export

**User Story:** As an interpreter, I want a clean canvas and an exportable result, so that the workflow ends in a usable artefact.

#### Acceptance Criteria

1. WHEN a mask is displayed THEN the UI SHALL offer the existing display modes and a legible overlay.
2. WHEN the user exports THEN the system SHALL write GeoJSON and CSV polygons as the inherited frontend already does.
3. WHEN the demo is recorded THEN the whole load → condition → prompt → refine → export flow SHALL fit inside a 3-minute script.

### Requirement 6 — Reproducibility and honesty

**User Story:** As a reviewer, I want every claim to be checkable, so that I can trust the submission.

#### Acceptance Criteria

1. THE repository SHALL contain no proprietary field data, model weights, large volume files or software-copyright application material.
2. THE repository SHALL NOT claim "first SAM for seismic"; prior work SHALL be cited only after verification (see `#sources`).
3. WHEN a quantitative claim is made in README or the video THEN a script in `scripts/` SHALL reproduce it with a fixed seed.
4. THE text SHALL NOT present UAV hardware or quantum sensing as implemented.

### Requirement 7 — Demonstrable product experience

**User Story:** As a judge, I want a polished, self-explanatory interface, so that the idea is clear without reading the code.

#### Acceptance Criteria

1. WHEN the app opens THEN the UI SHALL show a loaded synthetic section, an obvious prompt affordance and a visible state/status indicator.
2. WHEN SAM is unavailable THEN the UI SHALL still demonstrate data loading, low-frequency conditioning and QC scoring rather than showing a blank error page.
3. THE README SHALL contain a dedicated section explaining how Kiro specs, steering, hooks, CLI and Crew were used.
