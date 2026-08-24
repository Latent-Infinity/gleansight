# ALG.AXES ablation

**Study:** `ALG.AXES`  
**Freeze: no.** Archive axes remain the v1 finance triple. This is an LLM-scored probe. Humans validate the prompt and this result; they are not a second independent labeling panel.

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

Keep only the current finance v1 triple. Extra morphospace axes stay metadata, not archive bins. Defaults remain tunable until a later freeze review of this prompt and table.

## Freeze status

- `ALG-ABL` stays **not frozen**.
- DATA-NSQD-03 was not invented.
