# 004. Versioned prompts for analysis

## Status

Accepted

## Context

Extraction quality depends on the prompt text and schema. Re-running analysis must be attributable to a specific prompt version, and project-wide analysis may filter on an older extraction schema while targeting a newer prompt.

## Decision

Store prompts and immutable prompt versions in Piccolo. Analysis runs record `prompt_version_id`, profile, and model. `RunAnalysisUseCase` reuses the latest successful run for that idempotency key unless `force=True`.

`AnalyzeProjectUseCase` takes a **target** `prompt_version_id` for new runs. Each `ExtractionFilter` may name a different `prompt_version_id` whose existing extractions are queried (`latest_only` defaults true).

## Consequences

- Changing prompt text requires a new version row; old runs stay bound to the version they used.
- Filter constraints reuse `ExtractionStore.query` / `FilterByExtractionsUseCase`; the CLI parses `--constraint` with `_parse_constraints`.
