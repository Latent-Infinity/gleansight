# ALG.AXES ablation

**Study:** `ALG.AXES`  
**Freeze: no.** Archive axes remain the v1 finance triple. This is an LLM-scored probe. Human validation of the prompt and result completed 2026-08-24; no second independent labeling panel was required.

## Prompt

Score each proposed archive-axis triple 0–2 on each of: illuminable for NS/QD discovery, not empty of research occupancy, not more than 10k cells. Keep the triple if the three scores sum to at least 4 on the 6-point scale. Do not invent corpus papers.

## Dataset

| Triple | Axes | Cardinality product | Scores (illuminable, not empty, not >10k) | Sum | Keep |
| --- | --- | --- | --- | --- | --- |
| finance-v1-mechanism-target-horizon | mechanism × target × horizon | 7 × 8 × 6 = 336 | 2, 2, 2 | 6 | yes |
| finance-v1-plus-tick-bucket | + tick-bucket | 7 × 8 × 6 × 50 = 16800 | 1, 2, 0 | 3 | no |
| color-flavor | color × flavor | 5 × 5 = 25 | 0, 0, 2 | 2 | no |

Command: `uv run pytest tests/nsqd/test_ablations.py -q --no-cov`

## Result

Keep only the current finance v1 triple. Extra morphospace axes stay metadata, not archive bins. Human validation retained the default without freezing it.

## Human validation

- **Validated:** yes, 2026-08-24.
- **Scope reviewed:** recorded prompt, three scored triples, and keep/reject result.
- **Decision:** keep the finance v1 mechanism × target × horizon triple as the current default; do not freeze the axes.

## Freeze status

- Archive-axis selection remains **tunable**.
- `ALG-ABL` stays **not frozen**.
- DATA-NSQD-03 was not invented.
