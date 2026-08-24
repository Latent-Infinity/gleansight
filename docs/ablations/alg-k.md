# ALG.K ablation

**Study:** `ALG.K`  
**Freeze: no.** Production nearest-neighbor size remains **k=5**. This artifact is math/state evidence on a constructed `calibration` snapshot. It is not empirical finance calibration, not DATA-NSQD-03, and not a freeze of ALG-NOV k.

## Dataset

| Field | Value |
| --- | --- |
| Snapshot state | `calibration` via `PromoteSnapshotUseCase` |
| Domain policy | `optimization/1` with a listed recall probe (`opt-probe` → `doi:10.1/opt-0`) |
| Corpus | 28 synthetic 2-D unit vectors (20 clustered, 8 angular outliers) |
| Protocol | leave-one-out k-NN cosine distance; evidence = mean of first k distances; every item must have k neighbors and both rank vectors must vary |
| Items n | 28 |
| k values | {3, 5, 10} |
| Baseline | k=5 |
| Metric | Spearman ρ of item evidence ranks vs k=5 |
| Threshold | ρ ≥ 0.90 to treat a k as interchangeable with 5 |

Generated Data Authorization allows synthetic values for unit tests of math. These vectors are not approved fixtures, harvest-seed citations, or corpus evidence.

## Result

Command: `uv run pytest tests/nsqd/test_k_ablation.py -q --no-cov`

| k | Spearman ρ vs k=5 | Meets ρ ≥ 0.90 |
| --- | --- | --- |
| 3 | ≥ 0.90 (≈ 0.931) | yes |
| 5 | 1.0 | yes (identity) |
| 10 | < 0.90 (≈ 0.824) | no |

k=3 preserves novelty ranks relative to k=5 on this set. k=10 does not: expanding the neighborhood past local cluster structure reshuffles ranks. Keep the v1 default **k=5**. Do not freeze k until a human-approved calibration corpus with listed recall probes (finance/1 still needs DATA-NSQD-03) repeats the study.

## Freeze status

- Numeric default k=5 remains **tunable**.
- `ALG-ABL` stays **not frozen**.
- `ALG.AXES`, `ALG.NOVELTY_BINS`, `ALG.STATUS.THRESHOLDS`, and `ALG.VIABILITY` are not addressed here.
