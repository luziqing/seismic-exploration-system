# Recorded SAM3 + QC Refine Runs (Provenance)

Generated from the live local FastAPI + SAM3 server using the exact click rule in `scripts/test_refine_e2e.py` (`write_mask: false`).

- **Date**: 2026-11-27
- **Git commit SHA**: `fcd4e8e6b380504f3d1ac4adc3551c3b7b9fbb80`
- **Device / GPU**: `NVIDIA GeForce RTX 4090 D` (`sam_device=cuda`)

## Runs

### refine_clean_il24.json (synthetic_deep_v1_clean, IL 24, index 23)
- **Request body**: `{"direction":"inline","index":23,"mode":"raw","target_type":"deep_target","points":[[0.3020833333333333,0.880859375]],"labels":[1],"write_mask":false}`
- **run_id**: `1`
- **stop_reason**: `max_rounds`
- **best_round**: `3`
- **Round QC scores**: round 1: score=0.557747, truth_iou=0.569879, round 2: score=0.875716, truth_iou=0.924548, round 3: score=0.890049, truth_iou=0.862528
- **SHA-256**: `aee8777b7ab299a13f34bf41a5611a8fafd44ffe131549cd5768d3f7a61de3fb`

### refine_noisy_il21.json (synthetic_deep_v1, IL 21, index 20)
- **Request body**: `{"direction":"inline","index":20,"mode":"raw","target_type":"deep_target","points":[[0.3020833333333333,0.884765625]],"labels":[1],"write_mask":false}`
- **run_id**: `2`
- **stop_reason**: `qc_unreliable`
- **best_round**: `1`
- **Round QC scores**: round 1: score=0.204514, truth_iou=0.684404
- **SHA-256**: `cc596893259f114be16d1710f7770fec23a66b3342621ad6c1713a247b41186f`
