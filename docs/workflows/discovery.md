# Discovery and import

Find candidates, then import them as papers. Attach existing project and tag IDs on import when you have them.

Actual invocation is `uv run python -m papers.cli …`. The `papers` prefix below is the same Typer command set.

## Discover

```bash
uv run python -m papers.cli discover "optimization algorithm" --max-results 20
```

Equivalent: `papers discover "optimization algorithm" --max-results 20`

Optional filters include `--year-min`, `--year-max`, `--venue`, and `--include-paywalled`.

## Import

Import one candidate. Repeat `--project` and `--tag` for multiple IDs. Unknown IDs fail without writing a paper.

```bash
uv run python -m papers.cli import CANDIDATE_ID --project PROJECT_ID --tag TAG_ID
```

Equivalent: `papers import CANDIDATE_ID --project PROJECT_ID --tag TAG_ID`

Re-importing an already-imported candidate attaches missing projects/tags and does not enqueue a second download.
