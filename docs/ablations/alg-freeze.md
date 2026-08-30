# ALG freeze packet

**Study:** `ALG.FREEZE`
**Outcome:** Packet 3 kept every then-active numeric/default family `approved_default_tunable` and left `τ` unset. Packet 2b plus the later explicit human activation superseded only that `τ` state: `τ = 0.45` is now `approved_default_tunable`. Freeze is **not** approved.

Packet 3 compared only freeze-now versus keep-tunable. Existing constructed and LLM probes already support the current defaults; they do not support locking them. Families were reviewed together because the evidence (no production-valid calibration repeat) is the same for all of them.

## Decisions

| Family | Outcome | Freeze | Reopen |
| --- | --- | --- | --- |
| `ALG.AXES` | approved_default_tunable | no | second pack needs a different archive triple |
| `ALG.K` | approved_default_tunable | no | production-valid leave-one-out Spearman repeat |
| `ALG.NOVELTY_BINS` | approved_default_tunable | no | labeled novelty-term disagreements |
| `ALG.NOV.TAU` | approved_default_tunable at `0.45` | no | production-valid calibration repeat or policy-specific false-kill drift |
| `ALG.STATUS.THRESHOLDS` | approved_default_tunable | no | production-valid map labels vs density cut 3 |
| `ALG.STATUS.WINDOW` | approved_default_tunable | no | map uniformly Stalled/Active |
| `ALG.VIABILITY` | approved_default_tunable | no | recorded 1–4 rubric |
| `ALG.ACQUISITION_BUDGET` | approved_default_tunable | no | production acquisition logs or paging-contract change |

Runtime defaults are: k=5, bins 0.15/0.30/0.45/0.60, density cut 3, window 730 days (overridable), viability 0/5 stubs, acquisition 3/25/3/2, and tunable `τ = 0.45`.

Command: `uv run pytest tests/nsqd/test_ablations.py::test_alg_family_freezes_stay_tunable -q --no-cov`

## Human validation

- **Validated:** packet 3 accepted 2026-08-26 by proceeding after the recommended keep-tunable outcome.
- **Superseded state:** packet 2b plus explicit human activation set tunable `τ = 0.45` on 2026-08-29 without approving a freeze.
- **Not authorized:** `frozen` for any family.

## Freeze status

- `ALG-ABL` stays **not frozen**.
