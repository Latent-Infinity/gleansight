# Acquisition budget ablation

**Study:** `ALG.ACQUISITION_BUDGET`
**Freeze: no.** Current defaults remain **3 query batches per search pass, 25 candidates per discover call, 3 staged imports per search pass, and 2 approved rechecks before stop**. This artifact is math/state evidence on constructed searchable-failure worlds using a synthetic `PagedPaperBridge`. It is not empirical scholar traffic, not DATA-NSQD-03, and not a freeze of N6 acquisition bounds.

## Dataset

| Field | Value |
| --- | --- |
| Snapshot state | `calibration` via `PromoteSnapshotUseCase` on an empty finance snapshot |
| Domain policy | `finance/1` with one expected cell and one missing recall probe (searchable `ALG-SUF`) |
| Protocol | synthetic `PagedPaperBridge`; monkeypatch `QUERY_BATCH_LIMIT`, `STAGED_IMPORT_LIMIT`, `CANDIDATES_PER_BATCH`, and `RECHECK_CYCLE_LIMIT` in `nsqd.app.use_cases` |
| Loop semantics | per search pass: up to `QUERY_BATCH_LIMIT` discover calls; each result is sliced to `CANDIDATES_PER_BATCH`; new import capacity is `STAGED_IMPORT_LIMIT`; approved rechecks stop at `RECHECK_CYCLE_LIMIT` |
| Metric | cycle stages `source_paper_id:useful`; separate recheck probe asks whether an approved-but-still-insufficient projection reaches another search |
| Grid | batches ∈ {1,2,3}; staged ∈ {1,2,3}; candidates ∈ {1,5,25} |
| Worlds | dense first page (useful is rank 2 of 25); useful only on page 2 after 25 duds |

Generated Data Authorization allows synthetic values for unit tests of math and state policy. These candidates are not approved fixtures, harvest-seed citations, or corpus evidence. The synthetic bridge validates acquisition-loop behavior, not the full live scholar path. Production also couples `CANDIDATES_PER_BATCH` to each live discover-call result size.

## Result

Command: `uv run pytest tests/nsqd/test_acquisition_budget_ablation.py -q --no-cov`

Passed: **5 tests**.

### Dense first page (useful at rank 2)

| Winning budgets (batches, staged, candidates) | Notes |
| --- | --- |
| (1,2,5), (1,2,25), (1,3,5), (1,3,25), (2,2,5), (2,2,25), (2,3,5), (2,3,25), (3,2,5), (3,2,25), (3,3,5), (3,3,25) | Smallest winner is **(1,2,5)**. Current default **(3,3,25)** also wins. |

One search batch is enough when the useful result is already on the first dense page. Candidate pages of 1 never see rank 2. Staged-import limit 1 keeps only the dud.

### Useful only on page 2

| Winning budgets (batches, staged, candidates) | Notes |
| --- | --- |
| (2,2,1), (2,3,1), (3,2,1), (3,3,1) | Smallest winner is **(2,2,1)**. Current default **(3,3,25)** loses. |

The explicit counterexample is **(3,3,25)**: the first discover call can return enough candidates to consume the search pass's 3 staged-import slots, so the pass stops before page 2 is queried. Extra batches help only when earlier calls leave spare import capacity. This exposes a dense-first-page versus later-page tradeoff; the current default is not a demonstrated optimum.

### Recheck ceiling

| Rechecks | After approved-but-still-insufficient projection |
| --- | --- |
| 1 | `recheck_budget`; no second search |
| 2 | searches again |

Recheck counts advance only after a human-approved projection is supplied and promotion still returns `insufficient`.

## Decision

Keep **3 / 25 / 3 / 2** as the **current compatibility default**, but keep it tunable and do not treat it as optimal on this evidence.

- The probe does not show that 25 candidates is best. It shows that a large first-call result can preserve dense-page coverage while preventing a later-page hit under the current per-pass import ceiling.
- `CANDIDATES_PER_BATCH=25` is retained for compatibility because it is wired into the live discover-call size. Changing it changes operational behavior, while this synthetic probe does not establish a better production setting.
- Do not freeze until a human-reviewed production acquisition log repeats the comparison.

No-self-approval remains mandatory: LLM output cannot approve corpus evidence, and rechecks occur only after actual human-approved projections.

## Human validation

- **Validated:** yes, 2026-08-25.
- **Scope reviewed:** synthetic paging/import interaction, per-search-pass limits, live discover-call coupling, the page-2 counterexample, approved-recheck stop behavior, and probe limitations.
- **Decision:** keep **3 / 25 / 3 / 2** as the current compatibility default; do not freeze.
- **Outcome:** `approved_default_tunable`.

## Reopen triggers

- Human-reviewed production acquisition logs materially disagree with this synthetic result.
- Live discover paging or discover-call size semantics change.
- Per-search-pass shortlist or staged-import behavior changes.
- Approved recheck-stop semantics change.
- A follow-up probe evaluates an alternative live-compatible paging/import contract.

## Freeze status

- Numeric defaults remain **tunable**.
- Outcome is **`approved_default_tunable`**, not `frozen`.
- `ALG-ABL` stays **not frozen**.
- Novelty threshold `τ`, the 24-month status window, and Operators B–G are not addressed here.
