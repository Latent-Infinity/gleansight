# ALG.STATUS.THRESHOLDS ablation

**Study:** `ALG.STATUS.THRESHOLDS`  
**Freeze: no.** Sparse/Active density cut remains **3**. This is an LLM-labeled 10-cell probe at a fixed `as_of`. Humans validate the prompt and this result; they are not a hand-labeling panel.

## Prompt

Given ALG-STATUS exclusive predicates and ten constructed cells at a fixed UTC `as_of`, assign one status per cell. Then score exact agreement for Sparse/Active density cuts in {2, 3, 5}. Keep the default 3 on ties. Do not invent corpus papers.

## Dataset

Ten constructed cells (not DATA-NSQD-03): Unknown empty, Missing, Code-gap, Sparse pair (1 paper + 1 code), Active three, Active four, Mature, Stalled, Future-work-only, Invalid.

Command: `uv run pytest tests/nsqd/test_ablations.py -q --no-cov`

## Result

| Density cut | Exact agreement |
| --- | --- |
| 2 | 9/10 |
| 3 | 10/10 |
| 5 | 8/10 |

All cuts meet ≥ 8/10. Highest agreement is cut=3, which is also the v1 default, so **keep 3**. The 24-month recency window was not varied.

## Freeze status

- Sparse/Active cut remains **tunable**.
- `ALG-ABL` stays **not frozen**.
