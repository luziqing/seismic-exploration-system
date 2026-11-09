# Data Provenance

## Where the demo data comes from

**100% synthetic, generated in this repository.** No field data, no vendor data, no licensed seismic survey, no third-party dataset and no model weights are shipped or referenced.

Run:

```bash
python scripts/generate_synthetic_seismic.py            # noisy ("raw") volume
python scripts/generate_synthetic_seismic.py --clean    # low-noise ("cleaner platform") volume
```

The script writes, under `data/npy/<name>/`:

| File | Contents |
|---|---|
| `amplitude.npy` | C-order `float32`, shape `[nIL, nXL, nSamples]` — SGSeg-compatible volume |
| `meta.json` | geometry, `dt_us`, shape, seed, SNR, generator version, licence |
| `truth/fault_mask.npy` | boolean ground truth for the fault trace |
| `truth/horizon_mask.npy` | boolean ground truth for the horizons |
| `truth/deep_target_mask.npy` | boolean ground truth for the weak low-frequency deep target |

All of these are **generated artefacts** and are gitignored. Only the generator script is committed.

## Determinism

`np.random.default_rng(seed)` with a fixed default seed. `--verify-only` re-generates in memory and asserts byte equality with the stored volume, plus shape/dtype/finite/meta consistency. Same seed → identical bytes on any machine with the same NumPy version.

## What the synthetic model represents

- Four gently undulating horizons built from Ricker wavelets at a shallow dominant frequency.
- A fault plane that offsets deeper horizons by a fixed throw, with a slowly varying lateral position.
- A weak elliptical **deep target** rendered with a lower dominant frequency and a deliberately small amplitude — the element the low-frequency conditioning is meant to reveal.
- Additive Gaussian noise at a declared SNR; `--clean` raises the SNR to represent a cleaner platform.

This is a **teaching / demonstration phantom**, not a geological model of any real area. It must not be used to claim geophysical accuracy.

## Licence

The generator and all data it produces are released under the repository's MIT licence. No attribution to any external dataset is required because no external dataset is used.

## Forbidden in this repository

- `*.sgy`, `*.segy`, `*.npy`, `*.vds`, `*.pt`, `*.pth` and other large binary volumes.
- Software-copyright application material (`doc/`) — it contains third-party entity details and is unrelated to this entry.
- Any statement that the data is "real", "field", or "validated against wells".
