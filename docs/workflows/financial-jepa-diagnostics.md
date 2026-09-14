# YieldJEPA development diagnostics

This workflow is a development-selection diagnostic over Treasury observations from 2001 through
2021 only. It trains on 2001-2017 and selects checkpoints and ridge alphas on 2018-2021. It does not
read or evaluate 2022-2025, and its metrics are not held-out estimates.

Install the locked environment and inspect the operational interface without reading data:

```bash
uv sync --group research --group dev --group infra
UV_NO_SYNC=1 PYTHONPATH=src .venv/bin/python scripts/diagnose_financial_jepa.py --help
```

The command is offline by default and opens the explicitly named 21 yearly cache files. It never
globs the cache. `--no-offline` permits acquisition of those same years only. `--data-dir` and
`--output-dir` are operational controls; architecture, three seeds, ten epochs, optimizer, masking,
EMA, ridge grid, splits, and 900-second deadline are fixed.

Successful runs create eight files under a fresh
`output/financial-jepa-diagnostics/<UTC-run-id>/` directory:

- `protocol.json`, `source-metadata.json`, and `results.json` record the frozen protocol, source
  identity, and development-selection metrics.
- `states.npz` contains exact initial and selected model tensors.
- `ridge.npz` contains all fitted feature means/scales, coefficients, and intercepts.
- `validation.npz` contains contexts, actual futures, ISO dates, latents, representations, and every
  forecast.
- `report.md` states the diagnostic interpretation and capacity caveats.
- `run-metadata.json` is the completion marker written last and hash-binds the other seven files.

The strict loader hashes every artifact before parsing, rejects unknown keys and object arrays, and
uses `numpy.load(..., allow_pickle=False)`. A failure or deadline overrun removes the incomplete run
directory. The original `output/financial-jepa` namespace is rejected.

Raw history is a 240-input baseline and is not capacity-matched to the 16-dimensional neural probes.
Frozen-random comparisons are paired by seed. Results support no winner, causality, profitability,
significance, or untouched-holdout claim.
