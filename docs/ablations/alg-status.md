# ALG.STATUS.THRESHOLDS ablation

**Study:** `ALG.STATUS.THRESHOLDS`  
**Freeze: no.** Sparse/Active density cut remains **3**. This is an LLM-labeled 10-cell probe at a fixed `as_of`. Human validation of the prompt and result completed 2026-08-24; no hand-labeling panel was required.

## Prompt

Given ALG-STATUS exclusive predicates and ten constructed cells at a fixed UTC `as_of`, assign one status per cell. Then score exact agreement for Sparse/Active density cuts in {2, 3, 5}. Keep the default 3 on ties. Do not invent corpus papers.

## Dataset

Ten constructed cells at `as_of=2024-01-01T00:00:00Z` (not DATA-NSQD-03): Unknown empty, Missing, Code-gap, Sparse pair (1 paper + 1 code), Active three, Active four, Mature, Stalled, Future-work-only, Invalid.

Command: `uv run pytest tests/nsqd/test_ablations.py -q --no-cov`

## Result

| Density cut | Exact agreement |
| --- | --- |
| 2 | 9/10 |
| 3 | 10/10 |
| 5 | 8/10 |

All cuts meet ≥ 8/10. Highest agreement is cut=3, which is also the v1 default, so **keep 3**. The 24-month recency window was not varied.

## Human validation

- **Validated:** yes, 2026-08-24.
- **Scope reviewed:** recorded prompt, ten labeled cells, fixed `as_of`, and exact-agreement table.
- **Decision:** keep density cut 3 as the current default; do not freeze it. Recency window unit is recorded separately as 730 days (`docs/ablations/alg-status-window.md`).

## Freeze status

- Sparse/Active cut remains **tunable**.
- `ALG-ABL` stays **not frozen**.
