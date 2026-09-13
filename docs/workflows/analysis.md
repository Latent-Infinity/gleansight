# Analysis

Queue analysis for one paper or for project members. Run the job worker to execute queued convert/analyze work.

## Analyze one paper

```bash
uv run python -m papers.cli analyze PAPER_ID --prompt-id PROMPT_ID --profile-id PROFILE_ID
```

Equivalent: `papers analyze PAPER_ID --prompt-id PROMPT_ID --profile-id PROFILE_ID`

`--prompt-version-id` is optional (latest version of `--prompt-id`). Omit `--model-name` to use configured `llm.default_model`, or pass `--model-name MODEL` as an explicit override. `--force` creates a new run even when a successful run already exists.

## Analyze a project

Members are the project ∩ optional `--label`. Extraction filters AND together; `--filter-prompt-version-id` may differ from the target `--prompt-version-id` (defaults to the target).

```bash
uv run python -m papers.cli analyze-project PROJECT_ID \
  --prompt-version-id PROMPT_VERSION_ID \
  --profile-id PROFILE_ID \
  --field-path algorithm_family \
  --constraint value_text=transformer \
  --filter-prompt-version-id FILTER_PROMPT_VERSION_ID
```

Equivalent: `papers analyze-project PROJECT_ID --prompt-version-id PROMPT_VERSION_ID --profile-id PROFILE_ID`

Omit `--model-name` to use configured `llm.default_model`, or pass `--model-name MODEL` as an explicit override.

## Run jobs

```bash
uv run python -m papers.cli run-jobs --max-jobs 10
```

Equivalent: `papers run-jobs --max-jobs 10`

`papers status` lists job-queue counts.

## JEPA retained-evidence gaps report

Render the retained JEPA finance synthesis without invoking an LLM or changing its historical inputs:

```bash
uv run python scripts/report_jepa_ideas_gaps.py
```

The command creates a fresh ignored `output/jepa-finance-gap-analysis/<UTC-run-id>/` directory containing:

- `report.md`: the human-readable gap synthesis, retained hypotheses, baseline replication plan, targeted adjacent investigation directions, and resource requirements.
- `report-data.json`: the same synthesis and validated investigation plan as structured data.
- `provenance.json`: source hashes, cutoffs, schema hash, and citation metadata.
- `cited-excerpts/`: copied, hash-bound excerpts used by the report.

This is deterministic synthesis of retained evidence. It performs no new literature search, backtest, model training, investigation execution, or approval, and it never writes to `docs/`, `evidence/`, or `tests/fixtures/`. Use `--output-dir` only for a fresh directory below repository `output/` or the system temporary directory.

Read the replication plan in order: establish the core-paper baseline first, then attempt targeted adjacent reproductions. The strategy labels are binding:

- `exact_replication` follows the original protocol without substitutions.
- `constrained_reproduction` records every concrete substitution; direct metric comparison is allowed only when metric comparability is supported.
- `conceptual_reimplementation` tests the mechanism only and forbids direct comparison to the paper's metrics.

Resource requirements are evidence-qualified. Unknown hardware, VRAM, GPU-hour, data, model, code, or checkpoint details remain structured `null` values with an uncertainty rationale; they are not guessed.

## JEPA baseline replay diagnostics

Baseline replay is a separate diagnostic command, not report generation:

```bash
uv run python scripts/replay_jepa_operator_baselines.py
```

An ordinary replay creates isolated temporary scratch database/index state and writes its retained diagnostic bundle to a fresh ignored `output/jepa-baseline-replay/<UTC-run-id>/`. `--scratch-dir` may select a fresh, dedicated direct child of the system temporary directory; `--output-dir` may select a fresh directory below repository `output/` or system temporary storage. Use `--verify-current-receipt` when only the retained receipt should be checked. Replay requires the configured local embedding service and packet-pinned model digests; it does not train a model or update historical evidence.

## Active LLM investigation planning

Use the existing configured LLM provider to retrieve project evidence and request a replication-first plan:

```bash
uv run python -m papers.cli ask QUESTION --investigation-plan --project PROJECT_ID --num-docs 5 --model MODEL
```

Investigation-plan mode validates the provider response against the structured schema before rendering it. The plan must put the core baseline first, keep adjacent directions targeted, identify exact versus constrained versus conceptual reproduction, and state whether metrics are directly comparable. Unknown resource facts remain `null`, not estimates invented to complete the plan. This mode plans work only: it does not train a model, run experiments, admit evidence, or approve artifacts. Omit `--investigation-plan` for unchanged ordinary corpus Q&A.
