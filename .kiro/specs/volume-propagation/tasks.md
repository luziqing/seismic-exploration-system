# Implementation Plan — Volume Mask and Cross-Slice Propagation

> Spec written after the code. Ticked items landed in `5d7499f` / `24583f5` and were verified on 2026-11-09 (RTX 4090 D): `pytest tests` 81 passed, `scripts/test_sam_inference.py` and `scripts/test_propagation_e2e.py` passed against a running server. Tick the rest only after the listed check passes.

## Wave 1 — Volume mask (Requirements 1, 2)

- [x] `src/volume_mask_service.py`: resample to native grid, replace / union writes, memmap storage, provenance JSON, info with IL/XL/sample coordinates, list
- [x] Endpoints `POST /mask`, `GET /masks`, `GET /mask/{name}/info`, `GET /mask/{name}/slice/{dir}/{i}` with volume-path containment
- [x] `tests/test_volume_mask.py`: round trip in all three directions, replace vs union, info coordinates, validation errors
- [x] UI: write each NPY SAM result to `sam_mask`; overlay the stored mask on slice load

## Wave 2 — Propagation (Requirement 3)

- [x] `src/propagation_service.py`: propagation box, interior point prompts, per-side stop on empty / low IoU / box edge, clipped replace writes with provenance
- [x] Endpoint `POST /api/npy/{vol}/propagate` (sync route, runs in thread pool)
- [x] `tests/test_propagation.py` with SAM stubbed
- [x] `scripts/test_propagation_e2e.py`: real SAM seed, default and tightened limits, box containment, error codes

## Wave 3 — Latency (Requirement 5)

- [x] Encoder-feature cache and decoder-only predict in `sam_service.py`, serialised by a process-wide lock
- [x] Encode under `torch.inference_mode()`; regression test `tests/test_sam_service.py` (fixes empty propagation masks and ~3 s predicts)

## Wave 4 — UI (Requirement 4)

- [x] Propagate button and limits panel; sliders capped by volume dimensions; status shows new slices, voxels, stop reasons
- [ ] Map missing-weight errors from `/propagate` (and `/mask` callers) to HTTP 503 and show "SAM weights missing" in the UI (Req 4.5). Check: start without `data/weights/sam3.pt`, press propagate, status names the missing weights; browsing and mask read-back still work
- [ ] English UI strings for the propagate button, panel and status messages (with MVP C1)

## Wave 5 — Hardening and follow-ups

- [ ] Per-mask write lock so concurrent writers cannot drop provenance records. Check: a unit test with two threads writing different slices keeps both records
- [ ] Translate comments and error messages in `volume_mask_service.py` and `propagation_service.py` to English
- [ ] Accept `mode=raw|lowfreq` in propagation once the slice endpoints support it (depends on MVP Wave 2)
- [ ] Before the public instance goes up: decide whether `/mask` and `/propagate` stay enabled, and cap request size for `mask` payloads
- [ ] Decide whether propagation appears in the demo video (CLAUDE.md D4: at most a ~10 s "3-D extension" shot, after H1/H2/H3 are recorded)
- [x] Survey-map footprint endpoint `GET /api/npy/{vol}/mask/{name}/footprint` (voxels per trace, binary float32 `(nIL, nXL)`) and the survey-map panel that shows it (scope S13, 2026-11-12; `tests/test_mask_footprint.py`)
- [x] Fix scope B1: browser SAM clicks wrote an empty seed (the canvas screenshot sent for embedding contained the pick marker). UI now embeds via `POST /api/npy/{vol}/embed` (server-rendered slice); 2026-11-12

## Out of scope

- Negative or box prompts in propagation.
- Mesh or surface extraction from the voxel mask.
- Any accuracy claim for propagation beyond what `scripts/test_propagation_e2e.py` prints on the synthetic volume.
