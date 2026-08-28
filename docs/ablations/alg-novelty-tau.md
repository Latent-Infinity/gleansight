# ALG.NOV threshold τ

**Study:** `ALG.NOV.TAU`
**Outcome:** `unset` (report-only). Packet 2a accepted 2026-08-25. Packet 2b evidence collection is authorized; no executable threshold is authorized.

## Semantics (packet 2a)

| Choice | v1 |
| --- | --- |
| `τ` | **unset** (`None`) |
| Gate | novelty **term** from ALG-NOV bins; smoke / empty / already_done / renamed still force term 0 |
| Evidence | reported on the scored artifact |
| Not chosen | raw-evidence kill (`evidence < τ`) or novelty-term kill (`nov < N`) |

Low evidence (near-duplicate neighborhood) still maps to term **1**, not an extra kill. `apply_novelty_threshold(..., tau=0.15)` would zero that term; the gate does not pass a numeric `τ`.

## Dataset

Existing novelty-term table tests plus `test_novelty_threshold_tau_is_unset_and_report_only`. Score stamps `tau: null` and `tau_semantics: unset_report_only`.

Command: `uv run pytest tests/nsqd/test_domain_policies.py::test_novelty_threshold_tau_is_unset_and_report_only tests/nsqd/test_corpus_index.py -q --no-cov`

## Decision

Keep **unset / report-only** while packet 2b collects 120 offline human-approved labels. Agent labels are pending proposals only. Evaluate bin-aligned values under the false-kill constraints in `docs/ablations/alg-novelty-tau-2b.md`; if none qualify, keep `τ` unset. Operator E stays deferred if it would use novelty as a kill.

## Human validation

- **Validated:** packet 2a accepted by proceeding after the recommended unset/report-only outcome (2026-08-25).
- **2b:** evidence-only workflow approved 2026-08-27. The required repository-local pair set does not yet exist, so no executable `τ` is authorized.

## Freeze status

- `τ` remains **unset**, not a frozen number.
- Bin edges stay tunable and separate (`ALG.NOVELTY_BINS`).
