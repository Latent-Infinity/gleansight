# Existing-system baseline

**Plan:** `docs/development-plan-open-work.md` Phase V0
**As of:** 2026-08-18

## Composition and ports

- Composition root: `src/papers/app/composition_root.py`
- Ports: `src/papers/app/ports.py`
- Domain and use-cases must not import provider SDKs (`docling`, `lancedb`, `sentence_transformers`, `httpx`). Mechanical check: `tests/support/test_import_boundary.py`.

## Quality gate

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

Coverage: `pyproject.toml` `[tool.coverage.report] fail_under` is **91.90** (combined lines+branches on `src`, omitting `src/papers/ui/*`).

Type check: `uv run ty check` covers `src` and `tests` except `src/papers/ui` and `tests/ui`. Flet 0.80 generated control types are not usable with ty (`Event[T]` invariance, `BasePage` vs `Page`). Test doubles are not required to implement every Protocol member; `invalid-argument-type` is ignored under `tests/**` only. Production `src/` (non-UI) is fully checked.

## Walking skeleton

Already running:

```bash
uv run pytest tests/app/use_cases/test_pipeline.py tests/app/use_cases/test_search.py -q
uv run python -m papers.cli --help
```

## Already in place

- `.gitignore` — ignores `data/` and local DBs; `tests/fixtures/approved/` is tracked
- `docs/library-standards.md` — uv, ruff, typer, rich, flet, docling, sentence-transformers, lancedb, Piccolo
- Mutation-testing tool: **none**

## Schema upgrades

`PiccoloDatabase.initialize_schema` still `create_table`s paper tables, then runs a forward-only `schema_migrations` runner (`001_baseline`, `002_job_integrity_check`, `003_nsqd_tables`, `004_nsqd_snapshot_versions`, `005_nsqd_policy_verdicts`, `006_nsqd_legacy_finance_policy_backfill`, `007_nsqd_map_job_type`, `008_nsqd_acquisition_cycles`). Opening an existing user database applies the jobs CHECK, NS-QD tables, durable store-local snapshot versions, reserved policy-verdict schema, the one-way backfill from legacy finance-only NSQD policy state to explicit `finance/1` identity, the persisted `map` job type, and fail-closed acquisition-cycle reservations with no down-migration. Restore from a file backup to roll back.

## Discovery-layer dependencies

See `docs/development-plan-ns-qd.md`. **EW-V0.11, EW-V0.3, EW-V0B, EW-V0A, EW-V1 are done.** HD-NSQD-01 is LanceDB. Discovery jobs use `nsqd_jobs` (not paper `jobs`) through a shared persisted runner for harvest, project, map, diverge, ground, score, and re-score. `src/nsqd/` includes ports, domain, application, Piccolo/LanceDB adapters, domain-policy isolation, approved reviewed-payload projection, pack-scoped map/status handling, Operator A, `python -m nsqd skeleton`, and `python -m nsqd harvest` (rejects essay-only / sourceless ingest and commits content-addressed snapshots with store-local versions). `nsqd_*` tables are created by migration `003_nsqd_tables`; migration `007_nsqd_map_job_type` upgrades existing job tables; migration `008_nsqd_acquisition_cycles` adds fail-closed acquisition-cycle reservations. DATA-NSQD-04 is acquired and EV-N09 is Required. N6 pack-aware sufficiency promotion is active; the full acquisition fallback, honest `production_valid`, and DATA-NSQD-03 remain pending.
