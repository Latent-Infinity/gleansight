# ALG.NOV threshold τ

**Study:** `ALG.NOV.TAU`
**Outcome:** `approved_default_tunable` at `τ = 0.45`. Packet 2a accepted report-only operation on 2026-08-25; packet 2b evidence and the separate human activation decision superseded that runtime state on 2026-08-29.

## Runtime semantics

| Choice | v1 |
| --- | --- |
| `τ` | **0.45**, approved default, tunable (`settings.nsqd.novelty_threshold_tau`; no CLI `--tau`) |
| Gate | raw-evidence kill: `evidence < 0.45` zeros the novelty term; smoke / empty / already_done / renamed still force term 0 |
| Evidence | reported on the scored artifact |
| Not chosen | frozen `0.45`; novelty-term kill (`nov < N`) |

Low evidence still maps to the normal discrete novelty term first. The activated raw-evidence threshold then zeros that term when `evidence < 0.45`. An explicit `tau=None` remains available to isolated evaluation code but is not the runtime default.

## Dataset

Existing novelty-term table tests plus `test_novelty_threshold_tau_is_active_and_tunable`. Score stamps `tau: 0.45` and `tau_semantics: approved_default_tunable`.

Command: `uv run pytest tests/nsqd/test_domain_policies.py::test_novelty_threshold_tau_is_active_and_tunable tests/nsqd/test_corpus_index.py -q --no-cov`

## Decision

Activate **`τ = 0.45` as `approved_default_tunable`**. The packet contains 120 accepted autonomous writer/reviewer labels under N11.3/N11.4, with 30 near-duplicate and 30 novel rows per policy. At `0.45`, overall novel false-kill is 3.33%, finance is 0%, optimization is 6.67%, and near-duplicate false-pass is 21.67%. Measurement inventory is fail-closed and does not fabricate pairs. Operator E remains deferred; this decision does not authorize operators C–G, calendar-month semantics, or CLI `--operator`.

## Human validation

- **Validated:** packet 2a accepted by proceeding after the recommended unset/report-only outcome (2026-08-25).
- **2b:** evidence-only workflow approved 2026-08-27 and evaluated 2026-08-29. The balanced packet recommends `τ = 0.45`.
- **Runtime activation:** explicitly approved 2026-08-29 as `approved_default_tunable`; not frozen.

## Freeze status

- `τ = 0.45` is active and **not frozen**.
- Bin edges stay tunable and separate (`ALG.NOVELTY_BINS`).
