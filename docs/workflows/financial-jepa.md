# YieldJEPA independent prototype

YieldJEPA is an isolated mechanism study using U.S. Treasury-published Daily Treasury Par Yield
Curve Rates. It is not an exact Fin-JEPA replication and does not use the original paper's code,
private data, checkpoints, or reported metrics.

## Environment

Install the locked research and development groups:

```bash
uv sync --group research --group dev
```

Inspect the operational interface without acquiring data:

```bash
UV_NO_SYNC=1 PYTHONPATH=src .venv/bin/python scripts/run_financial_jepa.py --help
```

Only `--data-dir`, `--offline`, and `--output-dir` are configurable. Architecture, chronological
splits, seeds, variants, optimizer, epochs, ridge grid, and the 900-second deadline are fixed in
the protocol.

## Canonical run

Do not run the canonical experiment until the independent implementation audit is complete. Once
approved, the online command acquires the 2001-2025 yearly Treasury XML files and records their URLs,
UTC retrieval times, HTTP metadata, byte counts, and SHA-256 hashes:

```bash
UV_NO_SYNC=1 PYTHONPATH=src .venv/bin/python scripts/run_financial_jepa.py
```

The cache is `data/research/financial-jepa/treasury`. An offline rerun verifies every cached file
against its recorded byte hash before parsing:

```bash
UV_NO_SYNC=1 PYTHONPATH=src .venv/bin/python scripts/run_financial_jepa.py --offline
```

Outputs use a fresh `output/financial-jepa/<UTC-run-id>` directory. An explicit output path must be
fresh and below `output/financial-jepa` or the system temporary directory.

## Output contract

- `protocol.json` records stable protocol version `yield-jepa/1`, the frozen scientific choices, and
  the independent-study boundary.
- `source-metadata.json` records Treasury provenance, qualified rights metadata, and raw hashes.
- `results.json` retains every one of the nine variant/seed fits, all baselines, diagnostics, and the
  predeclared verdict. Each model/seed records one shared ridge alpha selected by aggregate
  validation RMSE across all horizons and tenors, plus separate coefficient, scaler, intercept, and
  combined identities. The direct ridge baseline records the same model identity components.
- `report.md` renders raw baseline RMSE, per-seed and aggregate JEPA RMSE, each model's own latent
  persistence comparison, split-level collapse diagnostics, failed conditions, and limitations.
- `run-metadata.json` is written last and binds the preceding artifacts by SHA-256. Its code identity
  covers the runner, lockfile, and every prototype module. Its frozen-protocol identity uses the
  emitted protocol version and `protocol.json` SHA-256, without relying on local planning or agent
  files. The timestamp is explicitly the start of the completion-marker write; a deadline check
  after that write and file sync removes the entire bundle if the full command exceeded 900 seconds.

A timeout or failure removes only the newly created incomplete output directory. It never removes
the Treasury source cache. No output is written to production databases, blobs, LanceDB indexes,
`docs`, `evidence`, `src`, or `tests`.

## Scientific boundary

The source metadata uses `NOASSERTION`, attributes Treasury, and gives a qualified U.S. government
work assessment referencing 17 U.S.C. 105. Treasury par yields are derived curve statistics; this
workflow stores neither underlying dealer quotations nor a claim of worldwide public-domain status.
No government endorsement is implied.

The only positive label available is `preliminary_descriptive_signal`, and it requires every frozen
condition to pass. Otherwise the valid result is `negative_or_inconclusive`. The workflow reports no
returns, Sharpe ratio, profitability, significance, or comparison with Fin-JEPA numbers.
