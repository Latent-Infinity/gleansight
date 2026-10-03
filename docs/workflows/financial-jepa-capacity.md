# YieldJEPA input and readout capacity diagnostics

This offline workflow extends the Treasury YieldJEPA prototype. It is independent of the deferred
Fin-JEPA paper replication audit. Training uses 2001–2017; the existing neural checkpoint selection
and the new ridge selection use 2018–2021. Every reported metric is a development-selection metric.
The command does not open the reserved 2022–2025 cache files.

Run against an explicit, verified diagnostic bundle:

```sh
UV_NO_SYNC=1 PYTHONPATH=src .venv/bin/python scripts/diagnose_jepa_capacity.py \
  --source-bundle output/financial-jepa-diagnostics/20260913T234227Z-cc31f53f22c0
```

`--data-dir` may select another offline cache containing the same hash-identified 2001–2021 files.
The source bundle is strictly reloaded, and its frozen schema, dates, targets, context windows,
training scaler, selected states, seed identities and cache hashes must agree. Changed source
artifacts, a different selection protocol, or missing cache files cause refusal. There is no
network-acquisition option and no override for years, seeds, alphas or readout budgets.

The command prints two new immutable output directories:

- `output/financial-jepa-capacity/<UTC-id>/`: actual matched development comparisons.
- `output/financial-jepa-walkforward-preregistration/<UTC-id>/`: a separate versioned plan,
  explicitly `preregistered_not_executed`.

The fixed resource budget is three seeds (17, 29, 43), six methods, four ridge alpha candidates,
five horizons and eight tenors: 360 small ridge fits, no new neural training, CPU model inference
in batches of 128, and a 900-second deadline checked between bounded steps. It is not hard
preemption of a BLAS call. Files have a 128 MiB read/write bound. A failed publication or deadline
overrun removes only this invocation's newly created output directories.

## What is matched

| Group | Observations supplied to every branch | Readout features | Ridge parameters | Methods |
| --- | --- | ---: | ---: | --- |
| Current | The same last curve, eight yields | 8 | 360 | Raw yields; selected EMA encoder with train-only PCA; paired initial EMA encoder with train-only PCA |
| History | The same 30 × 8 context window | 16 per horizon | 680 | Raw history with train-only PCA; selected predicted future; paired initial predicted future |

All branches share exact origin/target dates, targets, seeds, ridge alpha grid, horizon structure
and train-only readout fitting. The current neural branches receive only the last curve; they do
not receive pooled history. History branches receive identical full windows. The shared alpha is
selected over all horizons for each method and seed; ascending alpha order breaks exact ties.

PCA standardization and components use training features only. Reports separate nominal readout
parameter counts, numerical feature rank and retained PCA variance. Compression loses information.
Encoder parameter counts, nonlinear expressiveness and representation pretraining capacity are
not matched, so these results do not establish total-capacity equivalence or a representation-only
causal effect. The original checkpoint already used the selection interval.

`document.json` contains the frozen protocol, source and code identities, common membership dates,
per-seed trials, paired selected-minus-reference RMSE differences, variation and failures.
`fits.npz` contains selected readout state, projections, forecasts and actual selection targets.
`report.md` presents both groups and their limitations. The completion marker `run-metadata.json`
hash-binds all three artifacts and is written last. Existing runs are never overwritten.

RMSE is `100 × sqrt(mean((forecast − actual)²))` over raw percentage-point yields, reported in basis
points. Paired differences use common successful seeds only and show excluded counts. Aggregate
reports include mean, sample standard deviation, min/max and failure counts. Repeated deterministic
raw baselines are not independent replications. No significance, profitability, model-winner,
held-out or paper-equivalent claim is made.

Verify a completed capacity bundle through the public research verifier:

```python
from pathlib import Path
from research.financial_jepa.capacity_validation import verify_capacity_bundle

bundle = verify_capacity_bundle(Path("output/financial-jepa-capacity/<UTC-id>"))
print(bundle.document["aggregates"])
```

Verification checks hashes, exact pairing budgets and seed/method membership, chronological date
partitions, target and readout shapes, forecasts against recorded metrics, paired aggregates and
failure records. Altering metrics or relabeling the development result is refused even if a caller
recomputes the outer file hashes.

## Separate walk-forward preregistration

Version `yield-jepa-walkforward-preregistration/1` declares these retrospective development folds:

| Fold | Training | Selection | Diagnostic |
| --- | --- | --- | --- |
| 1 | 2001–2011 | 2012–2013 | 2014–2015 |
| 2 | 2001–2013 | 2014–2015 | 2016–2017 |
| 3 | 2001–2015 | 2016–2017 | 2018–2019 |
| 4 | 2001–2017 | 2018–2019 | 2020–2021 |

Every observed date belongs explicitly to a fold partition; membership and selection-plan
identities are hash-bound. The plan requires fold-local scalers, PCA, fresh seeded models and ridge
fits. Source selected checkpoints are recorded for provenance and forbidden as fold initializers.
Contexts and targets must remain wholly within each partition, retaining the original missing-row,
gap and methodology boundaries. Diagnostic partitions cannot select epochs or alphas. Every
seed/fold failure and excluded pair must remain visible; fold and seed variation is descriptive
because chronological folds are dependent.

The preregistration executes no folds. A later development executor is bounded to four folds,
three seeds, ten epochs each, CPU and 3600 seconds. The separate reserved interval remains
2022-01-01 through 2025-12-31. This command provides no loader or authorization to evaluate it;
a future evaluator requires a new versioned protocol and frozen selection handoff before opening
reserved values. Existing diagnostic guards and historical artifacts remain unchanged.
