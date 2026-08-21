# Analysis

Queue analysis for one paper or for project members. Run the job worker to execute queued convert/analyze work.

## Analyze one paper

```bash
uv run python -m papers.cli analyze PAPER_ID --prompt-id PROMPT_ID --profile-id PROFILE_ID --model-name MODEL
```

Equivalent: `papers analyze PAPER_ID --prompt-id PROMPT_ID --profile-id PROFILE_ID --model-name MODEL`

`--prompt-version-id` is optional (latest version of `--prompt-id`). `--force` creates a new run even when a successful run already exists.

## Analyze a project

Members are the project ∩ optional `--label`. Extraction filters AND together; `--filter-prompt-version-id` may differ from the target `--prompt-version-id` (defaults to the target).

```bash
uv run python -m papers.cli analyze-project PROJECT_ID \
  --prompt-version-id PROMPT_VERSION_ID \
  --profile-id PROFILE_ID \
  --model-name MODEL \
  --field-path algorithm_family \
  --constraint value_text=transformer \
  --filter-prompt-version-id FILTER_PROMPT_VERSION_ID
```

Equivalent: `papers analyze-project PROJECT_ID --prompt-version-id PROMPT_VERSION_ID --profile-id PROFILE_ID --model-name MODEL`

## Run jobs

```bash
uv run python -m papers.cli run-jobs --max-jobs 10
```

Equivalent: `papers run-jobs --max-jobs 10`

`papers status` lists job-queue counts.
