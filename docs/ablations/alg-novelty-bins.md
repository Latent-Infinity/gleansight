# ALG.NOVELTY_BINS ablation

**Study:** `ALG.NOVELTY_BINS`  
**Freeze: no.** Bin edges stay at 0.15 / 0.30 / 0.45 / 0.60. This probe uses a constructed `calibration` snapshot, not `smoke_only`. Human validation of the prompt and result completed 2026-08-24.

## Prompt

On a non-smoke calibration snapshot, score the approved pair: gamma-flow novelty term must be ≥ 1 when neighbors exist; mechanism-free mechanism term must stay 0. Do not use smoke_only. Do not invent DATA-NSQD-03 finance harvest records.

## Dataset

| Item | Role |
| --- | --- |
| Snapshot | constructed `optimization/1` calibration with a listed recall probe |
| Neighbors | one synthetic unit vector (math only) |
| DATA-NSQD-01 gamma-flow | candidate; nov ≥ 1 when evidence is defined on calibration |
| DATA-NSQD-02 mechanism-free | candidate; mech = 0 from empty inefficiency-block fields |

Command: `uv run pytest tests/nsqd/test_ablations.py -q --no-cov`

## Result

Both hold on calibration: gamma-flow `nov ≥ 1` (identical neighbor ⇒ evidence 0.0 ⇒ term 1); mechanism-free `mech = 0`. The same evidence on `smoke_only` still forces `nov = 0`. Bin edges are not changed.

## Human validation

- **Validated:** yes, 2026-08-24.
- **Scope reviewed:** recorded prompt, constructed calibration inputs, and runtime-backed result.
- **Decision:** keep the 0.15 / 0.30 / 0.45 / 0.60 edges as current defaults; do not freeze the edges. Packet 2a records `τ` as unset/report-only (`docs/ablations/alg-novelty-tau.md`).

## Freeze status

- Novelty bin edges remain **tunable**.
- `ALG-ABL` stays **not frozen**.
- DATA-NSQD-03 was not invented.
