# Requirements Document — Volume Mask and Cross-Slice Propagation

## Introduction

SAM segments one 2-D slice at a time. Interpreters work in 3-D. This feature maps each slice mask back onto the seismic volume grid as a voxel mask, and lets the interpreter grow a seed slice into its neighbours by re-prompting SAM automatically, within user-set limits. It extends the MVP spec (`.kiro/specs/samforgeophysics-mvp/`) from slice interpretation to a bounded volume interpretation.

The feature is written after the fact: the code landed in commit `5d7499f` before this spec existed. The requirements below describe the behaviour that code must keep; open gaps are listed as unticked tasks in `tasks.md`.

Terms:

- **volume mask**: a boolean array with the same shape as `amplitude.npy`, `[nIL, nXL, nSamples]`, stored under `data/npy/<vol>/masks/`.
- **seed slice**: the slice of the volume mask the interpreter already segmented with SAM.
- **propagation axis**: the axis normal to the seed slice (IL for inline, XL for crossline, sample for timeslice).
- **propagation box**: an axis-aligned voxel box that bounds where propagation may write.

## Requirements

### Requirement 1 — Write a slice mask into the volume

**User Story:** As an interpreter, I want each SAM result to land in a 3-D mask, so that slice-by-slice work builds a volume interpretation instead of disappearing when I change slice.

#### Acceptance Criteria

1. WHEN a client posts a 2-D mask of any size for `(direction, index)` THEN the system SHALL resample it bilinearly to the slice's native grid, binarise it at `threshold` (default 0.5), and write it into the named volume mask.
2. WHEN `mode` is `replace` THEN the system SHALL overwrite that slice; WHEN `mode` is `union` THEN it SHALL OR the new mask with the existing slice.
3. WHEN the named volume mask does not exist THEN the system SHALL create it as a boolean array with the same shape as `amplitude.npy`.
4. THE system SHALL NOT modify `amplitude.npy`, and SHALL write only under `data/npy/<vol>/masks/`.
5. WHEN a slice is written THEN the system SHALL record, in `<mask_name>.json`, the direction, index, source mask shape, native grid shape, threshold, mode, SAM score, prompt points, slice voxel count and timestamp, plus the total voxel count.
6. IF the mask name, direction, mode or index is invalid, or the mask is empty, not 2-D, or contains NaN/Inf, THEN the system SHALL reject the request with HTTP 400 and leave the stored mask unchanged.
7. IF the volume name does not resolve to a direct child of `data/npy/` containing `amplitude.npy` THEN the system SHALL return HTTP 404 (no path traversal).

### Requirement 2 — Read the volume mask back

**User Story:** As an interpreter, I want to see the stored mask on any slice and know where it sits in survey coordinates, so that I can check a 3-D result without exporting it.

#### Acceptance Criteria

1. WHEN a client requests a mask slice THEN the system SHALL return binary float32 (0/1) with `X-Rows` / `X-Cols` headers, in the same orientation as the matching amplitude slice endpoint.
2. WHEN a client requests mask info THEN the system SHALL return the stored metadata plus the voxel bounding box in index space and, when `meta.json` provides `ilines` / `xlines` / `samples`, the bounding box and centroid in IL / XL / sample coordinates.
3. WHEN a client lists masks for a volume THEN the system SHALL return each mask's name, voxel count and number of written slices.
4. WHEN the interpreter navigates to a slice of an NPY volume where the volume mask is non-empty THEN the UI SHALL draw it as the mask overlay.

### Requirement 3 — Propagate a seed slice to its neighbours

**User Story:** As an interpreter, I want to segment one slice and have the neighbouring slices segmented for me, so that I can cover a target in 3-D without clicking every slice.

#### Acceptance Criteria

1. WHEN propagation is requested for `(direction, index)` THEN the system SHALL use that slice of the named volume mask as the seed; IF the seed slice is empty THEN it SHALL return HTTP 400 telling the user to run SAM on that slice first.
2. THE system SHALL step along the propagation axis in both directions from the seed, at most the half-width for that axis (`max_il`, `max_xl` or `max_vertical`) on each side.
3. THE system SHALL limit the other two axes to the seed mask's bounding box expanded by their half-widths, and SHALL clip every propagated slice to this propagation box before writing.
4. WHEN processing slice `i` THEN the system SHALL derive up to 3 positive point prompts from the previous slice's mask (largest connected component, interior points by distance transform), run SAM on slice `i`, and write the clipped result with `mode = replace`.
5. WHEN the clipped mask is empty, OR its IoU with the previous slice's mask is below `min_iou`, OR the box edge is reached, THEN propagation SHALL stop on that side without writing the failing slice; each side SHALL stop independently.
6. WHEN propagation finishes THEN the response SHALL contain the propagation box, the limits used, a per-slice record (`index`, `side`, `voxels`, `score`, `iou_prev`, `written`, `stopped`), the written indices and the total voxel count.
7. THE defaults SHALL be `max_il = 5`, `max_xl = 5`, `max_vertical = 30`, `min_iou = 0.1`; IF a half-width is negative or not an integer, OR `min_iou` is outside `[0, 1]`, THEN the system SHALL return HTTP 400.
8. WHEN a propagated slice is written THEN its provenance record SHALL mark each prompt point as `propagated_from_<previous index>`.

### Requirement 4 — Interactive use in the UI

**User Story:** As an interpreter, I want propagation to be one button with visible limits, so that I can use it during a live demo without reading the API.

#### Acceptance Criteria

1. WHEN SAM runs on an NPY volume THEN the UI SHALL write the result to the `sam_mask` volume mask and show the total voxel and slice counts in the status bar.
2. WHEN the user presses the propagate button without a SAM mask on the current slice THEN the UI SHALL refuse and tell the user to run SAM first.
3. THE UI SHALL offer a settings panel for the three half-widths and `min_iou`, with each half-width slider capped at its axis length minus one for the loaded volume.
4. WHEN propagation completes THEN the UI SHALL show the number of new slices, the total voxels and the stop reasons; WHEN it fails THEN it SHALL show the server's error message.
5. IF SAM weights are missing THEN propagation SHALL fail with a clear "weights missing" message, and browsing, mask read-back and export SHALL remain usable.

### Requirement 5 — Latency and honesty

**User Story:** As a judge, I want propagation to finish in seconds and its numbers to be checkable, so that the 3-D step is credible in a short demo.

#### Acceptance Criteria

1. THE system SHALL run the SAM image encoder once per image with autograd disabled, cache its features, and reuse them for every prompt on that image.
2. THE system SHALL serialise access to the shared SAM predictor so that concurrent requests cannot mix one image's features with another image's prompts.
3. WHEN README or the video quotes a propagation timing or IoU THEN the number SHALL come from `scripts/test_propagation_e2e.py` (or a successor script) run on the synthetic volume, with the GPU model stated; THE text SHALL NOT present these numbers as a general accuracy benchmark.
