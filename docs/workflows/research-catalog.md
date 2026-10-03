# Verified research run catalog

The catalog indexes explicitly selected completed bundles under the current workspace's `output/` directory. It verifies source artifacts before indexing and again on every list or comparison. It never launches experiments, selects a winner, or grants execution or NSQD approval.

Install the optional research dependencies before verification:

```sh
uv sync --group research
```

Core API discovery works without these dependencies. A verification call without them returns the ordinary JSON error envelope with installation instructions.

## Select, verify, and index

Use the public API operations through the JSON CLI. Replace the example bundle names with actual completed runs in your workspace:

```sh
uv run gleansight api call research.runs.verify --input-json '{"bundle_path":"output/financial-jepa-capacity/RUN_A"}'
uv run gleansight api call research.runs.index --input-json '{"bundle_path":"output/financial-jepa-capacity/RUN_A"}'
uv run gleansight api call research.runs.index --input-json '{"bundle_path":"output/financial-jepa-capacity/RUN_B"}'
uv run gleansight api call research.runs.list --input-json '{"limit":50,"offset":0}'
```

Use `gleansight api --repo-root /absolute/workspace call ...` for another owned workspace. Indexing is explicit and idempotent. The catalog lives in `research_run_catalog` in the configured paper SQLite database. Verification and a cold list do not create this table. Bundle paths are stored relative to the workspace; identity JSON is independent of its filesystem location. Workspace backup/restore includes this table and the referenced bundles.

External paths and symlinked bundle directories are refused. Copy a selected external run into an owned `output/` directory first, preserving all artifact bytes. The copy is then verified as a selected local bundle. The capacity format has no internal run identifier: its selected directory name is included in catalog identity, alongside the manifest and every artifact digest. Distinct directory identities alone do not prove independent execution.

## Compare explicit identities

Take each `data.run_id` from indexing and pass those exact IDs:

```sh
uv run gleansight api call research.runs.compare --input-json '{"run_ids":["FIRST_64_CHARACTER_RUN_ID","SECOND_64_CHARACTER_RUN_ID"]}'
```

The API returns a separate `output/research-comparison/<UTC-run-id>/` bundle containing `comparison.json`, `report.md`, and their hash manifest. Source bundles remain unchanged. The result preserves source, protocol, split, code, manifest, and artifact identities; exact paired dates and seeds; method definitions; and horizon/tenor RMSE values in basis points. Differences are always reported as right minus left, with no winner or ranking.

Different workflows, classifications, verification strengths, sources, splits, protocols, code identities, dates, seed sets, methods, or metric definitions produce explicit incompatibility reasons. Missing exact paired dates also refuse numerical comparison. A failed capacity trial remains visible with its failure reason and no invented score or difference. Smoke runs, development diagnostics, and original canonical evaluation records retain distinct classifications.

Supported input verification strengths are:

- `financial-jepa-diagnostics`: existing semantic reconstruction of saved forecasts, fitted state, metrics, and exact validation dates.
- `financial-jepa-capacity`: existing capacity verifier checks fixed protocol, budgets, paired seeds/dates, state, forecasts, metrics, and declared failures. These remain development diagnostics.
- Original `financial-jepa`: verifies artifact hashes and available protocol/source/date/seed bindings. Original bundles lack exact saved paired dates and full reconstruction state, so the catalog labels these `artifact_hashes` and refuses numerical pairing. An `evaluation_record` classification preserves the original canonical label; it does not upgrade its verification strength.

Walk-forward preregistrations are plans, not executed metric bundles, and are refused. Changed or missing indexed artifacts appear as `verified: false` with a problem and no cached metrics in list results. Comparisons fail if any selected source is stale. Repair the source or explicitly index a newly verified bundle; listing never silently trusts stale cached results.
