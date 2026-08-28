# ALG freeze packet

**Study:** `ALG.FREEZE`
**Outcome:** `approved_default_tunable` for every numeric/default family; `τ` stays `unset`. Freeze is **not** approved.

Packet 3 compared only freeze-now versus keep-tunable. Existing constructed and LLM probes already support the current defaults; they do not support locking them. Families were reviewed together because the evidence (no production-valid calibration repeat) is the same for all of them.

## Decisions

| Family | Outcome | Freeze | Reopen |
| --- | --- | --- | --- |
| `ALG.AXES` | approved_default_tunable | no | second pack needs a different archive triple |
| `ALG.K` | approved_default_tunable | no | production-valid leave-one-out Spearman repeat |
| `ALG.NOVELTY_BINS` | approved_default_tunable | no | labeled novelty-term disagreements |
| `ALG.NOV.TAU` | unset | no | labeled near-duplicate vs novel pairs (packet 2b) |
| `ALG.STATUS.THRESHOLDS` | approved_default_tunable | no | production-valid map labels vs density cut 3 |
| `ALG.STATUS.WINDOW` | approved_default_tunable | no | map uniformly Stalled/Active |
| `ALG.VIABILITY` | approved_default_tunable | no | recorded 1–4 rubric |
| `ALG.ACQUISITION_BUDGET` | approved_default_tunable | no | production acquisition logs or paging-contract change |

Runtime defaults stay: k=5, bins 0.15/0.30/0.45/0.60, density cut 3, window 730 days (overridable), viability 0/5 stubs, acquisition 3/25/3/2, `τ` unset.

Command: `uv run pytest tests/nsqd/test_ablations.py::test_alg_family_freezes_stay_tunable -q --no-cov`

## Human validation

- **Validated:** packet 3 accepted 2026-08-26 by proceeding after the recommended keep-tunable outcome.
- **Not authorized:** `frozen` for any family.

## Freeze status

- `ALG-ABL` stays **not frozen**.
