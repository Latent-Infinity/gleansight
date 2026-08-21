# Query

Hybrid paper search (FTS on title+abstract, vectors on markdown, one-based RRF) and extraction filters.

## Search papers

```bash
uv run python -m papers.cli query "optimization algorithm" --limit 10
```

Equivalent: `papers query "optimization algorithm" --limit 10`

## Filter by extractions

```bash
uv run python -m papers.cli filter algorithm_family --prompt-version-id PROMPT_VERSION_ID --constraint value_text=transformer
```

Equivalent: `papers filter algorithm_family --prompt-version-id PROMPT_VERSION_ID --constraint value_text=transformer`

`value_numeric` is parsed as float; `value_boolean` as 0/1. Repeat `--constraint` for AND within one field. `--latest-only` is the default.
