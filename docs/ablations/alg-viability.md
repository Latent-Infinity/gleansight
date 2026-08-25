# ALG.VIABILITY ablation

**Study:** `ALG.VIABILITY`  
**Freeze: no.** `mech` / `fals` / `dpred` remain 0/5 presence stubs. This is an LLM probe. Human validation of the prompt and result completed 2026-08-24; no two-reviewer kappa panel was required.

## Prompt

On the approved gamma-flow / mechanism-free pair plus five extra constructed cards, decide whether to introduce intermediate scores 1–4 for mech/fals/dpred. Introduce them only if a recorded rubric is tighter than presence/absence and would not invent graded prose quality. Otherwise keep 0/5 stubs.

## Dataset

Approved pair DATA-NSQD-01/02 (requirement cards, never corpus) plus five constructed finance cards with present vs empty inefficiency-block fields. No DATA-NSQD-03.

Command: `uv run pytest tests/nsqd/test_ablations.py -q --no-cov`

## Result

Keep **0/5 presence stubs**. No 1–4 intermediates are introduced. `dval` stays a provenance-bearing assigned integer (not LLM self-approval of corpus evidence). Cohen’s κ is not applicable because a second label set was not collected.

## Human validation

- **Validated:** yes, 2026-08-24.
- **Scope reviewed:** recorded prompt, approved/constructed card set, and no-intermediate-rubric result.
- **Decision:** keep the 0/5 presence stubs as current defaults; do not freeze the viability rubrics.

## Freeze status

- Viability factor rubrics remain **tunable**.
- `ALG-ABL` stays **not frozen**.
